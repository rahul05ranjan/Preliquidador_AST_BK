"""El motor del Cruce: lo trabajado contra lo facturado, por Cliente y mes
(plan de la E3, decisión 6).

Es puro: recibe lo trabajado (las filas del campo, crudas), las Líneas de lo
facturado y el maestro de tareas, y devuelve el Cruce con el Estado del mes.
No lee ninguna base. Nunca modifica lo que recibe: las filas del campo vienen
de la caché compartida de consulta_externa, y tocarlas la ensuciaría.

Lo usan el Resumen (con trabajado_por_mes, ya agrupado en la base), el
Detalle (con los partes de un Cliente, que suma medidas_por_tarea) y el
script de aceptación.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from app.modulos.facturacion.services.reglas_comprobante import NOTA_CREDITO
from app.modulos.facturacion.unidades import UNIDADES, UNIDADES_COSECHA

CERO = Decimal("0")

# Qué medida del campo se compara con cada unidad (decisión 6). Son las cinco
# columnas del Resumen, en el orden de UNIDADES. Las de cosecha no tienen.
MEDIDA_DE_UNIDAD = {
    "horas_peon": "horas_jornal",
    "horas_tractor": "horas_maquina",
    "plantas": "unidades",
    "hectareas": "unidades",
    "tancadas": "tancadas",
}
UNIDADES_CRUCE = tuple(MEDIDA_DE_UNIDAD)

# Las claves de estado, en orden de urgencia (ruta 13 del plan).
PENDIENTE_DE_FACTURAR = "pendiente_de_facturar"
CON_DIFERENCIA = "con_diferencia"
FALTA_COMPROBANTE = "falta_comprobante"
FACTURADA = "facturada"
MES_EN_CURSO = "mes_en_curso"
ANTES_DEL_CORTE = "antes_del_corte"
ESTADOS = (PENDIENTE_DE_FACTURAR, CON_DIFERENCIA, FALTA_COMPROBANTE, FACTURADA,
           MES_EN_CURSO, ANTES_DEL_CORTE)

_CENTESIMOS = Decimal("0.01")


@dataclass(frozen=True)
class Medidas:
    """Lo trabajado en una tarea: las cuatro medidas crudas del campo y la
    cantidad de partes."""
    horas_jornal: Decimal = CERO
    horas_maquina: Decimal = CERO
    unidades: Decimal = CERO
    tancadas: Decimal = CERO
    partes: int = 0


@dataclass(frozen=True)
class LineaFacturada:
    """Una Línea de comprobante con lo de su Comprobante que el Cruce usa.
    Cantidad e importe van positivos, como en la base: el signo sale del
    tipo. La fecha es la de la Línea, y el mes en que cuenta es el suyo."""
    comprobante_id: int
    tipo: str
    numero: str | None
    es_historico: bool
    pendiente_de_facturar: bool
    cantidad_adjuntos: int
    cliente_id: int
    fecha: date
    tarea_id: int
    tarea_nombre: str
    unidad: str
    cantidad: Decimal
    importe: Decimal

    @property
    def mes(self) -> date:
        return self.fecha.replace(day=1)

    @property
    def signo(self) -> int:
        return -1 if self.tipo == NOTA_CREDITO else 1


@dataclass
class FilaCruce:
    """Una (tarea, unidad) del Cruce. `unidad` es None si la tarea no tiene
    nada facturado ni Unidad sugerida: entonces `campo`, `diferencia` y
    `diferencia_pct` son None. `facturado` e `importe` son netos (las Notas de
    crédito restan). `diferencia_pct` es None si el campo es 0."""
    tarea_id: int
    tarea_nombre: str | None
    grupo_tarea: str | None
    unidad: str | None
    sin_unidad_sugerida: bool
    en_varias_unidades: bool
    partes: int
    campo: Decimal | None
    facturado: Decimal
    importe: Decimal
    diferencia: Decimal | None
    diferencia_pct: Decimal | None
    supera: bool


@dataclass
class CruceMes:
    """El Cruce de un Cliente en un mes, con su Estado.

    - `estados`: claves de ESTADOS, en orden de urgencia.
    - `superan`: las (tarea_id, unidad) que superan el Umbral; vacío en los
      meses que no se controlan. Es lo que guarda una Revisión.
    - `columnas`: la Cantidad del campo sumada por unidad (las cinco de
      UNIDADES_CRUCE); una tarea sin unidad no suma.
    - `facturado_neto`: el importe neto de las Líneas que cuentan.
    - `lineas`: las Líneas que cuentan en el Cruce.
    - `comprobantes_sin_adjunto`: [{id, tipo, numero}] de los cargados a mano
      con alguna Línea que cuenta y sin Adjuntos, por id."""
    cliente_id: int
    mes: date
    filas: list[FilaCruce]
    estados: list[str]
    diferencia_revisada: bool
    superan: set
    columnas: dict[str, Decimal]
    facturado_neto: Decimal
    lineas: list[LineaFacturada] = field(default_factory=list)
    comprobantes_sin_adjunto: list[dict] = field(default_factory=list)


def medidas_por_tarea(filas: Iterable[dict]) -> dict[int, Medidas]:
    """Suma las medidas por tarea. Sirve para las filas de trabajado_por_mes
    (traen `partes`) y para los partes del Detalle (cada fila es un parte).
    No modifica las filas."""
    acumulado: dict[int, dict] = {}
    for f in filas:
        suma = acumulado.setdefault(f["tarea_id"], {
            "horas_jornal": CERO, "horas_maquina": CERO, "unidades": CERO,
            "tancadas": CERO, "partes": 0})
        for medida in ("horas_jornal", "horas_maquina", "unidades", "tancadas"):
            suma[medida] += f[medida]
        suma["partes"] += f.get("partes", 1)
    return {tarea_id: Medidas(**suma) for tarea_id, suma in acumulado.items()}


def cantidad_en_unidad(medidas, unidad: str | None) -> Decimal | None:
    """La medida que se compara con la unidad (MEDIDA_DE_UNIDAD), o None si
    la unidad no tiene medida (cosecha) o no hay unidad. `medidas` puede ser
    un Medidas o una fila del campo (dict): así el Detalle mide cada parte."""
    medida = MEDIDA_DE_UNIDAD.get(unidad)
    if medida is None:
        return None
    return medidas[medida] if isinstance(medidas, dict) else getattr(medidas, medida)


def _por_id(tareas: Iterable[dict]) -> dict[int, dict]:
    return {t["tarea_id"]: t for t in tareas}


def linea_cuenta(linea: LineaFacturada, tareas_por_id: dict[int, dict]) -> bool:
    """Si la Línea entra en el Cruce: fuera los históricos pendiente_de_facturar,
    las unidades de cosecha y las tareas No facturable. Una tarea que no está
    en el maestro cuenta."""
    if linea.pendiente_de_facturar or linea.unidad in UNIDADES_COSECHA:
        return False
    tarea = tareas_por_id.get(linea.tarea_id)
    return not (tarea and tarea["no_facturable"])


def _supera(partes: int, campo: Decimal | None, facturado: Decimal,
            umbral_pct: Decimal) -> bool:
    """La tabla "Supera" de la decisión 6. Con campo, el Umbral es estricto:
    |facturado - campo| / campo > umbral, sin dividir para no redondear."""
    if campo:
        return abs(facturado - campo) * 100 > umbral_pct * campo
    return partes > 0 or facturado != 0


def _orden_unidad(unidad: str | None) -> int:
    return UNIDADES.index(unidad) if unidad in UNIDADES else len(UNIDADES)


def cruzar_mes(*, cliente_id: int, mes: date, trabajado: dict[int, Medidas],
               lineas: Iterable[LineaFacturada], tareas: Iterable[dict],
               umbral_pct: Decimal, mes_corte: date, mes_en_curso: date,
               revisadas: set | None = None) -> CruceMes:
    """El Cruce de un Cliente en un mes.

    `trabajado` es lo de medidas_por_tarea; `lineas`, las Líneas del Cliente
    que caen en el mes (sin filtrar: acá se dejan afuera las que no cuentan);
    `tareas`, el maestro de tareas_cruce(); `revisadas`, las (tarea_id,
    unidad) que guardó la Revisión vigente, o None si no hay."""
    tareas_por_id = _por_id(tareas)
    que_cuentan = [l for l in lineas if linea_cuenta(l, tareas_por_id)]

    # Lo facturado neto por (tarea, unidad), y el nombre de la Línea por si
    # la tarea no está en el maestro.
    facturado: dict[tuple, list[Decimal]] = defaultdict(lambda: [CERO, CERO])
    nombre_de_linea: dict[int, str] = {}
    for l in que_cuentan:
        suma = facturado[(l.tarea_id, l.unidad)]
        suma[0] += l.signo * l.cantidad
        suma[1] += l.signo * l.importe
        nombre_de_linea.setdefault(l.tarea_id, l.tarea_nombre)

    unidades_facturadas: dict[int, list[str]] = defaultdict(list)
    for tarea_id, unidad in facturado:
        unidades_facturadas[tarea_id].append(unidad)

    controlado = mes_corte <= mes < mes_en_curso
    filas: list[FilaCruce] = []
    for tarea_id in set(trabajado) | set(unidades_facturadas):
        tarea = tareas_por_id.get(tarea_id, {})
        if tarea.get("no_facturable"):
            continue
        sugerida = tarea.get("unidad_sugerida")
        unidades = unidades_facturadas.get(tarea_id)
        if not unidades:
            if sugerida in UNIDADES_COSECHA:
                continue
            unidades = [sugerida]
        medidas = trabajado.get(tarea_id, Medidas())
        candidatas = []
        for unidad in unidades:
            cantidad, importe = facturado.get((tarea_id, unidad), (CERO, CERO))
            if medidas.partes == 0 and cantidad == 0:
                continue  # sin partes y nada facturado: no hay fila
            campo = cantidad_en_unidad(medidas, unidad)
            candidatas.append(FilaCruce(
                tarea_id=tarea_id,
                tarea_nombre=tarea.get("nombre") or nombre_de_linea.get(tarea_id),
                grupo_tarea=tarea.get("grupo_tarea"),
                unidad=unidad,
                sin_unidad_sugerida=sugerida is None,
                en_varias_unidades=False,
                partes=medidas.partes,
                campo=campo,
                facturado=cantidad,
                importe=importe,
                diferencia=None if campo is None else cantidad - campo,
                diferencia_pct=(None if not campo else
                                ((cantidad - campo) * 100 / campo)
                                .quantize(_CENTESIMOS, rounding=ROUND_HALF_UP)),
                supera=controlado and _supera(medidas.partes, campo, cantidad,
                                              umbral_pct),
            ))
        if len(candidatas) > 1:
            for f in candidatas:
                f.en_varias_unidades = True
        filas.extend(candidatas)
    filas.sort(key=lambda f: (f.tarea_nombre or "", f.tarea_id, _orden_unidad(f.unidad)))

    columnas = {u: CERO for u in UNIDADES_CRUCE}
    for f in filas:
        if f.unidad in columnas:
            columnas[f.unidad] += f.campo

    sin_adjunto: dict[int, dict] = {}
    for l in que_cuentan:
        if not l.es_historico and l.cantidad_adjuntos == 0:
            sin_adjunto[l.comprobante_id] = {
                "id": l.comprobante_id, "tipo": l.tipo, "numero": l.numero}
    falta = bool(sin_adjunto)

    superan = {(f.tarea_id, f.unidad) for f in filas if f.supera}
    diferencia_revisada = False
    if mes < mes_corte:
        estados = [ANTES_DEL_CORTE]
    elif not controlado:
        estados = [FALTA_COMPROBANTE, MES_EN_CURSO] if falta else [MES_EN_CURSO]
    elif not que_cuentan and any(f.partes > 0 for f in filas):
        estados = [PENDIENTE_DE_FACTURAR]
    else:
        estados = []
        if superan and revisadas is not None and superan <= revisadas:
            diferencia_revisada = True
        elif superan:
            estados.append(CON_DIFERENCIA)
        if falta:
            estados.append(FALTA_COMPROBANTE)
        if not estados:
            estados = [FACTURADA]

    return CruceMes(
        cliente_id=cliente_id,
        mes=mes,
        filas=filas,
        estados=estados,
        diferencia_revisada=diferencia_revisada,
        superan=superan,
        columnas=columnas,
        facturado_neto=sum((l.signo * l.importe for l in que_cuentan), CERO),
        lineas=que_cuentan,
        comprobantes_sin_adjunto=sorted(sin_adjunto.values(), key=lambda c: c["id"]),
    )


def cruzar(trabajado: Iterable[dict], lineas: Iterable[LineaFacturada],
           tareas: Iterable[dict], *, umbral_pct: Decimal, mes_corte: date,
           mes_en_curso: date, revisiones: dict | None = None) -> list[CruceMes]:
    """El Cruce de cada (Cliente, mes) que tenga trabajo o Líneas, para el
    Resumen y el script de aceptación, ordenado por mes y Cliente.

    `trabajado` son las filas de trabajado_por_mes; `lineas`, las del rango;
    `revisiones`, {(cliente_id, mes): las (tarea_id, unidad) de la vigente}.
    Un (Cliente, mes) que sólo tiene Líneas que no cuentan también sale: si
    se muestra lo decide quien llama."""
    tareas = list(tareas)
    revisiones = revisiones or {}
    filas_por_clave: dict[tuple, list[dict]] = defaultdict(list)
    for f in trabajado:
        filas_por_clave[(f["cliente_id"], f["mes"])].append(f)
    lineas_por_clave: dict[tuple, list[LineaFacturada]] = defaultdict(list)
    for l in lineas:
        lineas_por_clave[(l.cliente_id, l.mes)].append(l)

    claves = sorted(set(filas_por_clave) | set(lineas_por_clave),
                    key=lambda clave: (clave[1], clave[0]))
    return [
        cruzar_mes(cliente_id=cliente_id, mes=mes,
                   trabajado=medidas_por_tarea(filas_por_clave.get((cliente_id, mes), [])),
                   lineas=lineas_por_clave.get((cliente_id, mes), []),
                   tareas=tareas, umbral_pct=umbral_pct, mes_corte=mes_corte,
                   mes_en_curso=mes_en_curso,
                   revisadas=revisiones.get((cliente_id, mes)))
        for cliente_id, mes in claves
    ]


def tareas_sin_unidad(cruces: Iterable[CruceMes]) -> list[dict]:
    """El aviso del Resumen (decisión 5): las tareas facturables sin Unidad
    sugerida que tuvieron partes en el período, [{tarea_id, nombre,
    clientes}], con la cantidad de Clientes distintos, por nombre."""
    nombres: dict[int, str | None] = {}
    clientes: dict[int, set] = defaultdict(set)
    for cruce in cruces:
        for f in cruce.filas:
            if f.sin_unidad_sugerida and f.partes > 0:
                nombres[f.tarea_id] = f.tarea_nombre
                clientes[f.tarea_id].add(cruce.cliente_id)
    return sorted(
        ({"tarea_id": tarea_id, "nombre": nombres[tarea_id], "clientes": len(c)}
         for tarea_id, c in clientes.items()),
        key=lambda t: (t["nombre"] or "", t["tarea_id"]),
    )
