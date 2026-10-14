"""Lectura del sistema de campo (ADCP) y de la base de sueldos, sólo lectura,
con SQL crudo y text().

Del campo: el maestro de tareas, con el id que usan los partes (la Unidad
sugerida y la marca No facturable se leen en vivo del tercer segmento de su
descripción, y Facturación no guarda copia:
docs/superpowers/plans/2026-10-12-unidad-desde-campo.md), los clientes y
las fincas, con id, para los Comprobantes, y los partes diarios para el Cruce
(plan de la E3, decisión 6). De sueldos: las Empresas emisoras.

Preliquidación lee los mismos maestros, pero un módulo no importa a otro
(ADR-0013): el SQL se copia. La traducción de errores y los timeouts son del
núcleo (app/core/database.py): acá no se configuran.
"""

import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import traducir_errores_externa
from app.core.models import ahora_utc
from app.modulos.facturacion.fechas import mes_siguiente
from app.modulos.facturacion.unidades import traducir_unidad

# El maestro de tareas: la misma tabla, el mismo filtro de bajas y el mismo
# orden que QUERY_TAREAS de Preliquidación, más el id. La `descripcion` viene
# cruda y se corta en Python (obtener_tareas): el primer segmento es el grupo
# de tareas y el tercero, la unidad. Con SUBSTRING_INDEX, una descripción de
# dos segmentos devolvería el segundo, que es el grupo de pago. El grupo de
# pago y el grupo_factura no los usa este módulo.
QUERY_TAREAS = text("""
    SELECT ta.id AS tarea_id,
           ta.nombre AS nombre_tarea,
           ta.descripcion AS descripcion
    FROM laa_tareas ta
    WHERE ta.estado <> 9
    ORDER BY ta.nombre
""")

# La misma, con las dadas de baja: el histórico resuelve tareas por nombre y
# la planilla vieja nombra tareas que hoy están de baja.
QUERY_TAREAS_CON_BAJA = text("""
    SELECT ta.id AS tarea_id,
           ta.nombre AS nombre_tarea,
           ta.descripcion AS descripcion
    FROM laa_tareas ta
    ORDER BY ta.nombre
""")

# Clientes y fincas: las consultas de Preliquidación, con el id. Activo usa la
# misma regla que el filtro (estado distinto de 9; un NULL no cuenta), para
# que un cliente no sea activo en una lectura y de baja en la otra.
QUERY_CLIENTES = text("""
    SELECT c.id, c.nombre
    FROM laa_clientes c
    WHERE c.estado <> 9
    ORDER BY c.nombre
""")

QUERY_CLIENTES_CON_BAJA = text("""
    SELECT c.id, c.nombre,
           CASE WHEN c.estado <> 9 THEN 1 ELSE 0 END AS activo
    FROM laa_clientes c
    ORDER BY c.nombre
""")

# Las fincas de un cliente, por su id. No exige que el cliente esté activo:
# un Comprobante puede conservar un cliente que pasó a baja (plan de la E2,
# regla 7) y sus Líneas siguen validando la finca contra él.
QUERY_FINCAS_DE_CLIENTE = text("""
    SELECT f.id, f.nombre
    FROM laa_fincas f
    WHERE f.idcliente = :cliente_id
      AND f.estado <> 9
    ORDER BY f.nombre
""")

# Todas las fincas activas con su cliente, para el script del histórico.
QUERY_TODAS_LAS_FINCAS = text("""
    SELECT f.id, f.nombre, f.idcliente AS cliente_id
    FROM laa_fincas f
    WHERE f.estado <> 9
    ORDER BY f.idcliente, f.nombre
""")

# Las Empresas emisoras: la consulta del endpoint de empresas de
# Preliquidación, copiada (plan de la E2, regla 8: si aparece un tercer uso,
# se sube al núcleo).
QUERY_EMPRESAS = text(
    "SELECT DISTINCT empresa FROM nuempleados "
    "WHERE borrado IS NULL OR borrado <> 'S' "
    "ORDER BY empresa"
)


# ─── Los partes del campo, para el Cruce ────────────────────────────────────
# Una fila por (parte, tarea), copiada de las ramas de QUERY_PRINCIPAL de
# Preliquidación (ADR-0013: se copia, no se importa), con lo que lee Power BI:
#   PULVERIZADA  sólo el tractor 1 (trancadas1, hsjornal1, hsmaquina1), sumado
#                por parte; la tarea y `unidades` son de la cabecera, así que
#                `unidades` cuenta una sola vez (MAX)
#   MAQUINARIA y TAREAS MANUALES  la tarea es de cada registro: se suma por
#                cabecera y tarea
# Sin la planilla de cosecha (no entra en el Cruce) ni el tractor 2.
#
# Las medidas son varchar y pueden traer texto: cada una pasa por el REGEXP de
# Terceros antes de convertir, y lo que no es un número cuenta 0.
#
# El rango es semiabierto y sin DATE() en el filtro, para que pueda usar un
# índice de la fecha: fecha >= :desde AND fecha < :hasta_exclusivo. Un parte
# con hora (las 03:00) del último día queda adentro.
#
# El supervisor sale con el mismo join de cada rama de QUERY_PRINCIPAL, y
# "dónde" es el nombre de la finca del parte.


def _medida(campo: str) -> str:
    """El cast de Terceros: el número del varchar, o 0 si no lo es."""
    return (f"CASE WHEN TRIM({campo}) REGEXP '^[0-9]*[.]?[0-9]+$' "
            f"THEN CAST(TRIM({campo}) AS DECIMAL(12,2)) ELSE 0 END")


def _partes_del_campo(filtro_cliente: bool) -> str:
    """La consulta base: una fila por (parte, tarea) con sus cuatro medidas.
    Con filtro_cliente, cada rama filtra por :cliente_id."""
    cliente = {
        rama: f"AND {rama}.cliente = :cliente_id" if filtro_cliente else ""
        for rama in ("pdpulve", "pdmaquinarias", "pdtareas")
    }
    return f"""
  SELECT pdpulve.fecha AS fecha,
         pdpulve.cliente AS cliente_id,
         pdpulve.tarea AS tarea_id,
         MAX(fincas.nombre) AS donde,
         MAX(supervisor.name) AS supervisor,
         SUM({_medida("pregistros.hsjornal1")}) AS horas_jornal,
         SUM({_medida("pregistros.hsmaquina1")}) AS horas_maquina,
         MAX({_medida("pdpulve.unidades")}) AS unidades,
         SUM({_medida("pregistros.trancadas1")}) AS tancadas
  FROM laa_pdpulverizadas pdpulve
  INNER JOIN laa_pdpulverizadasregistros pregistros ON pregistros.parent_id = pdpulve.id AND pregistros.estado <> 9
  LEFT JOIN laa_fincas fincas ON fincas.id = pdpulve.finca
  LEFT JOIN ast_users supervisor ON supervisor.id = pdpulve.supervisor
  WHERE pdpulve.estado <> 9
    AND pdpulve.fecha >= :desde AND pdpulve.fecha < :hasta_exclusivo
    {cliente["pdpulve"]}
  GROUP BY pdpulve.id, pdpulve.fecha, pdpulve.cliente, pdpulve.tarea

  UNION ALL

  SELECT pdmaquinarias.fecha AS fecha,
         pdmaquinarias.cliente AS cliente_id,
         mregistros.tarea AS tarea_id,
         MAX(fincas.nombre) AS donde,
         MAX(usuario_supervisor.name) AS supervisor,
         SUM({_medida("mregistros.hsjornal")}) AS horas_jornal,
         SUM({_medida("mregistros.hsmaquina")}) AS horas_maquina,
         SUM({_medida("mregistros.unidades")}) AS unidades,
         0 AS tancadas
  FROM laa_pdmaquinarias pdmaquinarias
  INNER JOIN laa_pdmaquinariasregistros mregistros ON mregistros.parent_id = pdmaquinarias.id AND mregistros.estado <> 9
  LEFT JOIN laa_fincas fincas ON pdmaquinarias.finca = fincas.id
  LEFT JOIN laa_supervisores supervisores ON pdmaquinarias.supervisor = supervisores.idusuario
  LEFT JOIN ast_users usuario_supervisor ON supervisores.idusuario = usuario_supervisor.id
  WHERE pdmaquinarias.estado <> 9
    AND pdmaquinarias.fecha >= :desde AND pdmaquinarias.fecha < :hasta_exclusivo
    {cliente["pdmaquinarias"]}
  GROUP BY pdmaquinarias.id, mregistros.tarea, pdmaquinarias.fecha, pdmaquinarias.cliente

  UNION ALL

  SELECT pdtareas.fecha AS fecha,
         pdtareas.cliente AS cliente_id,
         tregistros.tarea AS tarea_id,
         MAX(fincas.nombre) AS donde,
         MAX(usuario_supervisor.name) AS supervisor,
         SUM({_medida("tregistros.hsjornal")}) AS horas_jornal,
         0 AS horas_maquina,
         SUM({_medida("tregistros.unidades")}) AS unidades,
         0 AS tancadas
  FROM laa_pdtareasmanuales pdtareas
  INNER JOIN laa_pdtareasmanualesregistros tregistros ON tregistros.parent_id = pdtareas.id AND tregistros.estado <> 9
  LEFT JOIN laa_fincas fincas ON fincas.id = pdtareas.finca
  LEFT JOIN laa_supervisores supervisores ON supervisores.idusuario = pdtareas.supervisor
  LEFT JOIN ast_users usuario_supervisor ON usuario_supervisor.id = supervisores.idusuario
  WHERE pdtareas.estado <> 9
    AND pdtareas.fecha >= :desde AND pdtareas.fecha < :hasta_exclusivo
    {cliente["pdtareas"]}
  GROUP BY pdtareas.id, tregistros.tarea, pdtareas.fecha, pdtareas.cliente
"""


# Lo trabajado del Resumen: por cliente, tarea y mes, con las sumas y la
# cantidad de partes. Agrupa en la base: en 12 meses los partes son decenas de
# miles de filas.
QUERY_TRABAJADO_POR_MES = text(f"""
SELECT p.cliente_id, p.tarea_id,
       YEAR(p.fecha) AS anio, MONTH(p.fecha) AS mes,
       SUM(p.horas_jornal) AS horas_jornal,
       SUM(p.horas_maquina) AS horas_maquina,
       SUM(p.unidades) AS unidades,
       SUM(p.tancadas) AS tancadas,
       COUNT(*) AS partes
FROM ({_partes_del_campo(filtro_cliente=False)}) AS p
GROUP BY p.cliente_id, p.tarea_id, YEAR(p.fecha), MONTH(p.fecha)
ORDER BY anio, mes, p.cliente_id, p.tarea_id
""")

# Los partes de un cliente, uno por fila, para el Detalle y la Precarga: suman
# en Python, así el panel de partes da igual que la columna.
QUERY_PARTES_DE_CLIENTE = text(f"""
SELECT p.fecha, p.tarea_id, p.donde, p.supervisor,
       p.horas_jornal, p.horas_maquina, p.unidades, p.tancadas
FROM ({_partes_del_campo(filtro_cliente=True)}) AS p
ORDER BY p.fecha, p.tarea_id
""")


# Caché de proceso de clientes, fincas por cliente y empresas, como la de
# empresas de Preliquidación: cambian casi nunca y la base de campo es lenta.
# La clave distingue cada lectura (y el cliente, en las fincas). Un error no
# se guarda: la próxima llamada vuelve a consultar.
_CACHE_TTL = 600  # segundos
_CACHE: dict = {}


def _reloj() -> float:
    """El reloj de la caché; los tests lo reemplazan."""
    return time.monotonic()


# Las claves de la caché que son del Cruce (su primer elemento): las borra
# invalidar_cache_cruce(), sin tocar clientes, fincas ni empresas.
_CLAVES_CRUCE = ("trabajado", "partes", "tareas_cruce")


def invalidar_cache():
    _CACHE.clear()


def invalidar_cache_cruce():
    """Borra de la caché sólo las lecturas del Cruce (el "Volver a leer")."""
    for clave in [c for c in _CACHE if c[0] in _CLAVES_CRUCE]:
        del _CACHE[clave]


def _cacheado(clave, leer):
    guardado = _CACHE.get(clave)
    if guardado is not None and guardado[0] > _reloj():
        return guardado[1]
    datos = leer()
    _CACHE[clave] = (_reloj() + _CACHE_TTL, datos)
    return datos


def _leida(filas: list) -> dict:
    """Una lectura del Cruce con su hora (UTC), que se guarda con ella en la
    caché: una llamada que sale de la caché devuelve la hora de la lectura."""
    return {"leido_en": ahora_utc(), "filas": filas}


def _numero(valor) -> Decimal:
    """Una medida del campo como Decimal; un NULL es 0."""
    return Decimal(0) if valor is None else Decimal(str(valor))


def _dia(valor) -> date:
    """La fecha de un parte, sin la hora con que la guarda el campo."""
    return valor.date() if isinstance(valor, datetime) else valor


def normalizar_nombre(nombre) -> str:
    """El nombre de una tarea listo para comparar: sin espacios en los bordes,
    con los espacios internos colapsados y en mayúsculas.

    Es como tarea_canonica de Preliquidación, con dos diferencias: colapsa los
    espacios internos (los nombres pueden traer dobles espacios) y no aplica el
    alias de pago de ADR-0012, porque la Unidad sugerida es de cada tarea del
    campo y no de cómo se le paga a quien la hizo. Hoy no la llama nadie: la
    conserva la E2."""
    return " ".join((nombre or "").split()).upper()


class ConsultaExternaService:

    def __init__(self, db_externa: Session, db_sueldos: Session | None = None):
        """La sesión de sueldos es opcional: sólo la usa empresas(), y así
        quien lee sólo el campo (las tareas) no abre otra conexión."""
        self.db = db_externa
        self.db_sueldos = db_sueldos

    def _ejecutar(self, query, params=None, db=None):
        """Todas las consultas pasan por acá: si venció el read_timeout o el
        servidor no está, pymysql levanta OperationalError y el núcleo lo
        traduce a ExternaNoDisponible, que main.py convierte en 503 con un
        mensaje que la persona entienda. Por defecto va al campo; empresas()
        pasa la sesión de sueldos."""
        with traducir_errores_externa():
            return (db or self.db).execute(query, params or {}).fetchall()

    def clientes(self, incluir_baja: bool = False) -> list[dict]:
        """Los clientes del campo por nombre, cada uno con {id, nombre,
        activo}. Sólo los activos, salvo con incluir_baja (el histórico), que
        trae también los de baja con activo=False. Con caché de 10 minutos."""
        if incluir_baja:
            return _cacheado(("clientes", True), lambda: [
                {"id": id_, "nombre": nombre, "activo": bool(activo)}
                for id_, nombre, activo in self._ejecutar(QUERY_CLIENTES_CON_BAJA)
            ])
        return _cacheado(("clientes", False), lambda: [
            {"id": id_, "nombre": nombre, "activo": True}
            for id_, nombre in self._ejecutar(QUERY_CLIENTES)
        ])

    def fincas_de_cliente(self, cliente_id: int) -> list[dict]:
        """Las fincas activas de un cliente, {id, nombre}, por nombre. Con
        caché de 10 minutos por cliente."""
        return _cacheado(("fincas", cliente_id), lambda: [
            {"id": id_, "nombre": nombre}
            for id_, nombre in self._ejecutar(
                QUERY_FINCAS_DE_CLIENTE, {"cliente_id": cliente_id})
        ])

    def todas_las_fincas(self) -> list[dict]:
        """Todas las fincas activas, {id, nombre, cliente_id}, para el script
        del histórico. Sin caché: el script la lee una vez por corrida."""
        return [
            {"id": id_, "nombre": nombre, "cliente_id": cliente_id}
            for id_, nombre, cliente_id in self._ejecutar(QUERY_TODAS_LAS_FINCAS)
        ]

    def empresas(self) -> list[str]:
        """Las Empresas emisoras, de la base de sueldos: recortadas, sin
        vacías ni repetidas, ordenadas. Con caché de 10 minutos."""
        if self.db_sueldos is None:
            raise RuntimeError(
                "ConsultaExternaService.empresas() necesita la sesión de sueldos")
        return _cacheado(("empresas",), lambda: sorted({
            empresa.strip()
            for (empresa,) in self._ejecutar(QUERY_EMPRESAS, db=self.db_sueldos)
            if empresa and empresa.strip()
        }))

    def obtener_tareas(self, incluir_baja: bool = False) -> list[dict]:
        """Las tareas del campo, en el orden del campo (por nombre), cada una
        con {tarea_id, nombre, grupo_tarea, unidad_sugerida, no_facturable}.
        Sólo las activas, salvo con incluir_baja (el histórico), que trae
        también las dadas de baja, armadas igual.

        La descripción se corta por ";". Sin grupo es siempre None (vacía,
        NULL o sólo espacios). La unidad es el tercer segmento, y sólo si hay
        tres o más: con dos, el segundo es el grupo de pago. traducir_unidad
        da la clave, la marca No facturable, o Sin definir (None, False). Sólo
        van los valores traducidos, sin el texto crudo."""
        filas = self._ejecutar(QUERY_TAREAS_CON_BAJA if incluir_baja else QUERY_TAREAS)
        tareas = []
        for tarea_id, nombre, descripcion in filas:
            partes = (descripcion or "").split(";")
            texto_unidad = partes[2] if len(partes) >= 3 else ""
            unidad_sugerida, no_facturable = traducir_unidad(texto_unidad)
            tareas.append({
                "tarea_id": tarea_id,
                "nombre": nombre,
                "grupo_tarea": partes[0].strip() or None,
                "unidad_sugerida": unidad_sugerida,
                "no_facturable": no_facturable,
            })
        return tareas

    # ─── El Cruce (plan de la E3, decisión 6) ──────────────────────────────
    # Las tres lecturas devuelven {leido_en, filas} y van con caché de 10
    # minutos; invalidar_cache_cruce() las borra.

    def trabajado_por_mes(self, desde: date, hasta: date) -> dict:
        """Lo trabajado por cliente, tarea y mes, entre el mes de desde y el
        de hasta (los dos incluidos). Cada fila: {cliente_id, tarea_id, mes
        (día 1), horas_jornal, horas_maquina, unidades, tancadas, partes}."""
        desde = desde.replace(day=1)
        hasta_exclusivo = mes_siguiente(hasta)

        def leer():
            filas = self._ejecutar(QUERY_TRABAJADO_POR_MES, {
                "desde": desde, "hasta_exclusivo": hasta_exclusivo})
            return _leida([
                {"cliente_id": cliente_id, "tarea_id": tarea_id,
                 "mes": date(anio, mes, 1),
                 "horas_jornal": _numero(jornal), "horas_maquina": _numero(maquina),
                 "unidades": _numero(unidades), "tancadas": _numero(tancadas),
                 "partes": partes}
                for (cliente_id, tarea_id, anio, mes, jornal, maquina, unidades,
                     tancadas, partes) in filas
            ])

        return _cacheado(("trabajado", desde, hasta_exclusivo), leer)

    def partes_de_cliente(self, cliente_id: int, desde: date, hasta: date) -> dict:
        """Los partes de un cliente entre desde y hasta (días, los dos
        incluidos), uno por (parte, tarea). Cada fila: {fecha, tarea_id,
        donde, supervisor, horas_jornal, horas_maquina, unidades, tancadas}."""
        hasta_exclusivo = hasta + timedelta(days=1)

        def leer():
            filas = self._ejecutar(QUERY_PARTES_DE_CLIENTE, {
                "cliente_id": cliente_id, "desde": desde,
                "hasta_exclusivo": hasta_exclusivo})
            return _leida([
                {"fecha": _dia(fecha), "tarea_id": tarea_id, "donde": donde,
                 "supervisor": supervisor,
                 "horas_jornal": _numero(jornal), "horas_maquina": _numero(maquina),
                 "unidades": _numero(unidades), "tancadas": _numero(tancadas)}
                for (fecha, tarea_id, donde, supervisor, jornal, maquina, unidades,
                     tancadas) in filas
            ])

        return _cacheado(("partes", cliente_id, desde, hasta_exclusivo), leer)

    def tareas_cruce(self) -> dict:
        """El maestro de tareas con las bajas, para el Cruce, con caché.
        obtener_tareas sigue sin caché: la validación del alta de la E2 no
        cambia."""
        return _cacheado(("tareas_cruce",),
                         lambda: _leida(self.obtener_tareas(incluir_baja=True)))
