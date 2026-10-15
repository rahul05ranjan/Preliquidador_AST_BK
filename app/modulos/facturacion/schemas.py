"""Schemas Pydantic (request/response) del módulo Facturación.

Los de la E1 salieron el 2026-10-12 con la pantalla Unidad de medida por
defecto. Los de acá son de la E2 (plan de la E2, sección 3.2): la entrada del
alta y la edición de Comprobantes, y las salidas del router de Comprobantes;
y de la E3 (plan de la E3, sección 3.2, rutas 13 a 17): el Resumen, el
Detalle, la Revisión de diferencia y la configuración.

Los decimales salen como texto (`Decimal`, igual que en Terceros): un número
JSON pasaría por float y podría perder centavos. Los meses de la E3 salen como
"AAAA-MM", igual que el `mes` del listado de Comprobantes y que el mes de las
rutas.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, PlainSerializer


class LineaEntrada(BaseModel):
    """Una Línea tal como la manda la pantalla.

    Los decimales entran como número o como texto con punto decimal (el front
    convierte el formato argentino antes de mandar). Que la cantidad sea > 0,
    el precio >= 0, la unidad una de las nueve y la tarea y la finca del
    maestro lo controla el servicio y no el schema: así el error sale como
    `linea_invalida` con la fila y el campo, que es lo que la pantalla usa
    para marcar la fila, y no como la lista genérica de FastAPI.

    Sin importe: lo calcula siempre el backend."""
    fecha: date
    tarea_id: int
    unidad: str
    finca_id: int | None = None
    cantidad: Decimal
    precio_unitario: Decimal


class ComprobanteEntrada(BaseModel):
    """La entrada de POST y PUT de un Comprobante.

    Empresa, número y fecha son opcionales acá y obligatorios en el servicio,
    por lo mismo que en la Línea: el faltante sale como `comprobante_invalido`
    con su campo. El tipo es texto por la misma razón."""
    tipo: str
    cliente_id: int
    empresa_emisora: str | None = None
    numero: str | None = None
    fecha: date | None = None
    # Obligatoria en una Nota de crédito; en una Factura tiene que ir vacía.
    factura_corregida_id: int | None = None
    # Sólo en el PUT: el `actualizado_en` tal como lo devolvió el detalle
    # (null si nunca se editó). Si ya no es el de la base, otra persona lo
    # guardó en el medio y el servicio responde `comprobante_modificado`
    # (pregunta 18). El alta lo ignora.
    actualizado_en: datetime | None = None
    lineas: list[LineaEntrada] = []


# ─── Salidas ────────────────────────────────────────────────────────────────
# Espejo de los dicts de ComprobantesService.listar() y .detalle().

class ComprobanteFila(BaseModel):
    """Una fila del listado de Comprobantes."""
    id: int
    tipo: str
    # Vacío sólo en un histórico sin número.
    numero: str | None = None
    # Vacía sólo en un histórico sin FECHA FAC.
    fecha: date | None = None
    # "AAAA-MM" de la primera Línea (pregunta 10).
    mes: str | None = None
    cliente_id: int
    cliente_nombre: str
    # Vacía sólo en un histórico.
    empresa_emisora: str | None = None
    es_historico: bool
    pendiente_de_facturar: bool
    cantidad_lineas: int
    cantidad_adjuntos: int
    # Con signo: negativo en una Nota de crédito.
    total_neto: Decimal


class ComprobanteReferencia(BaseModel):
    """La Factura que corrige una Nota de crédito, o una Nota de una Factura."""
    id: int
    numero: str | None = None
    fecha: date | None = None


class LineaSalida(BaseModel):
    id: int
    orden: int
    fecha: date
    tarea_id: int
    tarea_nombre: str
    unidad: str
    finca_id: int | None = None
    finca_nombre: str | None = None
    cantidad: Decimal
    precio_unitario: Decimal
    # Siempre positivo: el front lo muestra negativo en una Nota de crédito.
    importe: Decimal


class AdjuntoSalida(BaseModel):
    id: int
    nombre_original: str
    tipo_contenido: str
    tamano_bytes: int
    subido_en: datetime


class ComprobanteDetalle(ComprobanteFila):
    """Los campos de la fila, más lo que muestra la pantalla del Comprobante."""
    factura_corregida: ComprobanteReferencia | None = None
    notas_credito: list[ComprobanteReferencia] = []
    lineas: list[LineaSalida] = []
    adjuntos: list[AdjuntoSalida] = []
    creado_en: datetime | None = None
    # El PUT lo devuelve tal cual, sin zona horaria (pregunta 18).
    actualizado_en: datetime | None = None


class OpcionMaestro(BaseModel):
    """Un cliente o una finca del campo, para elegir en la pantalla."""
    id: int
    nombre: str


class TareaCampo(BaseModel):
    """Una tarea activa del campo, con lo que se lee de su descripción."""
    tarea_id: int
    nombre: str
    grupo_tarea: str | None = None
    # Una de las nueve claves, o None si la descripción no la define.
    unidad_sugerida: str | None = None
    no_facturable: bool


# ═══ Resumen, Detalle, Revisión y configuración (E3, rutas 13 a 17) ═════════
# Espejo de los dicts de ResumenService. El servicio da los meses como el día
# 1 (`date`); acá salen como "AAAA-MM".

Mes = Annotated[date, PlainSerializer(lambda mes: mes.strftime("%Y-%m"), return_type=str)]

# Las claves de estado del mes (decisión 6), en orden de urgencia.
EstadoMes = Literal["pendiente_de_facturar", "con_diferencia", "falta_comprobante",
                    "facturada", "mes_en_curso", "antes_del_corte"]


class ComprobanteSinAdjunto(BaseModel):
    """Un Comprobante a mano que cuenta en el mes y no tiene Adjuntos."""
    id: int
    tipo: str
    numero: str | None = None


class FilaResumen(BaseModel):
    """Una fila del Resumen: un Cliente en un mes."""
    cliente_id: int
    # None sólo si el Cliente no está en el maestro ni tiene Comprobantes.
    cliente_nombre: str | None = None
    mes: Mes
    # Lo trabajado en el campo, por unidad.
    horas_peon: Decimal
    horas_tractor: Decimal
    tancadas: Decimal
    plantas: Decimal
    hectareas: Decimal
    # Con signo: las Notas de crédito restan.
    facturado_neto: Decimal
    # Ordenados por urgencia: el primero es el que se muestra.
    estados: list[EstadoMes]
    diferencia_revisada: bool
    comprobantes_sin_adjunto: list[ComprobanteSinAdjunto] = []


class TareaSinUnidad(BaseModel):
    """El aviso del Resumen (decisión 5): una tarea facturable sin Unidad
    sugerida que tuvo partes, y en cuántos Clientes."""
    tarea_id: int
    nombre: str | None = None
    clientes: int


class Resumen(BaseModel):
    """La respuesta de la ruta 13."""
    umbral_pct: Decimal
    mes_corte: Mes
    mes_en_curso: Mes
    # La lectura más vieja del campo que usa la pantalla, en UTC.
    leido_en: datetime
    filas: list[FilaResumen]
    tareas_sin_unidad: list[TareaSinUnidad]


class ComprobanteDelMes(BaseModel):
    """Un Comprobante con alguna Línea en el mes, cuente o no en el Cruce."""
    id: int
    tipo: str
    numero: str | None = None
    cantidad_adjuntos: int
    es_historico: bool


class ParteCampo(BaseModel):
    """Un parte del campo de una tarea, medido en la unidad de su fila."""
    fecha: date
    # El nombre de la finca del parte.
    donde: str | None = None
    supervisor: str | None = None
    # None si la fila no tiene unidad.
    cantidad: Decimal | None = None


class TareaDetalle(BaseModel):
    """Una fila del Detalle: una (tarea, unidad)."""
    tarea_id: int
    # Del maestro o, si la tarea no está ahí, de la Línea.
    tarea_nombre: str | None = None
    # La de lo facturado en el mes, si no la sugerida; None si no hay ninguna.
    unidad: str | None = None
    sin_unidad_sugerida: bool
    en_varias_unidades: bool
    # None si la fila no tiene unidad.
    campo: Decimal | None = None
    facturado: Decimal
    diferencia: Decimal | None = None
    # None ("—") si el campo es 0 o no hay.
    diferencia_pct: Decimal | None = None
    supera: bool
    # El precio medio del mes o el Precio sugerido; None si no hay ninguno.
    precio: Decimal | None = None
    partes: list[ParteCampo] = []


class GrupoDetalle(BaseModel):
    """Un grupo de tareas del maestro, o "Sin grupo"."""
    grupo: str
    tareas: list[TareaDetalle]


class TotalDetalle(BaseModel):
    """El TOTAL en pesos del Detalle."""
    campo_pesos: Decimal
    # El neto real: las Notas de crédito restan.
    facturado_pesos: Decimal
    diferencia_pesos: Decimal
    # None si el campo valorizado es 0.
    diferencia_pct: Decimal | None = None
    tareas_sin_precio: int


class TareaRevisada(BaseModel):
    """Una (tarea, unidad) que superaba cuando se dejó la Revisión."""
    tarea_id: int
    tarea_nombre: str | None = None
    unidad: str | None = None


class RevisionSalida(BaseModel):
    """La Revisión de diferencia vigente del mes."""
    id: int
    comentario: str
    creada_en: datetime
    # None si la persona ya no existe.
    creada_por_nombre: str | None = None
    tareas: list[TareaRevisada] = []


class DetalleResumen(BaseModel):
    """La respuesta de las rutas 14, 15 y 16: el Detalle de un Cliente en un
    mes."""
    cliente_id: int
    cliente_nombre: str | None = None
    mes: Mes
    umbral_pct: Decimal
    mes_corte: Mes
    leido_en: datetime
    estados: list[EstadoMes]
    diferencia_revisada: bool
    se_puede_revisar: bool
    comprobantes: list[ComprobanteDelMes] = []
    grupos: list[GrupoDetalle] = []
    total: TotalDetalle
    revision: RevisionSalida | None = None


class RevisionEntrada(BaseModel):
    """El cuerpo de la ruta 15.

    Opcional acá y obligatorio en el servicio, como la cabecera de un
    Comprobante: el faltante, el vacío y el de más de 500 caracteres salen
    como `revision_invalida` con su campo, y no como la lista genérica de
    FastAPI. El largo se mide en el servicio, después de recortar los bordes."""
    comentario: str | None = None


class ConfiguracionEntrada(BaseModel):
    """El cuerpo de la ruta 17: el Umbral (número o texto con punto decimal) y
    el Mes de corte como "AAAA-MM".

    Opcionales acá, por lo mismo que la Revisión: que el Umbral sea mayor que
    0, hasta 100 y con dos decimales, y que el Mes de corte no pase el mes en
    curso, lo controla el servicio, y el error sale como
    `configuracion_invalida` con su campo."""
    umbral_pct: Decimal | None = None
    mes_corte: str | None = None


class ConfiguracionSalida(BaseModel):
    """La respuesta de la ruta 17: lo guardado, con quién y cuándo."""
    umbral_pct: Decimal
    mes_corte: Mes
    # Los dos en None mientras nadie la cambió (valores iniciales).
    actualizado_en: datetime | None = None
    actualizado_por_nombre: str | None = None
