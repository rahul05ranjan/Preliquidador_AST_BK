"""El Detalle de un Cliente en un mes (plan de la E3, paso A8, y el contrato de
la ruta 14), sobre SQLite en memoria y con una consulta del campo falsa.

Lo que se cuida acá: el Detalle tiene una fila por (grupo de tareas, unidad),
como las líneas del Resumen, con sus tareas adentro (Ticket 2 de la spec de la
E3a por grupo); la diferencia y "supera" son de la fila, y las tareas no
avisan: traen la Cantidad del campo en la unidad de su fila y sus partes; una
tarea en dos unidades va en las dos filas, con los mismos partes medidos en
cada una; los pesos salen del precio medio de las Facturas del mes, si no del
Precio sugerido, y si tampoco hay la tarea queda sin precio (también si el
precio medio da 0 o menos, paso A8b); la Revisión vigente trae quién la dejó y
sus (grupo, unidad); los estados son los del Resumen para el mismo mes, porque
los dos pasan por el mismo motor; y el 404 sigue la regla del contrato.

La consulta falsa arma lo trabajado por mes del Resumen con los mismos partes
que da al Detalle, así las dos pantallas leen el mismo campo.

Hoy es el 10 de noviembre de 2026: noviembre es el mes en curso y, con el
corte inicial en octubre, octubre se controla y septiembre queda Antes del
corte. Datos inventados.
"""
import copy
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.models import Usuario
from app.modulos.facturacion import config, fechas
from app.modulos.facturacion.models import (
    Adjunto, Comprobante, LineaComprobante, RevisionDiferencia, RevisionGrupo,
)
from app.modulos.facturacion.services import consulta_externa
from app.modulos.facturacion.services.precios import precios_sugeridos
from app.modulos.facturacion.services.resumen_service import (
    ClienteNoEncontrado, MesInvalido, ResumenService,
)
from tests.facturacion import test_resumen_service as resumen_a6

D = Decimal

SEPTIEMBRE = date(2026, 9, 1)
OCTUBRE = date(2026, 10, 1)
NOVIEMBRE = date(2026, 11, 1)

LEIDO_PARTES = datetime(2026, 11, 10, 14, 0)
LEIDO_TAREAS = resumen_a6.LEIDO_TAREAS   # 13:30, la más vieja

PODA = resumen_a6.PODA              # MANUALES, horas de peón
RALEO = resumen_a6.RALEO            # MANUALES, plantas
ATADO = resumen_a6.ATADO            # MANUALES, sin Unidad sugerida
INTERNA = resumen_a6.INTERNA        # No facturable
CARGA_BINS = resumen_a6.CARGA_BINS  # cosecha
RASTREADO = 104                     # MAQUINARIA, horas de tractor
DESMALEZADO = 105                   # sin grupo, horas de peón
TRASPLANTE = 109                    # VIVERO, plantas
TAREA_VIEJA = 999                   # no está en el maestro

UNO, DOS, TRES, CUATRO, CINCO, NUEVE = 1, 2, 3, 4, 5, 9
SIN_NADA = 77                       # ni en el maestro ni con Comprobantes


class ConsultaFalsa(resumen_a6.ConsultaFalsa):
    """La del Resumen, con dos tareas más y los partes de cada Cliente. Lo
    trabajado por mes sale de esos mismos partes, agrupados como en la base."""

    TAREAS = resumen_a6.ConsultaFalsa.TAREAS + [
        {"tarea_id": RASTREADO, "nombre": "RASTREADO", "grupo_tarea": "MAQUINARIA",
         "unidad_sugerida": "horas_tractor", "no_facturable": False},
        {"tarea_id": DESMALEZADO, "nombre": "DESMALEZADO", "grupo_tarea": None,
         "unidad_sugerida": "horas_peon", "no_facturable": False},
        {"tarea_id": TRASPLANTE, "nombre": "TRASPLANTE", "grupo_tarea": "VIVERO",
         "unidad_sugerida": "plantas", "no_facturable": False},
    ]

    def __init__(self):
        super().__init__()
        self.partes = []   # (cliente_id, fila del parte)

    def parte(self, cliente_id, tarea_id, fecha, *, jornal="0", maquina="0",
              unidades="0", tancadas="0", donde="FINCA A", supervisor="SUPERVISOR A"):
        self.partes.append((cliente_id, {
            "fecha": fecha, "tarea_id": tarea_id, "donde": donde,
            "supervisor": supervisor, "horas_jornal": D(jornal),
            "horas_maquina": D(maquina), "unidades": D(unidades),
            "tancadas": D(tancadas)}))

    def partes_de_cliente(self, cliente_id, desde, hasta):
        self.lecturas.append(("partes", cliente_id, desde, hasta))
        return {"leido_en": LEIDO_PARTES, "filas": [
            p for c, p in self.partes if c == cliente_id and desde <= p["fecha"] <= hasta]}

    def trabajado_por_mes(self, desde, hasta):
        self.lecturas.append(("trabajado", desde, hasta, False))
        sumas = defaultdict(lambda: {"horas_jornal": D("0"), "horas_maquina": D("0"),
                                     "unidades": D("0"), "tancadas": D("0"),
                                     "partes": 0})
        for cliente_id, p in self.partes:
            mes = p["fecha"].replace(day=1)
            if desde.replace(day=1) <= mes <= hasta.replace(day=1):
                suma = sumas[(cliente_id, p["tarea_id"], mes)]
                for medida in ("horas_jornal", "horas_maquina", "unidades", "tancadas"):
                    suma[medida] += p[medida]
                suma["partes"] += 1
        return {"leido_en": LEIDO_PARTES, "filas": [
            {"cliente_id": c, "tarea_id": t, "mes": m, **suma}
            for (c, t, m), suma in sumas.items()]}


@pytest.fixture(autouse=True)
def hoy_10_de_noviembre(monkeypatch):
    monkeypatch.setattr(fechas, "_ahora",
                        lambda: datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc))


@pytest.fixture(autouse=True)
def cache_limpia():
    consulta_externa.invalidar_cache()
    yield
    consulta_externa.invalidar_cache()


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)()
    yield sesion
    sesion.close()
    engine.dispose()


@pytest.fixture()
def consulta():
    return ConsultaFalsa()


@pytest.fixture()
def servicio(db, consulta):
    return ResumenService(db, consulta)


@pytest.fixture()
def persona(db):
    p = Usuario(nombre="PERSONA DE PRUEBA", email="persona@prueba.test",
                password="x", rol="admin")
    db.add(p)
    db.commit()
    return p


_numeros = iter(range(1, 10_000))


def comprobante(db, cliente_id, lineas, *, tipo="factura", es_historico=False,
                pendiente_de_facturar=False, adjuntos=0, cliente_nombre=None):
    """Un Comprobante con sus Líneas, cada una (tarea_id, unidad, fecha,
    cantidad, importe) o con un sexto valor, el precio unitario (si no, 1), y
    un séptimo, el nombre de la tarea. Con `adjuntos` Adjuntos."""
    n = next(_numeros)
    filas = []
    for i, linea in enumerate(lineas, 1):
        tarea_id, unidad, fecha, cantidad, importe, *resto = linea
        precio = resto[0] if resto else "1"
        nombre = resto[1] if len(resto) > 1 else f"TAREA {tarea_id}"
        filas.append(LineaComprobante(
            orden=i, fecha=fecha, tarea_id=tarea_id, tarea_nombre=nombre,
            unidad=unidad, cantidad=D(cantidad), precio_unitario=D(precio),
            importe=D(importe)))
    c = Comprobante(
        tipo=tipo, cliente_id=cliente_id,
        cliente_nombre=cliente_nombre or f"COPIA {cliente_id}",
        empresa_emisora=None if es_historico else "EMPRESA UNO",
        numero=f"A {n:04d}", fecha=date(2026, 11, 2), es_historico=es_historico,
        pendiente_de_facturar=pendiente_de_facturar,
        clave_identidad=f"P|{n}", lineas=filas)
    db.add(c)
    db.flush()
    for i in range(adjuntos):
        db.add(Adjunto(comprobante_id=c.id, nombre_original="factura.pdf",
                       nombre_en_disco=f"{n}-{i}.pdf", tipo_contenido="application/pdf",
                       tamano_bytes=10))
    db.commit()
    return c


def revision(db, cliente_id, mes, grupos, *, creada_en, creada_por=None,
             deshecha=False, comentario="Explicada."):
    """Una Revisión del mes entero."""
    r = RevisionDiferencia(
        cliente_id=cliente_id, mes=mes, desde=mes, hasta=fechas.fin_de_mes(mes),
        comentario=comentario, creada_en=creada_en, creada_por=creada_por,
        deshecha_en=datetime(2026, 11, 9) if deshecha else None,
        grupos=[RevisionGrupo(grupo=g, unidad=u) for g, u in grupos])
    db.add(r)
    db.commit()
    return r


def tareas(detalle):
    """Las tareas del Detalle, en orden, cada una con la unidad de su fila
    (grupo, unidad) en "unidad", para buscarlas."""
    return [{**t, "unidad": g["unidad"]} for g in detalle["grupos"] for t in g["tareas"]]


def linea(detalle, grupo, unidad):
    """La fila (grupo, unidad) del Detalle, sin sus tareas."""
    encontradas = [{k: v for k, v in g.items() if k != "tareas"}
                   for g in detalle["grupos"]
                   if (g["grupo"], g["unidad"]) == (grupo, unidad)]
    assert len(encontradas) == 1, detalle["grupos"]
    return encontradas[0]


def medidas(detalle, grupo, unidad):
    """(campo, facturado, diferencia, diferencia_pct, supera) de una fila."""
    g = linea(detalle, grupo, unidad)
    return (g["campo"], g["facturado"], g["diferencia"], g["diferencia_pct"], g["supera"])


def fila(detalle, tarea_id, unidad=None):
    encontradas = [t for t in tareas(detalle) if t["tarea_id"] == tarea_id
                   and (unidad is None or t["unidad"] == unidad)]
    assert len(encontradas) == 1, encontradas
    return encontradas[0]


# ─── Encabezado ─────────────────────────────────────────────────────────────

def test_el_encabezado_trae_la_configuracion_y_la_lectura_mas_vieja(servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="8")

    detalle = servicio.detalle(UNO, "2026-10")

    assert detalle["cliente_id"] == UNO
    assert detalle["cliente_nombre"] == "CLIENTE UNO"
    assert detalle["mes"] == OCTUBRE
    assert detalle["umbral_pct"] == config.UMBRAL_INICIAL
    assert detalle["mes_corte"] == config.MES_CORTE_INICIAL
    # Dos lecturas del campo con hora distinta: vale la más vieja.
    assert detalle["leido_en"] == LEIDO_TAREAS
    # Los partes se leen del día 1 al último del mes, sólo de ese Cliente.
    assert ("partes", UNO, OCTUBRE, date(2026, 10, 31)) in consulta.lecturas


def test_los_comprobantes_son_todos_los_que_tienen_una_linea_en_el_mes(db, servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="8")
    a_mano = comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "8", "800")],
                         adjuntos=2)
    # No cuentan en el Cruce, pero tienen una Línea en el mes: van.
    historico = comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 16), "8", "800")],
                            es_historico=True, pendiente_de_facturar=True)
    cosecha = comprobante(db, UNO, [(CARGA_BINS, "bins", date(2026, 10, 1), "3", "90")])
    # Otro mes y otro Cliente: no van.
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 9, 16), "8", "800")])
    comprobante(db, DOS, [(PODA, "horas_peon", date(2026, 10, 1), "8", "800")])

    detalle = servicio.detalle(UNO, "2026-10")

    assert detalle["comprobantes"] == [
        {"id": a_mano.id, "tipo": "factura", "numero": a_mano.numero,
         "cantidad_adjuntos": 2, "es_historico": False},
        {"id": historico.id, "tipo": "factura", "numero": historico.numero,
         "cantidad_adjuntos": 0, "es_historico": True},
        {"id": cosecha.id, "tipo": "factura", "numero": cosecha.numero,
         "cantidad_adjuntos": 0, "es_historico": False},
    ]


# ─── Filas y partes ─────────────────────────────────────────────────────────

def test_el_campo_de_cada_fila_es_la_suma_de_sus_partes(db, servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="8", donde="FINCA A",
                   supervisor="SUPERVISOR A")
    consulta.parte(UNO, PODA, date(2026, 10, 17), jornal="12.5", donde="FINCA B",
                   supervisor=None)
    consulta.parte(UNO, RALEO, date(2026, 10, 5), unidades="300", jornal="40")
    consulta.parte(UNO, RALEO, date(2026, 10, 6), unidades="200", jornal="30")
    # Del mismo Cliente en otro mes y de otro Cliente en el mes: no suman.
    consulta.parte(UNO, PODA, date(2026, 9, 30), jornal="100")
    consulta.parte(DOS, PODA, date(2026, 10, 3), jornal="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "20", "2000")],
                adjuntos=1)

    detalle = servicio.detalle(UNO, "2026-10")

    poda = fila(detalle, PODA)
    assert poda["unidad"] == "horas_peon"
    assert poda["campo"] == D("20.5")
    assert medidas(detalle, "MANUALES", "horas_peon") == (
        D("20.5"), D("20"), D("-0.5"), D("-2.44"), False)
    assert poda["partes"] == [
        {"fecha": date(2026, 10, 3), "donde": "FINCA A", "supervisor": "SUPERVISOR A",
         "cantidad": D("8")},
        {"fecha": date(2026, 10, 17), "donde": "FINCA B", "supervisor": None,
         "cantidad": D("12.5")},
    ]
    # El modal da igual que la columna.
    assert sum(p["cantidad"] for p in poda["partes"]) == poda["campo"]

    # RALEO no tiene nada facturado: va con su Unidad sugerida, plantas, en
    # su propia fila, y cada parte se mide en plantas, no en horas.
    raleo = fila(detalle, RALEO)
    assert (raleo["unidad"], raleo["campo"]) == ("plantas", D("500"))
    assert [p["cantidad"] for p in raleo["partes"]] == [D("300"), D("200")]
    assert medidas(detalle, "MANUALES", "plantas") == (
        D("500"), D("0"), D("-500"), D("-100.00"), True)


def test_las_tareas_no_avisan_avisa_su_fila(db, servicio, consulta):
    # PODA facturada de menos y ATADO (facturado en horas de peón) de más:
    # MANUALES en horas de peón cierra (150 contra 150) y nadie avisa.
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="100")
    consulta.parte(UNO, ATADO, date(2026, 10, 3), jornal="50")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "50", "2500"),
                          (ATADO, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)

    detalle = servicio.detalle(UNO, "2026-10")

    assert medidas(detalle, "MANUALES", "horas_peon") == (
        D("150"), D("150"), D("0"), D("0.00"), False)
    # Una fila, con las dos tareas y la Cantidad del campo de cada una. Las
    # tareas no traen lo facturado ni la diferencia: no se comparan solas.
    assert [(g["grupo"], g["unidad"]) for g in detalle["grupos"]] == [
        ("MANUALES", "horas_peon")]
    assert [(t["tarea_nombre"], t["campo"]) for t in tareas(detalle)] == [
        ("ATADO", D("50")), ("PODA", D("100"))]
    for t in detalle["grupos"][0]["tareas"]:
        assert not {"facturado", "diferencia", "diferencia_pct", "supera"} & set(t)
    assert detalle["estados"] == ["facturada"]


def test_una_tarea_en_dos_unidades_muestra_sus_partes_en_cada_fila(db, servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="8", maquina="3")
    consulta.parte(UNO, PODA, date(2026, 10, 4), jornal="4", maquina="2")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "12", "1200"),
                          (PODA, "horas_tractor", date(2026, 10, 1), "5", "2500")],
                adjuntos=1)

    detalle = servicio.detalle(UNO, "2026-10")

    peon = fila(detalle, PODA, "horas_peon")
    tractor = fila(detalle, PODA, "horas_tractor")
    assert peon["en_varias_unidades"] is True
    assert tractor["en_varias_unidades"] is True
    assert (peon["campo"], [p["cantidad"] for p in peon["partes"]]) == (
        D("12"), [D("8"), D("4")])
    assert (tractor["campo"], [p["cantidad"] for p in tractor["partes"]]) == (
        D("5"), [D("3"), D("2")])
    assert [p["fecha"] for p in tractor["partes"]] == [date(2026, 10, 3), date(2026, 10, 4)]


def test_agrupa_por_grupo_de_tareas(db, servicio, consulta):
    consulta.parte(UNO, RALEO, date(2026, 10, 5), unidades="300")
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="8")
    consulta.parte(UNO, ATADO, date(2026, 10, 3), jornal="6")
    consulta.parte(UNO, RASTREADO, date(2026, 10, 3), maquina="4")
    consulta.parte(UNO, DESMALEZADO, date(2026, 10, 3), jornal="2")
    consulta.parte(UNO, TRASPLANTE, date(2026, 10, 3), unidades="50")
    # No facturable: no va en ningún grupo.
    consulta.parte(UNO, INTERNA, date(2026, 10, 3), jornal="9")
    # Una tarea que no está en el maestro: el nombre sale de su Línea.
    comprobante(db, UNO, [(TAREA_VIEJA, "horas_peon", date(2026, 10, 1), "3", "300",
                           "100", "TAREA VIEJA")], adjuntos=1)

    detalle = servicio.detalle(UNO, "2026-10")

    # Una fila por (grupo, unidad): por grupo, con "Sin grupo" al final
    # aunque por nombre iría antes de VIVERO, y dentro del grupo por unidad,
    # con la fila sin unidad al final. Las tareas, por nombre.
    assert [(g["grupo"], g["unidad"], [t["tarea_nombre"] for t in g["tareas"]])
            for g in detalle["grupos"]] == [
        ("MANUALES", "horas_peon", ["PODA"]),
        ("MANUALES", "plantas", ["RALEO"]),
        ("MANUALES", None, ["ATADO"]),
        ("MAQUINARIA", "horas_tractor", ["RASTREADO"]),
        ("VIVERO", "plantas", ["TRASPLANTE"]),
        ("Sin grupo", "horas_peon", ["DESMALEZADO", "TAREA VIEJA"]),
    ]
    vieja = fila(detalle, TAREA_VIEJA)
    assert (vieja["tarea_id"], vieja["campo"], vieja["partes"]) == (TAREA_VIEJA, D("0"), [])
    # Sin grupo en horas de peón: 2 trabajadas y 3 facturadas, las de TAREA
    # VIEJA, que no tiene partes.
    assert medidas(detalle, "Sin grupo", "horas_peon") == (
        D("2"), D("3"), D("1"), D("50.00"), True)
    # La fila sin unidad (ATADO, sin Unidad sugerida y sin nada facturado):
    # sin campo, sin diferencia y sin %, y la tarea lo dice; sus partes se ven
    # igual, sin cantidad.
    assert medidas(detalle, "MANUALES", None) == (None, D("0"), None, None, True)
    atado = fila(detalle, ATADO)
    assert atado["sin_unidad_sugerida"] is True
    assert atado["campo"] is None
    assert atado["partes"] == [{"fecha": date(2026, 10, 3), "donde": "FINCA A",
                                "supervisor": "SUPERVISOR A", "cantidad": None}]
    assert fila(detalle, PODA)["sin_unidad_sugerida"] is False


def test_un_grupo_en_dos_unidades_da_dos_filas(db, servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="10")
    # RALEO facturado en hectáreas y sin partes: lo facturado sin campo supera.
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "10", "1000"),
                          (RALEO, "hectareas", date(2026, 10, 1), "2.5", "500")],
                adjuntos=1)

    detalle = servicio.detalle(UNO, "2026-10")

    assert medidas(detalle, "MANUALES", "horas_peon") == (
        D("10"), D("10"), D("0"), D("0.00"), False)
    assert medidas(detalle, "MANUALES", "hectareas") == (
        D("0"), D("2.5"), D("2.5"), None, True)
    assert detalle["estados"] == ["con_diferencia"]


# ─── Pesos ──────────────────────────────────────────────────────────────────

def test_los_pesos_salen_del_precio_medio_del_mes_o_del_sugerido(db, servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="25")
    consulta.parte(UNO, RALEO, date(2026, 10, 5), unidades="400")
    consulta.parte(UNO, ATADO, date(2026, 10, 3), jornal="6")
    consulta.parte(UNO, RASTREADO, date(2026, 10, 3), maquina="4")
    # Octubre: dos Facturas de PODA, a 100 y a 120 la hora, más una Nota de
    # crédito. El precio medio del mes es (1000 + 1200) / 20 = 110: no es el
    # de la última Factura (el sugerido) ni lo toca la Nota de crédito.
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "10", "1000", "100")],
                adjuntos=1)
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 16), "10", "1200", "120")],
                adjuntos=1)
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 16), "5", "600", "120")],
                tipo="nota_credito", adjuntos=1)
    # RALEO no tiene Facturas en octubre: vale el Precio sugerido, el de la
    # última Factura del Cliente (septiembre, a 3 la planta).
    comprobante(db, UNO, [(RALEO, "plantas", date(2026, 9, 1), "100", "300", "3")],
                adjuntos=1)
    # De otro Cliente: no da precio a nadie.
    comprobante(db, DOS, [(RASTREADO, "horas_tractor", date(2026, 10, 1), "4", "2000",
                           "500")], adjuntos=1)

    detalle = servicio.detalle(UNO, "2026-10")

    assert fila(detalle, PODA)["precio"] == D("110")
    assert fila(detalle, RALEO)["precio"] == D("3")
    # Sin Facturas ni Precio sugerido, y sin unidad: sin precio.
    assert fila(detalle, RASTREADO)["precio"] is None
    assert fila(detalle, ATADO)["precio"] is None
    # Campo valorizado: PODA 25 × 110 + RALEO 400 × 3 = 3950. Facturado, el
    # neto real: 1000 + 1200 - 600 = 1600.
    assert detalle["total"] == {
        "campo_pesos": D("3950"),
        "facturado_pesos": D("1600"),
        "diferencia_pesos": D("-2350"),
        "diferencia_pct": D("-59.49"),
        "tareas_sin_precio": 2,
    }


def test_una_tarea_en_dos_unidades_cuenta_una_vez_sin_precio(db, servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="8", maquina="3")
    # Dos Notas de crédito: lo facturado en el mes no tiene Facturas y el
    # Cliente no tiene Precio sugerido.
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "1", "100"),
                          (PODA, "horas_tractor", date(2026, 10, 1), "1", "100")],
                tipo="nota_credito", adjuntos=1)

    detalle = servicio.detalle(UNO, "2026-10")

    assert [t["precio"] for t in tareas(detalle)] == [None, None]
    assert detalle["total"] == {
        "campo_pesos": D("0"),
        "facturado_pesos": D("-200"),
        "diferencia_pesos": D("-200"),
        "diferencia_pct": None,
        "tareas_sin_precio": 1,
    }


@pytest.mark.parametrize("importe, precio", [
    ("0", "0"),          # precio medio 0
    ("-100", "-10"),     # precio medio negativo
])
def test_un_precio_medio_de_0_o_menos_deja_la_tarea_sin_precio(db, servicio, consulta,
                                                                importe, precio):
    # Paso A8b, decisión del usuario: la misma regla que el Precio sugerido
    # (A7b). Un precio medio del mes de 0 o menos no es un precio y no cae al
    # Precio sugerido, aunque lo haya.
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="10")
    consulta.parte(UNO, RALEO, date(2026, 10, 5), unidades="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "10", importe, precio)],
                adjuntos=1)
    # Una Factura posterior, a 50 la hora: PODA tiene Precio sugerido.
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 11, 1), "10", "500", "50")],
                adjuntos=1)
    comprobante(db, UNO, [(RALEO, "plantas", date(2026, 10, 1), "100", "300", "3")],
                adjuntos=1)
    assert precios_sugeridos(db, UNO)[(PODA, "horas_peon")]["precio_unitario"] == D("50")

    detalle = servicio.detalle(UNO, "2026-10")

    assert fila(detalle, PODA)["precio"] is None
    assert fila(detalle, RALEO)["precio"] == D("3")
    # Sólo RALEO se valoriza: 100 × 3.
    assert detalle["total"]["campo_pesos"] == D("300")
    assert detalle["total"]["tareas_sin_precio"] == 1


# ─── Revisión ───────────────────────────────────────────────────────────────

def test_la_revision_vigente_trae_quien_y_sus_grupos(db, servicio, consulta, persona):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "150", "7500"),
                          (TAREA_VIEJA, "horas_peon", date(2026, 10, 1), "3", "300",
                           "100", "TAREA VIEJA")], adjuntos=1)
    revision(db, UNO, OCTUBRE, [("MANUALES", "horas_peon")],
             creada_en=datetime(2026, 11, 1))
    # TAREA VIEJA no está en el maestro: va en Sin grupo, que se guarda nulo.
    vigente = revision(db, UNO, OCTUBRE, [(None, "horas_peon"), ("MANUALES", "horas_peon")],
                       creada_en=datetime(2026, 11, 5, 12, 30), creada_por=persona.id,
                       comentario="Acordado con el Cliente.")
    revision(db, UNO, OCTUBRE, [], creada_en=datetime(2026, 11, 8), deshecha=True)
    # De otro mes: no cuenta.
    revision(db, UNO, SEPTIEMBRE, [], creada_en=datetime(2026, 11, 9))

    detalle = servicio.detalle(UNO, "2026-10")

    assert detalle["revision"] == {
        "id": vigente.id,
        "comentario": "Acordado con el Cliente.",
        "creada_en": datetime(2026, 11, 5, 12, 30),
        "creada_por_nombre": "PERSONA DE PRUEBA",
        # Por grupo, con Sin grupo al final, como las líneas del Resumen.
        "grupos": [
            {"grupo": "MANUALES", "unidad": "horas_peon"},
            {"grupo": "Sin grupo", "unidad": "horas_peon"},
        ],
    }
    assert (detalle["estados"], detalle["diferencia_revisada"]) == (["facturada"], True)
    assert detalle["se_puede_revisar"] is False


def test_sin_revision_vigente_es_null(db, servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "150", "7500")],
                adjuntos=1)
    revision(db, UNO, OCTUBRE, [("MANUALES", "horas_peon")],
             creada_en=datetime(2026, 11, 1), deshecha=True)

    detalle = servicio.detalle(UNO, "2026-10")

    assert detalle["revision"] is None
    assert (detalle["estados"], detalle["diferencia_revisada"]) == (["con_diferencia"], False)
    assert detalle["se_puede_revisar"] is True


# ─── Estados ────────────────────────────────────────────────────────────────

def test_los_estados_son_los_del_resumen_para_el_mismo_mes(db, servicio, consulta):
    # Octubre, que se controla.
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="100")          # pendiente
    consulta.parte(DOS, PODA, date(2026, 10, 3), jornal="60")
    consulta.parte(DOS, PODA, date(2026, 10, 20), jornal="40")
    comprobante(db, DOS, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)                                              # facturada
    consulta.parte(CUATRO, PODA, date(2026, 10, 3), jornal="100")
    comprobante(db, CUATRO, [(PODA, "horas_peon", date(2026, 10, 1), "150", "7500")],
                adjuntos=1)                                              # con diferencia
    consulta.parte(CINCO, PODA, date(2026, 10, 3), jornal="100")
    comprobante(db, CINCO, [(PODA, "horas_peon", date(2026, 10, 1), "150", "7500")],
                adjuntos=1)
    revision(db, CINCO, OCTUBRE, [("MANUALES", "horas_peon")],
             creada_en=datetime(2026, 11, 1))                            # revisada
    consulta.parte(TRES, RALEO, date(2026, 10, 3), unidades="300")
    comprobante(db, TRES, [(RALEO, "plantas", date(2026, 10, 1), "300", "900")])
    consulta.parte(TRES, PODA, date(2026, 10, 3), jornal="10")          # falta y diferencia
    # Septiembre, antes del corte, y noviembre, en curso.
    consulta.parte(UNO, PODA, date(2026, 9, 3), jornal="100")
    consulta.parte(DOS, RALEO, date(2026, 11, 3), unidades="300")
    comprobante(db, DOS, [(RALEO, "plantas", date(2026, 11, 1), "100", "300")])

    resumen = servicio.resumen("2026-09", "2026-11")
    detalles = {(f["cliente_id"], f["mes"]): servicio.detalle(
                    f["cliente_id"], f["mes"].strftime("%Y-%m"))
                for f in resumen["filas"]}

    for f in resumen["filas"]:
        detalle = detalles[(f["cliente_id"], f["mes"])]
        assert detalle["estados"] == f["estados"], (f["cliente_id"], f["mes"])
        assert detalle["diferencia_revisada"] == f["diferencia_revisada"]
        assert detalle["se_puede_revisar"] == ("con_diferencia" in f["estados"])
    # Y no es una comparación vacía: están todos los casos.
    assert {clave: (d["estados"], d["diferencia_revisada"])
            for clave, d in detalles.items()} == {
        (UNO, OCTUBRE): (["pendiente_de_facturar"], False),
        (DOS, OCTUBRE): (["facturada"], False),
        (CUATRO, OCTUBRE): (["con_diferencia"], False),
        (CINCO, OCTUBRE): (["facturada"], True),
        (TRES, OCTUBRE): (["con_diferencia", "falta_comprobante"], False),
        (UNO, SEPTIEMBRE): (["antes_del_corte"], False),
        (DOS, NOVIEMBRE): (["falta_comprobante", "mes_en_curso"], False),
    }


@pytest.mark.parametrize("mes, estados", [
    ("2026-09", ["antes_del_corte"]),
    ("2026-11", ["mes_en_curso"]),
])
def test_en_los_meses_que_no_se_controlan_nada_supera(db, servicio, consulta, mes, estados):
    inicio = fechas.leer_mes(mes)
    consulta.parte(UNO, PODA, inicio.replace(day=3), jornal="100")
    consulta.parte(UNO, RALEO, inicio.replace(day=4), unidades="300")
    consulta.parte(UNO, ATADO, inicio.replace(day=5), jornal="7")
    comprobante(db, UNO, [(PODA, "horas_peon", inicio, "10", "500")], adjuntos=1)

    detalle = servicio.detalle(UNO, mes)

    assert detalle["estados"] == estados
    assert len(tareas(detalle)) == 3
    assert all(g["supera"] is False for g in detalle["grupos"])
    assert detalle["se_puede_revisar"] is False
    # Los números se muestran igual.
    assert linea(detalle, "MANUALES", "horas_peon")["diferencia"] == D("-90")


# ─── 404 y errores ──────────────────────────────────────────────────────────

def test_un_cliente_que_no_esta_en_el_maestro_ni_tiene_comprobantes_da_404(db, servicio,
                                                                          consulta):
    # Tiene partes, pero el campo no lo tiene como Cliente.
    consulta.parte(SIN_NADA, PODA, date(2026, 10, 3), jornal="8")

    with pytest.raises(ClienteNoEncontrado) as error:
        servicio.detalle(SIN_NADA, "2026-10")
    assert error.value.mensaje
    # Se decide antes de leer los partes.
    assert not any(l[0] == "partes" for l in consulta.lecturas)


def test_un_cliente_fuera_del_maestro_con_comprobantes_de_otro_mes_no_da_404(db, servicio):
    comprobante(db, NUEVE, [(PODA, "horas_peon", date(2026, 8, 1), "10", "500")],
                cliente_nombre="CLIENTE NUEVE")

    detalle = servicio.detalle(NUEVE, "2026-10")

    assert detalle["cliente_nombre"] == "CLIENTE NUEVE"
    assert detalle["grupos"] == []
    assert detalle["comprobantes"] == []


def test_un_cliente_de_baja_sin_nada_en_el_mes_no_da_404(servicio):
    detalle = servicio.detalle(TRES, "2026-10")

    assert detalle["cliente_nombre"] == "CLIENTE TRES"
    assert detalle["grupos"] == []
    assert detalle["revision"] is None
    assert detalle["total"]["campo_pesos"] == D("0")


@pytest.mark.parametrize("mes", ["2026-13", "2026-9", "x"])
def test_mes_invalido(servicio, consulta, mes):
    with pytest.raises(MesInvalido) as error:
        servicio.detalle(UNO, mes)
    assert error.value.campo == "mes"
    assert consulta.lecturas == []


# ─── Caché ──────────────────────────────────────────────────────────────────

def test_no_modifica_las_filas_del_campo(db, servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="8", maquina="3")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "8", "800"),
                          (PODA, "horas_tractor", date(2026, 10, 1), "3", "300")],
                adjuntos=1)
    antes = copy.deepcopy(consulta.partes)

    servicio.detalle(UNO, "2026-10")

    assert consulta.partes == antes


def test_refrescar_invalida_la_cache_del_cruce_antes_de_leer(servicio):
    consulta_externa._CACHE[("partes", UNO, OCTUBRE, NOVIEMBRE)] = (float("inf"), {})
    consulta_externa._CACHE[("clientes", True)] = (float("inf"), [])

    servicio.detalle(UNO, "2026-10")
    assert ("partes", UNO, OCTUBRE, NOVIEMBRE) in consulta_externa._CACHE

    servicio.detalle(UNO, "2026-10", refrescar=True)
    assert ("partes", UNO, OCTUBRE, NOVIEMBRE) not in consulta_externa._CACHE
    assert ("clientes", True) in consulta_externa._CACHE
