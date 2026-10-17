"""El Resumen de Facturación, el Detalle, la Revisión de diferencia y la
configuración (plan de la E3, decisiones 4 y 6, rutas 13 a 17).

El Resumen es una fila por Cliente y mes, con sus líneas (grupo de tareas,
unidad) y el Estado del mes. Lo trabajado y el maestro de tareas salen del campo, con la
caché de consulta_externa; lo facturado, los Adjuntos, las Revisiones y la
configuración se leen siempre frescos de la base propia. El Cruce lo hace el
motor puro (cruce.py): acá se lee, se valida y se arma la respuesta. El
Detalle pasa por el mismo motor con los partes del Cliente, así da los mismos
estados que el Resumen para el mismo mes; la Revisión guarda las (grupo,
unidad) que superaban con esos mismos datos. Hasta el filtro por día (Ticket 4
de la spec de la E3a por grupo), el período de una Revisión es siempre el mes
entero: se guarda así y sólo se leen las de ese período.

La consulta del campo se recibe por parámetro, como en ComprobantesService,
para que los tests usen una falsa. Los valores salen como Decimal y date: el
texto del contrato lo da el schema del router.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.models import Usuario, ahora_utc
from app.modulos.facturacion import fechas
from app.modulos.facturacion.config import (
    LARGO_COMENTARIO, MES_CORTE_INICIAL, MESES_MAXIMOS, UMBRAL_INICIAL,
)
from app.modulos.facturacion.models import (
    Adjunto, Comprobante, Configuracion, LineaComprobante, RevisionDiferencia,
    RevisionGrupo,
)
from app.modulos.facturacion.services.consulta_externa import invalidar_cache_cruce
from app.modulos.facturacion.services.cruce import (
    ANTES_DEL_CORTE, CERO, CON_DIFERENCIA, ESTADOS, MES_EN_CURSO,
    PENDIENTE_DE_FACTURAR, UNIDADES, CruceMes, FilaCruce, FilaGrupo,
    LineaFacturada, cantidad_en_unidad, cruzar, cruzar_mes, medidas_por_tarea,
    tareas_sin_unidad,
)
from app.modulos.facturacion.services.precios import precios_sugeridos
from app.modulos.facturacion.services.reglas_comprobante import FACTURA

# La única fila de facturacion_configuracion.
ID_CONFIGURACION = 1
# Hasta 100 %, con dos decimales como la columna, DECIMAL(5,2).
UMBRAL_MAXIMO = Decimal("100")
_CENTESIMOS = Decimal("0.01")
# El precio medio del mes, con los decimales de precio_unitario, NUMERIC(14,4).
_DIEZMILESIMOS = Decimal("0.0001")
# El grupo de las tareas sin grupo en el maestro (o que no están en él).
SIN_GRUPO = "Sin grupo"


# ─── Excepciones ────────────────────────────────────────────────────────────
# Las traduce el router: a 422 con `detail` {tipo, mensaje, campo}, a 409 con
# {tipo, mensaje} y a 404 con texto. El mensaje lo lee una persona.

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


class ClienteNoEncontrado(ErrorResumen):
    """404 del Detalle: el Cliente no está en el maestro (con las bajas) y no
    tiene ningún Comprobante."""
    mensaje = "No existe ese Cliente."


class ConfiguracionInvalida(ErrorResumen):
    """422 `configuracion_invalida`, con el campo que falla."""

    def __init__(self, campo: str, mensaje: str):
        self.campo = campo
        super().__init__(mensaje)


class RevisionInvalida(ErrorResumen):
    """422 `revision_invalida`, campo `comentario`: vacío o de más de
    LARGO_COMENTARIO caracteres, contados sin los espacios de los bordes."""

    def __init__(self, mensaje: str):
        self.campo = "comentario"
        super().__init__(mensaje)


class NoRevisable(ErrorResumen):
    """409 `no_revisable`: el mes no está Con diferencia. El mensaje dice por
    qué, según el estado."""


class SinRevision(ErrorResumen):
    """409 `sin_revision`: el mes no tiene una Revisión vigente que deshacer."""
    mensaje = "Este mes no tiene una Revisión para deshacer."


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
    de hasta: {(cliente_id, mes): RevisionDiferencia}, con sus grupos. La
    vigente es la más reciente que nadie deshizo, entre las del mes entero
    (las de otro período no cubren el mes, decisión 5 de la spec); una
    deshecha no tapa a una anterior."""
    consulta = (
        select(RevisionDiferencia)
        .options(selectinload(RevisionDiferencia.grupos))
        .where(RevisionDiferencia.deshecha_en.is_(None),
               RevisionDiferencia.mes >= desde.replace(day=1),
               RevisionDiferencia.mes <= hasta.replace(day=1))
        .order_by(RevisionDiferencia.creada_en.desc(), RevisionDiferencia.id.desc()))
    if cliente_id is not None:
        consulta = consulta.where(RevisionDiferencia.cliente_id == cliente_id)
    vigentes: dict = {}
    for revision in db.scalars(consulta):
        if (revision.desde, revision.hasta) == (revision.mes,
                                                fechas.fin_de_mes(revision.mes)):
            vigentes.setdefault((revision.cliente_id, revision.mes), revision)
    return vigentes


def grupos_revisados(revision: RevisionDiferencia) -> set:
    """Las (grupo, unidad) de una Revisión, como las pide el motor."""
    return {(g.grupo, g.unidad) for g in revision.grupos}


def revisadas(vigentes: dict) -> dict:
    """Las (grupo, unidad) de cada Revisión vigente, como las pide
    cruce.cruzar en `revisiones`."""
    return {clave: grupos_revisados(revision) for clave, revision in vigentes.items()}


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
        tareas_sin_unidad, actualizado_en, actualizado_por_nombre}.

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
            "actualizado_en": configuracion["actualizado_en"],
            "actualizado_por_nombre": configuracion["actualizado_por_nombre"],
        }

    # ─── Detalle (ruta 14) ──────────────────────────────────────────────────

    def detalle(self, cliente_id: int, mes: str, refrescar: bool = False) -> dict:
        """El Detalle de un Cliente en un mes ("AAAA-MM"): el Cruce tarea por
        tarea con sus partes, los pesos, los Comprobantes del mes y la
        Revisión vigente (ruta 14).

        El mes se valida antes de leer nada, y el 404 (un Cliente que no está
        en el maestro, con las bajas, ni tiene ningún Comprobante) se decide
        antes de leer los partes. Con refrescar, la caché del Cruce se vacía
        antes de leer. `leido_en` es la más vieja de las dos lecturas del
        campo, como en el Resumen."""
        inicio = _leer_mes(mes, "mes")
        if refrescar:
            invalidar_cache_cruce()
        nombres = self.nombres_de_clientes({cliente_id})
        if cliente_id not in nombres:
            raise ClienteNoEncontrado()

        datos = self.datos_del_mes(cliente_id, inicio)
        cruce = datos.cruce
        precios = _precios(cruce, precios_sugeridos(self.db, cliente_id))
        configuracion = datos.configuracion
        return {
            "cliente_id": cliente_id,
            "cliente_nombre": nombres[cliente_id],
            "mes": inicio,
            "umbral_pct": configuracion["umbral_pct"],
            "mes_corte": configuracion["mes_corte"],
            "leido_en": datos.leido_en,
            "estados": list(cruce.estados),
            "diferencia_revisada": cruce.diferencia_revisada,
            "se_puede_revisar": CON_DIFERENCIA in cruce.estados,
            "comprobantes": _comprobantes(datos.lineas),
            "grupos": _grupos(cruce, datos.partes, precios),
            "total": _total(cruce, precios),
            "revision": self._revision(datos.vigente),
        }

    def datos_del_mes(self, cliente_id: int, mes: date) -> "DatosDelMes":
        """Lee el campo y la base propia de un Cliente en un mes y los pasa
        por el motor, igual que el Resumen: los partes del mes (con caché),
        el maestro de tareas (con caché), lo facturado y la Revisión vigente
        (frescos). Lo usan el Detalle y la Revisión, que así ven el mismo
        Cruce."""
        configuracion = self.configuracion()
        partes = self.consulta.partes_de_cliente(cliente_id, mes, fechas.fin_de_mes(mes))
        tareas = self.consulta.tareas_cruce()
        lineas = leer_lineas(self.db, mes, mes, cliente_id)
        vigente = revisiones_vigentes(self.db, mes, mes, cliente_id).get((cliente_id, mes))
        cruce = cruzar_mes(
            cliente_id=cliente_id, mes=mes,
            trabajado=medidas_por_tarea(partes["filas"]),
            lineas=lineas, tareas=tareas["filas"],
            umbral_pct=configuracion["umbral_pct"],
            mes_corte=configuracion["mes_corte"], mes_en_curso=mes_en_curso(),
            revisadas=None if vigente is None else grupos_revisados(vigente))

        return DatosDelMes(
            configuracion=configuracion,
            leido_en=min(partes["leido_en"], tareas["leido_en"]),
            partes=partes["filas"],
            lineas=lineas,
            vigente=vigente,
            cruce=cruce,
        )

    # ─── Revisión de diferencia (rutas 15 y 16) ─────────────────────────────

    def revisar(self, cliente_id: int, mes: str, comentario: str | None,
                usuario_id: int | None) -> dict:
        """Deja una Revisión de diferencia en un Cliente y mes ("AAAA-MM") y
        devuelve el Detalle (ruta 15).

        El comentario se recorta en los bordes antes de medirlo, como en el
        front, y se guarda recortado. Sólo se revisa un mes Con diferencia;
        cualquier otro da NoRevisable. Guarda quién, cuándo, el período (el
        mes entero) y las (grupo, unidad) que superaban, calculadas con
        datos_del_mes: el mismo Cruce, con la misma caché del campo, que vio
        el Detalle, y en el orden de sus líneas. Una Revisión anterior no se
        toca: la nueva pasa a ser la vigente por ser la más reciente."""
        inicio = _leer_mes(mes, "mes")
        texto = _leer_comentario(comentario)
        self._validar_cliente(cliente_id)

        cruce = self.datos_del_mes(cliente_id, inicio).cruce
        if CON_DIFERENCIA not in cruce.estados:
            raise NoRevisable(_por_que_no_se_revisa(cruce))

        self.db.add(RevisionDiferencia(
            cliente_id=cliente_id, mes=inicio,
            desde=inicio, hasta=fechas.fin_de_mes(inicio),
            comentario=texto, creada_en=ahora_utc(), creada_por=usuario_id,
            grupos=[RevisionGrupo(grupo=g.grupo, unidad=g.unidad)
                    for g in cruce.grupos if g.supera]))
        self.db.commit()
        return self.detalle(cliente_id, mes)

    def deshacer_revision(self, cliente_id: int, mes: str,
                          usuario_id: int | None) -> dict:
        """Deshace la Revisión vigente de un Cliente y mes ("AAAA-MM") y
        devuelve el Detalle (ruta 16). No la borra: sella `deshecha_en` y
        `deshecha_por`, y queda en el registro. Sin una vigente, SinRevision.
        No mira el estado del mes: se deshace aunque el Admin haya movido el
        corte después."""
        inicio = _leer_mes(mes, "mes")
        self._validar_cliente(cliente_id)

        vigente = revisiones_vigentes(self.db, inicio, inicio, cliente_id).get(
            (cliente_id, inicio))
        if vigente is None:
            raise SinRevision()
        vigente.deshecha_en = ahora_utc()
        vigente.deshecha_por = usuario_id
        self.db.commit()
        return self.detalle(cliente_id, mes)

    def _validar_cliente(self, cliente_id: int) -> None:
        """El 404 del Detalle (ruta 14), antes de leer los partes."""
        if cliente_id not in self.nombres_de_clientes({cliente_id}):
            raise ClienteNoEncontrado()

    def _revision(self, vigente: RevisionDiferencia | None) -> dict | None:
        """La Revisión vigente como la pide la ruta 14, o None. Sus grupos van
        en el orden de las líneas del Resumen, con "Sin grupo" al final."""
        if vigente is None:
            return None
        persona = (self.db.get(Usuario, vigente.creada_por)
                   if vigente.creada_por is not None else None)
        grupos = sorted(vigente.grupos, key=lambda g: (
            g.grupo is None, g.grupo or "", _orden_unidad(g.unidad)))
        return {
            "id": vigente.id,
            "comentario": vigente.comentario,
            "creada_en": vigente.creada_en,
            "creada_por_nombre": persona.nombre if persona else None,
            "grupos": [{"grupo": g.grupo or SIN_GRUPO, "unidad": g.unidad} for g in grupos],
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


def _leer_comentario(comentario: str | None) -> str:
    """El comentario de una Revisión sin los espacios de los bordes: no
    vacío y de hasta LARGO_COMENTARIO caracteres."""
    texto = (comentario or "").strip()
    if not texto:
        raise RevisionInvalida("Falta el comentario: por qué está bien la diferencia.")
    if len(texto) > LARGO_COMENTARIO:
        raise RevisionInvalida(
            f"El comentario puede tener hasta {LARGO_COMENTARIO} caracteres.")
    return texto


def _por_que_no_se_revisa(cruce: CruceMes) -> str:
    """El mensaje de NoRevisable, según el estado del mes."""
    if ANTES_DEL_CORTE in cruce.estados:
        return "El mes es anterior al Mes de corte: no se controla."
    if MES_EN_CURSO in cruce.estados:
        return "El mes todavía no terminó: se controla cuando termine."
    if PENDIENTE_DE_FACTURAR in cruce.estados:
        return "El mes no tiene nada facturado: falta cargar la factura, no revisarla."
    if cruce.diferencia_revisada:
        return "La diferencia de este mes ya está revisada."
    return "Ninguna tarea supera el Umbral: no hay diferencia que revisar."


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


@dataclass
class DatosDelMes:
    """Lo que el Detalle y la Revisión leen de un Cliente en un mes, ya
    cruzado. `lineas` son todas las del mes, también las que no cuentan en el
    Cruce; `partes`, las filas del campo tal como vienen de la caché (no se
    modifican)."""
    configuracion: dict
    leido_en: datetime
    partes: list[dict]
    lineas: list[LineaFacturada]
    vigente: RevisionDiferencia | None
    cruce: CruceMes


def _orden_unidad(unidad: str | None) -> int:
    return UNIDADES.index(unidad) if unidad in UNIDADES else len(UNIDADES)


def _precios(cruce: CruceMes, sugeridos: dict) -> dict:
    """El precio de cada (tarea, unidad) del Cruce (decisión 6, pesos del
    Detalle): el precio medio de las Facturas del mes que cuentan
    (Σimporte / Σcantidad) y, si no hay, el Precio sugerido. Una fila sin
    unidad o sin ninguno de los dos no figura: queda sin valorizar.

    Si el precio medio del mes da 0 o menos, la fila tampoco figura y no cae
    al Precio sugerido (paso A8b, decisión del usuario, la misma regla que
    el A7b para el sugerido): un precio 0 suele ser un error de carga."""
    sumas: dict[tuple, list[Decimal]] = defaultdict(lambda: [CERO, CERO])
    for linea in cruce.lineas:
        if linea.tipo == FACTURA:
            suma = sumas[(linea.tarea_id, linea.unidad)]
            suma[0] += linea.importe
            suma[1] += linea.cantidad
    precios = {}
    for f in cruce.filas:
        clave = (f.tarea_id, f.unidad)
        if f.unidad is None:
            continue
        importe, cantidad = sumas.get(clave, (CERO, CERO))
        if cantidad:
            medio = (importe / cantidad).quantize(_DIEZMILESIMOS, rounding=ROUND_HALF_UP)
            if medio > 0:
                precios[clave] = medio
        elif clave in sugeridos:
            precios[clave] = sugeridos[clave]["precio_unitario"]
    return precios


def _comprobantes(lineas: list[LineaFacturada]) -> list[dict]:
    """Todos los Comprobantes con alguna Línea en el mes, también los que no
    cuentan en el Cruce, por id."""
    por_id = {}
    for linea in lineas:
        por_id.setdefault(linea.comprobante_id, {
            "id": linea.comprobante_id, "tipo": linea.tipo, "numero": linea.numero,
            "cantidad_adjuntos": linea.cantidad_adjuntos,
            "es_historico": linea.es_historico,
        })
    return [por_id[i] for i in sorted(por_id)]


def _grupos(cruce: CruceMes, partes: list[dict], precios: dict) -> list[dict]:
    """Las filas del Detalle: una por línea (grupo, unidad), como las del
    Resumen y en el orden del motor ("Sin grupo" al final), con sus tareas
    adentro en el orden de las filas del Cruce.

    Las tareas no avisan (decisión 1 de la spec): la diferencia y "supera"
    son de la fila. Cada tarea trae su Cantidad del campo en la unidad de la
    fila, su precio y sus partes medidos en esa unidad (None si no tiene),
    por fecha."""
    partes_por_tarea: dict[int, list[dict]] = defaultdict(list)
    for parte in sorted(partes, key=lambda p: p["fecha"]):
        partes_por_tarea[parte["tarea_id"]].append(parte)
    return [
        {**_linea(g), "tareas": [_tarea(f, partes_por_tarea, precios) for f in g.tareas]}
        for g in cruce.grupos
    ]


def _tarea(f: FilaCruce, partes_por_tarea: dict, precios: dict) -> dict:
    """Una tarea dentro de su fila (grupo, unidad) del Detalle."""
    return {
        "tarea_id": f.tarea_id,
        "tarea_nombre": f.tarea_nombre,
        "sin_unidad_sugerida": f.sin_unidad_sugerida,
        "en_varias_unidades": f.en_varias_unidades,
        "campo": f.campo,
        "precio": precios.get((f.tarea_id, f.unidad)),
        "partes": [
            {"fecha": p["fecha"], "donde": p["donde"], "supervisor": p["supervisor"],
             "cantidad": cantidad_en_unidad(p, f.unidad)}
            for p in partes_por_tarea.get(f.tarea_id, [])
        ],
    }


def _total(cruce: CruceMes, precios: dict) -> dict:
    """El TOTAL del Detalle: el campo valorizado con el precio de cada fila,
    lo facturado neto real (las Notas de crédito restan), la diferencia y su
    % ("—", None, si el campo valorizado es 0), y cuántas tareas tienen alguna
    fila sin precio (una tarea en dos unidades cuenta una vez)."""
    campo = sum((f.campo * precios[(f.tarea_id, f.unidad)]
                 for f in cruce.filas
                 if (f.tarea_id, f.unidad) in precios and f.campo is not None),
                CERO).quantize(_CENTESIMOS, rounding=ROUND_HALF_UP)
    facturado = cruce.facturado_neto
    diferencia = facturado - campo
    return {
        "campo_pesos": campo,
        "facturado_pesos": facturado,
        "diferencia_pesos": diferencia,
        "diferencia_pct": (None if not campo else
                           (diferencia * 100 / campo).quantize(
                               _CENTESIMOS, rounding=ROUND_HALF_UP)),
        "tareas_sin_precio": len({f.tarea_id for f in cruce.filas
                                  if (f.tarea_id, f.unidad) not in precios}),
    }


def _linea(grupo: FilaGrupo) -> dict:
    """Una línea (grupo, unidad) de una fila del Resumen, en cantidades."""
    return {
        "grupo": grupo.grupo or SIN_GRUPO,
        "unidad": grupo.unidad,
        "campo": grupo.campo,
        "facturado": grupo.facturado,
        "diferencia": grupo.diferencia,
        "diferencia_pct": grupo.diferencia_pct,
        "supera": grupo.supera,
    }


def _fila(cruce: CruceMes, cliente_nombre: str | None) -> dict:
    """Una fila del Resumen (ruta 13): las líneas (grupo, unidad) en el orden
    del motor, cuántas superan (decisión 2 de la spec: cuenta líneas, no
    grupos) y el Estado del mes. Sólo cantidades: sin pesos ni TOTAL."""
    return {
        "cliente_id": cruce.cliente_id,
        "cliente_nombre": cliente_nombre,
        "mes": cruce.mes,
        "grupos": [_linea(g) for g in cruce.grupos],
        "lineas_superan": len(cruce.superan),
        "estados": list(cruce.estados),
        "diferencia_revisada": cruce.diferencia_revisada,
        "comprobantes_sin_adjunto": list(cruce.comprobantes_sin_adjunto),
    }
