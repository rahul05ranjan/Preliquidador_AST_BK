"""El motor del Cruce: lo trabajado contra lo facturado, por Cliente y mes
(plan de la E3, decisión 6). La diferencia se mide por (grupo de tareas,
unidad) (spec de la E3a por grupo, decisión 1): las filas por tarea quedan
para el Detalle y el script, pero no avisan.

Es puro: recibe lo trabajado (las filas del campo, crudas), las Líneas de lo
facturado y el maestro de tareas, y devuelve el Cruce con el Estado del mes.

El Cruce mira el filtro recortado al mes (decisión 6; sin filtro, el mes
entero). Una Línea cuenta sólo si su período entero cae adentro (decisiones 7
y 8): una que cae en parte no cuenta, deja su (grupo, unidad) "fuera del
filtro" y su Comprobante va al aviso; una que cae entera afuera no está.
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

from app.modulos.facturacion.fechas import fin_de_mes, periodo_de_linea, recorte
from app.modulos.facturacion.services.reglas_comprobante import NOTA_CREDITO
from app.modulos.facturacion.unidades import UNIDADES, UNIDADES_COSECHA

CERO = Decimal("0")

# Qué medida del campo se compara con cada unidad (decisión 6), en el orden
# de UNIDADES. Las de cosecha no tienen.
MEDIDA_DE_UNIDAD = {
    "horas_peon": "horas_jornal",
    "horas_tractor": "horas_maquina",
    "plantas": "unidades",
    "hectareas": "unidades",
    "tancadas": "tancadas",
}

# Las claves de estado, en orden de urgencia (ruta 13 del plan).
PENDIENTE_DE_FACTURAR = "pendiente_de_facturar"
CON_DIFERENCIA = "con_diferencia"
FALTA_COMPROBANTE = "falta_comprobante"
# Ningún grupo de la fila se puede comparar en el filtro (decisión 7).
SIN_COMPARAR = "sin_comparar"
FACTURADA = "facturada"
ANTES_DEL_CORTE = "antes_del_corte"
ESTADOS = (PENDIENTE_DE_FACTURAR, CON_DIFERENCIA, FALTA_COMPROBANTE, SIN_COMPARAR,
           FACTURADA, ANTES_DEL_CORTE)

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

    @property
    def periodo(self) -> tuple[date, date]:
        """La quincena que cubre la Línea (decisión 8)."""
        return periodo_de_linea(self.fecha)


@dataclass
class FilaCruce:
    """Una (tarea, unidad) del Cruce. `unidad` es None si la tarea no tiene
    nada facturado ni Unidad sugerida: entonces `campo`, `diferencia` y
    `diferencia_pct` son None. `facturado` e `importe` son netos (las Notas de
    crédito restan). `diferencia_pct` es None si el campo es 0. `grupo_tarea`
    es None si la tarea no tiene grupo o no está en el maestro."""
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


@dataclass
class FilaGrupo:
    """Una línea (grupo de tareas, unidad) del Cruce: la suma de sus filas
    por tarea, que van en `tareas`. `grupo` None es Sin grupo. `campo`,
    `diferencia` y `diferencia_pct` siguen la regla de FilaCruce; `supera` es
    la tabla "Supera" sobre las sumas, y es False en los meses que no se
    controlan.

    `fuera_del_filtro`: alguna de sus Líneas cae en parte afuera del filtro.
    Entonces no se compara: `diferencia` y `diferencia_pct` van None y
    `supera` False, aunque tenga otras Líneas enteras adentro (grupo mixto);
    `facturado` suma sólo las que entran."""
    grupo: str | None
    unidad: str | None
    partes: int
    campo: Decimal | None
    facturado: Decimal
    diferencia: Decimal | None
    diferencia_pct: Decimal | None
    supera: bool
    tareas: list[FilaCruce] = field(default_factory=list)
    fuera_del_filtro: bool = False


@dataclass
class CruceMes:
    """El Cruce de un Cliente en un mes, con su Estado.

    - `estados`: claves de ESTADOS, en orden de urgencia.
    - `grupos`: las líneas (grupo, unidad), por grupo (Sin grupo al final)
      y por unidad.
    - `superan`: las (grupo, unidad) que superan el Umbral; vacío en los
      meses que no se controlan. Es lo que guarda una Revisión.
    - `facturado_neto`: el importe neto de las Líneas que cuentan.
    - `lineas`: las Líneas que cuentan en el Cruce.
    - `comprobantes_sin_adjunto`: [{id, tipo, numero}] de los cargados a mano
      sin Adjuntos con alguna Línea que cuenta o que cae en parte en el
      filtro, por id.
    - `desde` y `hasta`: el filtro recortado al mes, los dos incluidos.
    - `en_curso`: el período todavía no terminó (`hasta` es hoy o
      posterior). Se controla igual: el campo puede sumar partes.
    - `comprobantes_fuera`: [{id, tipo, numero, desde, hasta}] de los que
      tienen Líneas que cuentan en el Cruce pero caen en parte afuera, con el
      período de esas Líneas; por desde y por id. Es el aviso del Resumen."""
    cliente_id: int
    mes: date
    filas: list[FilaCruce]
    grupos: list[FilaGrupo]
    estados: list[str]
    diferencia_revisada: bool
    superan: set
    facturado_neto: Decimal
    lineas: list[LineaFacturada] = field(default_factory=list)
    comprobantes_sin_adjunto: list[dict] = field(default_factory=list)
    desde: date | None = None
    hasta: date | None = None
    comprobantes_fuera: list[dict] = field(default_factory=list)
    en_curso: bool = False


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


def _diferencia_pct(campo: Decimal | None, facturado: Decimal) -> Decimal | None:
    if not campo:
        return None
    return ((facturado - campo) * 100 / campo).quantize(_CENTESIMOS, rounding=ROUND_HALF_UP)


def _grupos(filas: list[FilaCruce], controlado: bool, umbral_pct: Decimal,
            fuera: set) -> list[FilaGrupo]:
    """Las líneas (grupo, unidad) de las filas por tarea, en el orden de
    CruceMes.grupos; las tareas de cada una, en el orden de las filas. El
    campo de una unidad sin medida queda None, como el de sus tareas. Las
    (tarea, unidad) de `fuera` dejan su línea fuera del filtro."""
    por_clave: dict[tuple, list[FilaCruce]] = defaultdict(list)
    for f in filas:
        por_clave[(f.grupo_tarea, f.unidad)].append(f)
    grupos = []
    for (nombre, unidad), tareas in por_clave.items():
        partes = sum(f.partes for f in tareas)
        facturado = sum((f.facturado for f in tareas), CERO)
        campo = (None if MEDIDA_DE_UNIDAD.get(unidad) is None
                 else sum((f.campo for f in tareas), CERO))
        afuera = any((f.tarea_id, f.unidad) in fuera for f in tareas)
        grupos.append(FilaGrupo(
            grupo=nombre, unidad=unidad, partes=partes, campo=campo,
            facturado=facturado,
            diferencia=None if campo is None or afuera else facturado - campo,
            diferencia_pct=None if afuera else _diferencia_pct(campo, facturado),
            supera=(controlado and not afuera
                    and _supera(partes, campo, facturado, umbral_pct)),
            tareas=tareas, fuera_del_filtro=afuera))
    grupos.sort(key=lambda g: (g.grupo is None, g.grupo or "", _orden_unidad(g.unidad)))
    return grupos


def _comprobantes_fuera(en_parte: list[LineaFacturada]) -> list[dict]:
    """Un Comprobante por entrada, con el período de sus Líneas que caen en
    parte: dentro de un mes son quincenas, así que van seguidas."""
    por_id: dict[int, dict] = {}
    for l in en_parte:
        desde, hasta = l.periodo
        c = por_id.setdefault(l.comprobante_id, {
            "id": l.comprobante_id, "tipo": l.tipo, "numero": l.numero,
            "desde": desde, "hasta": hasta})
        c["desde"], c["hasta"] = min(c["desde"], desde), max(c["hasta"], hasta)
    return sorted(por_id.values(), key=lambda c: (c["desde"], c["id"]))


def cruzar_mes(*, cliente_id: int, mes: date, trabajado: dict[int, Medidas],
               lineas: Iterable[LineaFacturada], tareas: Iterable[dict],
               umbral_pct: Decimal, mes_corte: date, hoy: date,
               revisadas: set | None = None, desde: date | None = None,
               hasta: date | None = None) -> CruceMes:
    """El Cruce de un Cliente en un mes.

    `trabajado` es lo de medidas_por_tarea, ya en el filtro; `lineas`, las
    Líneas del Cliente que caen en el mes (sin filtrar: acá se dejan afuera
    las que no cuentan y las que no entran en el filtro); `tareas`, el
    maestro de tareas_cruce(); `revisadas`, las (grupo, unidad) que guardó la
    Revisión vigente del período, o None si no hay; `desde` y `hasta`, el
    filtro recortado al mes (sin ellos, el mes entero); `hoy`, para saber si
    el período está en curso. Todo mes desde el Mes de corte se controla,
    también el mes en curso."""
    desde = desde or mes.replace(day=1)
    hasta = hasta or fin_de_mes(mes)
    tareas_por_id = _por_id(tareas)
    que_cuentan: list[LineaFacturada] = []
    en_parte: list[LineaFacturada] = []
    for l in lineas:
        if not linea_cuenta(l, tareas_por_id):
            continue
        inicio, fin = l.periodo
        if desde <= inicio and fin <= hasta:
            que_cuentan.append(l)
        elif inicio <= hasta and desde <= fin:
            en_parte.append(l)
    fuera = {(l.tarea_id, l.unidad) for l in en_parte}

    # Lo facturado neto por (tarea, unidad), y el nombre de la Línea por si
    # la tarea no está en el maestro.
    facturado: dict[tuple, list[Decimal]] = defaultdict(lambda: [CERO, CERO])
    nombre_de_linea: dict[int, str] = {}
    for l in que_cuentan:
        suma = facturado[(l.tarea_id, l.unidad)]
        suma[0] += l.signo * l.cantidad
        suma[1] += l.signo * l.importe
        nombre_de_linea.setdefault(l.tarea_id, l.tarea_nombre)

    for l in en_parte:
        nombre_de_linea.setdefault(l.tarea_id, l.tarea_nombre)

    # Las unidades de cada tarea: las de lo facturado, las que entran y las
    # que caen en parte (una Línea en parte también da su fila).
    unidades_facturadas: dict[int, list[str]] = defaultdict(list)
    for tarea_id, unidad in list(facturado) + sorted(fuera - set(facturado)):
        unidades_facturadas[tarea_id].append(unidad)

    controlado = mes >= mes_corte
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
            if medidas.partes == 0 and cantidad == 0 and (tarea_id, unidad) not in fuera:
                continue  # sin partes y nada facturado: no hay fila
            campo = cantidad_en_unidad(medidas, unidad)
            candidatas.append(FilaCruce(
                tarea_id=tarea_id,
                tarea_nombre=tarea.get("nombre") or nombre_de_linea.get(tarea_id),
                grupo_tarea=tarea.get("grupo_tarea") or None,
                unidad=unidad,
                sin_unidad_sugerida=sugerida is None,
                en_varias_unidades=False,
                partes=medidas.partes,
                campo=campo,
                facturado=cantidad,
                importe=importe,
                diferencia=None if campo is None else cantidad - campo,
                diferencia_pct=_diferencia_pct(campo, cantidad),
            ))
        if len(candidatas) > 1:
            for f in candidatas:
                f.en_varias_unidades = True
        filas.extend(candidatas)
    filas.sort(key=lambda f: (f.tarea_nombre or "", f.tarea_id, _orden_unidad(f.unidad)))
    grupos = _grupos(filas, controlado, umbral_pct, fuera)

    sin_adjunto: dict[int, dict] = {}
    for l in que_cuentan + en_parte:
        if not l.es_historico and l.cantidad_adjuntos == 0:
            sin_adjunto[l.comprobante_id] = {
                "id": l.comprobante_id, "tipo": l.tipo, "numero": l.numero}
    falta = bool(sin_adjunto)

    superan = {(g.grupo, g.unidad) for g in grupos if g.supera}
    diferencia_revisada = False
    if not controlado:
        estados = [ANTES_DEL_CORTE]
    elif grupos and all(g.fuera_del_filtro for g in grupos):
        estados = [FALTA_COMPROBANTE, SIN_COMPARAR] if falta else [SIN_COMPARAR]
    elif not que_cuentan and not en_parte and any(f.partes > 0 for f in filas):
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
        grupos=grupos,
        estados=estados,
        diferencia_revisada=diferencia_revisada,
        superan=superan,
        facturado_neto=sum((l.signo * l.importe for l in que_cuentan), CERO),
        lineas=que_cuentan,
        comprobantes_sin_adjunto=sorted(sin_adjunto.values(), key=lambda c: c["id"]),
        desde=desde,
        hasta=hasta,
        comprobantes_fuera=_comprobantes_fuera(en_parte),
        en_curso=hasta >= hoy,
    )


def cruzar(trabajado: Iterable[dict], lineas: Iterable[LineaFacturada],
           tareas: Iterable[dict], *, umbral_pct: Decimal, mes_corte: date,
           hoy: date, revisiones: dict | None = None,
           desde: date | None = None, hasta: date | None = None) -> list[CruceMes]:
    """El Cruce de cada (Cliente, mes) que tenga trabajo o Líneas, para el
    Resumen y el script de aceptación, ordenado por mes y Cliente.

    `trabajado` son las filas de trabajado_por_mes, ya en el filtro; `lineas`,
    las de los meses del rango; `revisiones`, {(cliente_id, mes): las (grupo,
    unidad) de la vigente del período}; `desde` y `hasta`, el filtro, que se
    recorta a cada mes (sin ellos, los meses enteros); `hoy`, como en
    cruzar_mes.
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
    cruces = []
    for cliente_id, mes in claves:
        corte = recorte(desde, hasta, mes)
        if corte is None:
            continue  # un mes que el filtro no toca
        cruces.append(cruzar_mes(
            cliente_id=cliente_id, mes=mes,
            trabajado=medidas_por_tarea(filas_por_clave.get((cliente_id, mes), [])),
            lineas=lineas_por_clave.get((cliente_id, mes), []),
            tareas=tareas, umbral_pct=umbral_pct, mes_corte=mes_corte,
            hoy=hoy,
            revisadas=revisiones.get((cliente_id, mes)),
            desde=corte[0], hasta=corte[1]))
    return cruces


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
