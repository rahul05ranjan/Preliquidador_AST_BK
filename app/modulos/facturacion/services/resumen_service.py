"""El Resumen de Facturación y su configuración (plan de la E3, decisiones 4
y 6, rutas 13 y 17).

El Resumen es una fila por Cliente y mes, con lo trabajado, lo facturado y el
Estado del mes. Lo trabajado y el maestro de tareas salen del campo, con la
caché de consulta_externa; lo facturado, los Adjuntos, las Revisiones y la
configuración se leen siempre frescos de la base propia. El Cruce lo hace el
motor puro (cruce.py): acá se lee, se valida y se arma la respuesta.

La consulta del campo se recibe por parámetro, como en ComprobantesService,
para que los tests usen una falsa. Los valores salen como Decimal y date: el
texto del contrato lo da el schema del router.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.models import Usuario, ahora_utc
from app.modulos.facturacion import fechas
from app.modulos.facturacion.config import (
    MES_CORTE_INICIAL, MESES_MAXIMOS, UMBRAL_INICIAL,
)
from app.modulos.facturacion.models import (
    Adjunto, Comprobante, Configuracion, LineaComprobante, RevisionDiferencia,
)
from app.modulos.facturacion.services.consulta_externa import invalidar_cache_cruce
from app.modulos.facturacion.services.cruce import (
    ESTADOS, UNIDADES_CRUCE, CruceMes, LineaFacturada, cruzar, tareas_sin_unidad,
)

# La única fila de facturacion_configuracion.
ID_CONFIGURACION = 1
# Hasta 100 %, con dos decimales como la columna, DECIMAL(5,2).
UMBRAL_MAXIMO = Decimal("100")
_CENTESIMOS = Decimal("0.01")


# ─── Excepciones ────────────────────────────────────────────────────────────
# Las traduce el router a 422 con `detail` {tipo, mensaje, campo}. El mensaje
# lo lee una persona.

class ErrorResumen(Exception):
    mensaje = "No se pudo armar el Resumen."

    def __init__(self, mensaje: str | None = None):
        if mensaje:
            self.mensaje = mensaje
        super().__init__(self.mensaje)


class MesInvalido(ErrorResumen):
    """422 `mes_invalido`: un mes que no viene como AAAA-MM."""

    def __init__(self, campo: str):
        self.campo = campo
        super().__init__("El mes va como AAAA-MM, por ejemplo 2026-09.")


class RangoInvalido(ErrorResumen):
    """422 `rango_invalido`, con el campo que hay que mover."""

    def __init__(self, campo: str, mensaje: str):
        self.campo = campo
        super().__init__(mensaje)


class ConfiguracionInvalida(ErrorResumen):
    """422 `configuracion_invalida`, con el campo que falla."""

    def __init__(self, campo: str, mensaje: str):
        self.campo = campo
        super().__init__(mensaje)


# ─── Lecturas de la base propia, siempre frescas ────────────────────────────
# Funciones sueltas y no métodos: las usan también el Detalle y el script de
# aceptación, que no tienen por qué armar el servicio entero.

def leer_lineas(db: Session, desde: date, hasta: date,
                cliente_id: int | None = None) -> list[LineaFacturada]:
    """Lo facturado entre el mes de desde y el de hasta (los dos incluidos),
    por la fecha de cada Línea: una LineaFacturada por Línea, con lo de su
    Comprobante y su cantidad de Adjuntos. Sin filtrar: qué cuenta lo decide
    el motor. Con cliente_id, sólo las de ese Cliente."""
    por_adjuntos = (
        select(Adjunto.comprobante_id.label("comprobante_id"),
               func.count(Adjunto.id).label("cantidad"))
        .group_by(Adjunto.comprobante_id)
        .subquery())
    consulta = (
        select(Comprobante.id, Comprobante.tipo, Comprobante.numero,
               Comprobante.es_historico, Comprobante.pendiente_de_facturar,
               por_adjuntos.c.cantidad, Comprobante.cliente_id,
               LineaComprobante.fecha, LineaComprobante.tarea_id,
               LineaComprobante.tarea_nombre, LineaComprobante.unidad,
               LineaComprobante.cantidad, LineaComprobante.importe)
        .join(LineaComprobante, LineaComprobante.comprobante_id == Comprobante.id)
        .outerjoin(por_adjuntos, por_adjuntos.c.comprobante_id == Comprobante.id)
        # Semiabierto, como el campo: usa ix_facturacion_linea_tarea_fecha
        # sin cuentas sobre la columna.
        .where(LineaComprobante.fecha >= desde.replace(day=1),
               LineaComprobante.fecha < fechas.mes_siguiente(hasta))
        .order_by(LineaComprobante.fecha, Comprobante.id, LineaComprobante.orden))
    if cliente_id is not None:
        consulta = consulta.where(Comprobante.cliente_id == cliente_id)
    return [
        LineaFacturada(
            comprobante_id=comprobante_id, tipo=tipo, numero=numero,
            es_historico=bool(es_historico),
            pendiente_de_facturar=bool(pendiente_de_facturar),
            cantidad_adjuntos=adjuntos or 0, cliente_id=cliente,
            fecha=fecha, tarea_id=tarea_id, tarea_nombre=tarea_nombre,
            unidad=unidad, cantidad=cantidad, importe=importe)
        for (comprobante_id, tipo, numero, es_historico, pendiente_de_facturar,
             adjuntos, cliente, fecha, tarea_id, tarea_nombre, unidad, cantidad,
             importe) in db.execute(consulta).all()
    ]


def revisiones_vigentes(db: Session, desde: date, hasta: date,
                        cliente_id: int | None = None) -> dict:
    """La Revisión vigente de cada (Cliente, mes) entre el mes de desde y el
    de hasta: {(cliente_id, mes): RevisionDiferencia}, con sus tareas. La
    vigente es la más reciente que nadie deshizo; una deshecha no tapa a una
    anterior."""
    consulta = (
        select(RevisionDiferencia)
        .options(selectinload(RevisionDiferencia.tareas))
        .where(RevisionDiferencia.deshecha_en.is_(None),
               RevisionDiferencia.mes >= desde.replace(day=1),
               RevisionDiferencia.mes <= hasta.replace(day=1))
        .order_by(RevisionDiferencia.creada_en.desc(), RevisionDiferencia.id.desc()))
    if cliente_id is not None:
        consulta = consulta.where(RevisionDiferencia.cliente_id == cliente_id)
    vigentes: dict = {}
    for revision in db.scalars(consulta):
        vigentes.setdefault((revision.cliente_id, revision.mes), revision)
    return vigentes


def revisadas(vigentes: dict) -> dict:
    """Las (tarea_id, unidad) de cada Revisión vigente, como las pide
    cruce.cruzar en `revisiones`."""
    return {clave: {(t.tarea_id, t.unidad) for t in revision.tareas}
            for clave, revision in vigentes.items()}


def se_muestra(cruce: CruceMes) -> bool:
    """Si el (Cliente, mes) va en el Resumen. Un Cliente sin trabajo ni
    Comprobantes no aparece (paso A6): cuenta sólo lo que entra en el Cruce.
    Un mes que sólo tiene Líneas que no cuentan (un histórico pendiente de
    facturar, cosecha o No facturable) o sólo trabajo No facturable no tiene
    nada que cruzar: mostrarlo daría una fila en cero marcada Facturada."""
    return bool(cruce.filas or cruce.lineas)


def _leer_mes(texto, campo: str) -> date:
    try:
        return fechas.leer_mes(texto)
    except ValueError:
        raise MesInvalido(campo) from None


def mes_en_curso() -> date:
    return fechas.hoy().replace(day=1)


class ResumenService:

    def __init__(self, db: Session, consulta):
        """`consulta` es la ConsultaExternaService del módulo (o una falsa):
        trabajado_por_mes, tareas_cruce y clientes."""
        self.db = db
        self.consulta = consulta

    # ─── Configuración (decisión 4, ruta 17) ────────────────────────────────

    def configuracion(self) -> dict:
        """El Umbral y el Mes de corte vigentes, con quién y cuándo los cambió.
        Sin fila, los valores iniciales de config.py, sin quién ni cuándo."""
        fila = self.db.get(Configuracion, ID_CONFIGURACION)
        if fila is None:
            return {"umbral_pct": UMBRAL_INICIAL, "mes_corte": MES_CORTE_INICIAL,
                    "actualizado_en": None, "actualizado_por_nombre": None}
        persona = (self.db.get(Usuario, fila.actualizado_por)
                   if fila.actualizado_por is not None else None)
        return {"umbral_pct": fila.umbral_pct, "mes_corte": fila.mes_corte,
                "actualizado_en": fila.actualizado_en,
                "actualizado_por_nombre": persona.nombre if persona else None}

    def cambiar_configuracion(self, umbral_pct, mes_corte: str,
                              usuario_id: int | None) -> dict:
        """Guarda el Umbral (mayor que 0 y hasta 100, con dos decimales como
        máximo) y el Mes de corte ("AAAA-MM", no posterior al mes en curso).
        El primer cambio crea la fila. Devuelve lo de configuracion()."""
        umbral = _leer_umbral(umbral_pct)
        try:
            corte = fechas.leer_mes(mes_corte)
        except ValueError:
            raise ConfiguracionInvalida(
                "mes_corte", "El Mes de corte va como AAAA-MM, por ejemplo 2026-10.") from None
        if corte > mes_en_curso():
            raise ConfiguracionInvalida(
                "mes_corte", "El Mes de corte no puede ser posterior al mes en curso.")

        fila = self.db.get(Configuracion, ID_CONFIGURACION)
        if fila is None:
            fila = Configuracion(id=ID_CONFIGURACION)
            self.db.add(fila)
        fila.umbral_pct = umbral
        fila.mes_corte = corte
        fila.actualizado_en = ahora_utc()
        fila.actualizado_por = usuario_id
        self.db.commit()
        return self.configuracion()

    # ─── Resumen (ruta 13) ──────────────────────────────────────────────────

    def resumen(self, desde: str, hasta: str, refrescar: bool = False) -> dict:
        """El Resumen de los meses de desde a hasta ("AAAA-MM", los dos
        incluidos): {umbral_pct, mes_corte, mes_en_curso, leido_en, filas,
        tareas_sin_unidad}.

        El rango se valida antes de leer el campo. Con refrescar, la caché del
        Cruce se vacía antes de leer ("Volver a leer"). `leido_en` es la más
        vieja de las dos lecturas del campo (lo trabajado y el maestro): la
        pantalla no muestra nada más nuevo que eso."""
        inicio = _leer_mes(desde, "desde")
        fin = _leer_mes(hasta, "hasta")
        en_curso = mes_en_curso()
        _validar_rango(inicio, fin, en_curso)

        if refrescar:
            invalidar_cache_cruce()
        configuracion = self.configuracion()
        trabajado = self.consulta.trabajado_por_mes(inicio, fin)
        tareas = self.consulta.tareas_cruce()

        cruces = cruzar(
            trabajado["filas"], leer_lineas(self.db, inicio, fin), tareas["filas"],
            umbral_pct=configuracion["umbral_pct"],
            mes_corte=configuracion["mes_corte"], mes_en_curso=en_curso,
            revisiones=revisadas(revisiones_vigentes(self.db, inicio, fin)))
        visibles = [c for c in cruces if se_muestra(c)]
        nombres = self.nombres_de_clientes({c.cliente_id for c in visibles})

        filas = [_fila(c, nombres.get(c.cliente_id)) for c in visibles]
        filas.sort(key=lambda f: (-f["mes"].toordinal(),
                                  ESTADOS.index(f["estados"][0]),
                                  f["cliente_nombre"] or "", f["cliente_id"]))
        return {
            "umbral_pct": configuracion["umbral_pct"],
            "mes_corte": configuracion["mes_corte"],
            "mes_en_curso": en_curso,
            "leido_en": min(trabajado["leido_en"], tareas["leido_en"]),
            "filas": filas,
            "tareas_sin_unidad": tareas_sin_unidad(visibles),
        }

    def nombres_de_clientes(self, cliente_ids: set) -> dict:
        """{cliente_id: nombre}: del maestro del campo, con las bajas; si el
        Cliente no está ahí, la copia de su Comprobante más nuevo. Un Cliente
        que no está en ninguno de los dos no figura (None en la fila)."""
        if not cliente_ids:
            return {}
        nombres = {c["id"]: c["nombre"]
                   for c in self.consulta.clientes(incluir_baja=True)
                   if c["id"] in cliente_ids}
        faltan = cliente_ids - set(nombres)
        if faltan:
            copias = self.db.execute(
                select(Comprobante.cliente_id, Comprobante.cliente_nombre)
                .where(Comprobante.cliente_id.in_(faltan))
                .order_by(Comprobante.id.desc())).all()
            for cliente_id, nombre in copias:
                nombres.setdefault(cliente_id, nombre)
        return nombres


def _leer_umbral(valor) -> Decimal:
    mensaje = "El Umbral tiene que ser mayor que 0 y hasta 100, con dos decimales como máximo."
    try:
        umbral = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError):
        raise ConfiguracionInvalida("umbral_pct", mensaje) from None
    if (not umbral.is_finite() or not 0 < umbral <= UMBRAL_MAXIMO
            or umbral != umbral.quantize(_CENTESIMOS)):
        raise ConfiguracionInvalida("umbral_pct", mensaje)
    return umbral


def _validar_rango(desde: date, hasta: date, en_curso: date) -> None:
    """Hasta MESES_MAXIMOS meses, desde no posterior a hasta, y sin pasar el
    mes en curso. Va antes de fechas.meses(), que con el rango invertido
    devuelve vacío sin avisar."""
    if hasta < desde:
        raise RangoInvalido("hasta", "El mes final no puede ser anterior al inicial.")
    if len(fechas.meses(desde, hasta)) > MESES_MAXIMOS:
        raise RangoInvalido(
            "desde", f"El Resumen muestra hasta {MESES_MAXIMOS} meses de una vez.")
    if hasta > en_curso:
        raise RangoInvalido("hasta", "El mes final no puede pasar del mes en curso.")


def _fila(cruce: CruceMes, cliente_nombre: str | None) -> dict:
    """Una fila del Resumen (ruta 13): las cinco columnas del campo, el neto
    facturado (con signo) y el Estado del mes."""
    return {
        "cliente_id": cruce.cliente_id,
        "cliente_nombre": cliente_nombre,
        "mes": cruce.mes,
        **{unidad: cruce.columnas[unidad] for unidad in UNIDADES_CRUCE},
        "facturado_neto": cruce.facturado_neto,
        "estados": list(cruce.estados),
        "diferencia_revisada": cruce.diferencia_revisada,
        "comprobantes_sin_adjunto": list(cruce.comprobantes_sin_adjunto),
    }
