"""El motor del Cruce (plan de la E3, decisión 6, paso A5; spec de la E3a
por grupo, decisión 1).

`cruce.py` es puro: recibe lo trabajado (las filas del campo, crudas), las
Líneas de lo facturado y el maestro de tareas, y devuelve el Cruce de cada
Cliente y mes con su Estado. No lee ninguna base, así que acá no hay sesiones
ni SQLite. Datos inventados.
"""
import copy
from datetime import date
from decimal import Decimal

import pytest

from app.modulos.facturacion.services.cruce import (
    ESTADOS,
    LineaFacturada,
    cantidad_en_unidad,
    cruzar,
    cruzar_mes,
    medidas_por_tarea,
    tareas_sin_unidad,
)

D = Decimal

SEPTIEMBRE = date(2026, 9, 1)
AGOSTO = date(2026, 8, 1)
OCTUBRE = date(2026, 10, 1)

# El corte en agosto y hoy el 17 de octubre: desde agosto todo se controla,
# también octubre, el mes en curso.
MES_CORTE = AGOSTO
HOY = date(2026, 10, 17)
UMBRAL = D("5")

CLIENTE = 7

# El maestro, como lo devuelve tareas_cruce()["filas"].
PODA = 101          # horas de peón
TRACTOR = 102       # horas de tractor
RALEO = 103         # plantas
DESMALEZADO = 104   # hectáreas
PULVERIZACION = 105  # tancadas
SIN_UNIDAD = 106    # facturable, sin Unidad sugerida
INTERNA = 107       # No facturable
CARGA_BINS = 108    # sugerida de cosecha
FUERA_DEL_MAESTRO = 999

TAREAS = [
    {"tarea_id": PODA, "nombre": "PODA", "grupo_tarea": "MANUALES",
     "unidad_sugerida": "horas_peon", "no_facturable": False},
    {"tarea_id": TRACTOR, "nombre": "RASTRA", "grupo_tarea": "MAQUINARIA",
     "unidad_sugerida": "horas_tractor", "no_facturable": False},
    {"tarea_id": RALEO, "nombre": "RALEO", "grupo_tarea": "MANUALES",
     "unidad_sugerida": "plantas", "no_facturable": False},
    {"tarea_id": DESMALEZADO, "nombre": "DESMALEZADO", "grupo_tarea": None,
     "unidad_sugerida": "hectareas", "no_facturable": False},
    {"tarea_id": PULVERIZACION, "nombre": "PULVERIZACION", "grupo_tarea": "SANIDAD",
     "unidad_sugerida": "tancadas", "no_facturable": False},
    {"tarea_id": SIN_UNIDAD, "nombre": "ATADO", "grupo_tarea": "MANUALES",
     "unidad_sugerida": None, "no_facturable": False},
    {"tarea_id": INTERNA, "nombre": "LIMPIEZA GALPON", "grupo_tarea": "INTERNAS",
     "unidad_sugerida": None, "no_facturable": True},
    {"tarea_id": CARGA_BINS, "nombre": "CARGA DE BINS", "grupo_tarea": "COSECHA",
     "unidad_sugerida": "bins", "no_facturable": False},
]


def trabajo(tarea_id, *, jornal="0", maquina="0", unidades="0", tancadas="0",
            partes=1, cliente_id=CLIENTE, mes=SEPTIEMBRE):
    """Una fila de trabajado_por_mes()["filas"]."""
    return {"cliente_id": cliente_id, "tarea_id": tarea_id, "mes": mes,
            "horas_jornal": D(jornal), "horas_maquina": D(maquina),
            "unidades": D(unidades), "tancadas": D(tancadas), "partes": partes}


_ids = iter(range(1, 10_000))


def linea(tarea_id, unidad, cantidad, importe="1000", *, tipo="factura",
          comprobante_id=None, es_historico=False, pendiente_de_facturar=False,
          adjuntos=1, cliente_id=CLIENTE, fecha=date(2026, 9, 1),
          tarea_nombre="DE LA LINEA", numero="0001-00000001"):
    return LineaFacturada(
        comprobante_id=comprobante_id or next(_ids), tipo=tipo, numero=numero,
        es_historico=es_historico, pendiente_de_facturar=pendiente_de_facturar,
        cantidad_adjuntos=adjuntos, cliente_id=cliente_id, fecha=fecha,
        tarea_id=tarea_id, tarea_nombre=tarea_nombre, unidad=unidad,
        cantidad=D(cantidad), importe=D(importe))


def mes(trabajado=(), lineas=(), *, el_mes=SEPTIEMBRE, revisadas=None,
        umbral=UMBRAL, tareas=TAREAS, **corte):
    """El Cruce de CLIENTE en un mes; `corte` es desde y hasta, si van."""
    return cruzar_mes(
        cliente_id=CLIENTE, mes=el_mes,
        trabajado=medidas_por_tarea(trabajado), lineas=list(lineas),
        tareas=tareas, umbral_pct=umbral, mes_corte=MES_CORTE,
        hoy=HOY, revisadas=revisadas, **corte)


def fila(cruce, tarea_id, unidad="*"):
    encontradas = [f for f in cruce.filas
                   if f.tarea_id == tarea_id and (unidad == "*" or f.unidad == unidad)]
    assert len(encontradas) == 1, encontradas
    return encontradas[0]


def grupo(cruce, nombre, unidad):
    """La línea (grupo, unidad) del Cruce; `nombre` None es Sin grupo."""
    encontradas = [g for g in cruce.grupos if g.grupo == nombre and g.unidad == unidad]
    assert len(encontradas) == 1, cruce.grupos
    return encontradas[0]


# ─── Medida por unidad ──────────────────────────────────────────────────────

@pytest.mark.parametrize("unidad, esperado", [
    ("horas_peon", D("10")),
    ("horas_tractor", D("20")),
    ("plantas", D("30")),
    ("hectareas", D("30")),
    ("tancadas", D("40")),
])
def test_cada_unidad_compara_su_medida(unidad, esperado):
    medidas = medidas_por_tarea([trabajo(PODA, jornal="10", maquina="20",
                                         unidades="30", tancadas="40")])[PODA]
    assert cantidad_en_unidad(medidas, unidad) == esperado


def test_una_unidad_de_cosecha_o_ninguna_no_tiene_medida():
    medidas = medidas_por_tarea([trabajo(PODA, jornal="10")])[PODA]
    assert cantidad_en_unidad(medidas, "bins") is None
    assert cantidad_en_unidad(medidas, None) is None


def test_medidas_por_tarea_suma_y_cuenta_partes_sin_tocar_las_filas():
    # Los partes del Detalle no traen "partes": cada fila es un parte.
    partes = [
        {"fecha": date(2026, 9, 2), "tarea_id": PODA, "horas_jornal": D("4"),
         "horas_maquina": D("0"), "unidades": D("0"), "tancadas": D("0")},
        {"fecha": date(2026, 9, 3), "tarea_id": PODA, "horas_jornal": D("6"),
         "horas_maquina": D("0"), "unidades": D("0"), "tancadas": D("0")},
    ]
    antes = copy.deepcopy(partes)
    medidas = medidas_por_tarea(partes)
    assert medidas[PODA].horas_jornal == D("10")
    assert medidas[PODA].partes == 2
    assert partes == antes


def test_sin_facturado_se_usa_la_sugerida():
    cruce = mes([trabajo(RALEO, jornal="8", unidades="500")])
    f = fila(cruce, RALEO)
    assert f.unidad == "plantas"
    assert f.campo == D("500")
    assert f.facturado == D("0")


def test_facturado_en_otra_unidad_se_usa_la_de_lo_facturado():
    cruce = mes([trabajo(RALEO, jornal="8", unidades="500")],
                [linea(RALEO, "horas_peon", "8")])
    f = fila(cruce, RALEO)
    assert f.unidad == "horas_peon"
    assert f.campo == D("8")
    assert f.facturado == D("8")
    assert f.en_varias_unidades is False


def test_una_tarea_en_dos_unidades_da_dos_filas_marcadas():
    cruce = mes([trabajo(RALEO, jornal="8", unidades="500", partes=3)],
                [linea(RALEO, "horas_peon", "8"), linea(RALEO, "plantas", "500")])
    peon = fila(cruce, RALEO, "horas_peon")
    plantas = fila(cruce, RALEO, "plantas")
    assert peon.en_varias_unidades and plantas.en_varias_unidades
    assert (peon.campo, plantas.campo) == (D("8"), D("500"))
    assert peon.partes == plantas.partes == 3


def test_el_nombre_y_el_grupo_salen_del_maestro_o_de_la_linea():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10"),
                 linea(FUERA_DEL_MAESTRO, "horas_peon", "2", tarea_nombre="TAREA VIEJA")])
    assert (fila(cruce, PODA).tarea_nombre, fila(cruce, PODA).grupo_tarea) == ("PODA", "MANUALES")
    vieja = fila(cruce, FUERA_DEL_MAESTRO)
    assert (vieja.tarea_nombre, vieja.grupo_tarea) == ("TAREA VIEJA", None)


# ─── Qué entra ──────────────────────────────────────────────────────────────

def test_lo_no_facturable_no_entra_ni_trabajado_ni_facturado():
    cruce = mes([trabajo(INTERNA, jornal="10")],
                [linea(INTERNA, "horas_peon", "10", "500")])
    assert cruce.filas == []
    assert cruce.facturado_neto == D("0")
    assert cruce.lineas == []


def test_la_cosecha_no_entra():
    # Lo facturado en unidad de cosecha queda afuera, y la tarea de sugerida
    # de cosecha sin otro facturado tampoco tiene fila.
    cruce = mes([trabajo(CARGA_BINS, jornal="10")],
                [linea(PODA, "bins", "3", "900")])
    assert cruce.filas == []
    assert cruce.facturado_neto == D("0")


def test_una_tarea_de_sugerida_de_cosecha_facturada_en_horas_entra():
    cruce = mes([trabajo(CARGA_BINS, jornal="10")],
                [linea(CARGA_BINS, "horas_peon", "10")])
    assert fila(cruce, CARGA_BINS).unidad == "horas_peon"


def test_un_historico_pendiente_de_facturar_no_cuenta():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10", es_historico=True,
                       pendiente_de_facturar=True, numero=None)])
    assert fila(cruce, PODA).facturado == D("0")
    assert cruce.estados == ["pendiente_de_facturar"]


def test_una_nota_de_credito_resta_cantidad_e_importe():
    cruce = mes([trabajo(PODA, jornal="8")],
                [linea(PODA, "horas_peon", "10", "1000"),
                 linea(PODA, "horas_peon", "2", "200", tipo="nota_credito")])
    f = fila(cruce, PODA)
    assert f.facturado == D("8")
    assert f.importe == D("800")
    assert cruce.facturado_neto == D("800")


# ─── El Umbral ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("facturado, supera", [
    ("105", False),      # justo en el Umbral (5 %)
    ("105.01", True),    # apenas arriba
    ("95", False),       # para abajo, justo en el Umbral
    ("94.99", True),     # para abajo, apenas arriba
])
def test_el_umbral_es_estricto(facturado, supera):
    cruce = mes([trabajo(PODA, jornal="100")], [linea(PODA, "horas_peon", facturado)])
    assert grupo(cruce, "MANUALES", "horas_peon").supera is supera


def test_diferencia_y_porcentaje():
    cruce = mes([trabajo(PODA, jornal="80")], [linea(PODA, "horas_peon", "100")])
    f = fila(cruce, PODA)
    assert f.diferencia == D("20")
    assert f.diferencia_pct == D("25.00")
    g = grupo(cruce, "MANUALES", "horas_peon")
    assert g.diferencia == D("20")
    assert g.diferencia_pct == D("25.00")


# ─── La tabla "Supera", por (grupo, unidad) ─────────────────────────────────

def test_con_partes_y_campo_cero_sin_facturado_supera():
    cruce = mes([trabajo(PODA, jornal="0", maquina="5")])
    g = grupo(cruce, "MANUALES", "horas_peon")
    assert g.campo == D("0")
    assert g.diferencia_pct is None
    assert g.supera is True


def test_la_tarea_sin_unidad_no_tiene_campo_supera_y_va_al_aviso():
    cruce = mes([trabajo(SIN_UNIDAD, jornal="10")],
                [linea(PODA, "horas_peon", "1")])
    f = fila(cruce, SIN_UNIDAD)
    assert f.unidad is None
    assert f.sin_unidad_sugerida is True
    assert f.campo is None
    assert f.diferencia is None and f.diferencia_pct is None
    g = grupo(cruce, "MANUALES", None)
    assert g.campo is None
    assert g.diferencia is None and g.diferencia_pct is None
    assert g.supera is True
    assert tareas_sin_unidad([cruce]) == [
        {"tarea_id": SIN_UNIDAD, "nombre": "ATADO", "clientes": 1}]


def test_con_campo_cero_y_algo_facturado_supera():
    cruce = mes([trabajo(PODA, jornal="0", maquina="3")],
                [linea(PODA, "horas_peon", "4")])
    assert grupo(cruce, "MANUALES", "horas_peon").supera is True


def test_facturado_sin_partes_supera():
    cruce = mes([], [linea(PODA, "horas_peon", "4")])
    g = grupo(cruce, "MANUALES", "horas_peon")
    assert g.partes == 0
    assert g.campo == D("0")
    assert g.supera is True


def test_facturado_sin_campo_supera_con_la_raya():
    # Una pulverización facturada por hectárea: el campo la mide en
    # tancadas, así que en hectáreas no tiene nada (caso borde 4 de la spec).
    cruce = mes([trabajo(PULVERIZACION, tancadas="12")],
                [linea(PULVERIZACION, "hectareas", "30")])
    g = grupo(cruce, "SANIDAD", "hectareas")
    assert g.campo == D("0")
    assert g.facturado == D("30")
    assert g.diferencia == D("30")
    assert g.diferencia_pct is None
    assert g.supera is True
    assert cruce.estados == ["con_diferencia"]


def test_sin_partes_y_facturado_cero_no_hay_fila():
    cruce = mes([], [linea(PODA, "horas_peon", "4", "400"),
                     linea(PODA, "horas_peon", "4", "400", tipo="nota_credito")])
    assert cruce.filas == []
    assert cruce.grupos == []


# ─── Las líneas por (grupo, unidad) ─────────────────────────────────────────

def test_con_el_mes_entero_da_lo_de_hoy_agrupado():
    # Guardián del cambio: las filas por tarea siguen iguales, y cada línea
    # (grupo, unidad) es la suma de las suyas.
    cruce = mes([trabajo(PODA, jornal="10", partes=2),
                 trabajo(TRACTOR, jornal="3", maquina="6"),
                 trabajo(RALEO, jornal="8", unidades="500"),
                 trabajo(DESMALEZADO, unidades="2.5"),
                 trabajo(PULVERIZACION, tancadas="12"),
                 trabajo(SIN_UNIDAD, jornal="99")],
                [linea(PODA, "horas_peon", "11"),
                 linea(RALEO, "horas_peon", "8"), linea(RALEO, "plantas", "450"),
                 linea(TRACTOR, "horas_tractor", "6"),
                 linea(PULVERIZACION, "tancadas", "12", tipo="nota_credito"),
                 linea(FUERA_DEL_MAESTRO, "horas_peon", "2")])
    assert [(f.tarea_id, f.unidad, f.campo, f.facturado) for f in cruce.filas] == [
        (SIN_UNIDAD, None, None, D("0")),
        (FUERA_DEL_MAESTRO, "horas_peon", D("0"), D("2")),
        (DESMALEZADO, "hectareas", D("2.5"), D("0")),
        (PODA, "horas_peon", D("10"), D("11")),
        (PULVERIZACION, "tancadas", D("12"), D("-12")),
        (RALEO, "horas_peon", D("8"), D("8")),
        (RALEO, "plantas", D("500"), D("450")),
        (TRACTOR, "horas_tractor", D("6"), D("6")),
    ]
    assert [(g.grupo, g.unidad, g.partes, g.campo, g.facturado) for g in cruce.grupos] == [
        ("MANUALES", "horas_peon", 3, D("18"), D("19")),
        ("MANUALES", "plantas", 1, D("500"), D("450")),
        ("MANUALES", None, 1, None, D("0")),
        ("MAQUINARIA", "horas_tractor", 1, D("6"), D("6")),
        ("SANIDAD", "tancadas", 1, D("12"), D("-12")),
        (None, "horas_peon", 0, D("0"), D("2")),
        (None, "hectareas", 1, D("2.5"), D("0")),
    ]
    for g in cruce.grupos:
        tareas = [(f.tarea_id, f.unidad) for f in g.tareas]
        assert tareas == [(f.tarea_id, f.unidad) for f in cruce.filas
                          if (f.grupo_tarea, f.unidad) == (g.grupo, g.unidad)]


def test_las_tareas_de_un_grupo_se_compensan():
    # PODA de más y RALEO de menos, en la misma unidad: el grupo cierra.
    cruce = mes([trabajo(PODA, jornal="10"), trabajo(RALEO, jornal="10")],
                [linea(PODA, "horas_peon", "15"), linea(RALEO, "horas_peon", "5")])
    g = grupo(cruce, "MANUALES", "horas_peon")
    assert (g.campo, g.facturado, g.diferencia) == (D("20"), D("20"), D("0"))
    assert g.supera is False
    assert cruce.superan == set()
    assert cruce.estados == ["facturada"]


def test_un_grupo_con_dos_unidades_da_dos_lineas():
    cruce = mes([trabajo(PODA, jornal="10"), trabajo(RALEO, unidades="500")],
                [linea(PODA, "horas_peon", "20"), linea(RALEO, "plantas", "800")])
    assert [(g.grupo, g.unidad) for g in cruce.grupos] == [
        ("MANUALES", "horas_peon"), ("MANUALES", "plantas")]
    assert cruce.superan == {("MANUALES", "horas_peon"), ("MANUALES", "plantas")}


def test_las_lineas_van_por_grupo_con_sin_grupo_al_final_y_por_unidad():
    cruce = mes([trabajo(DESMALEZADO, unidades="2"), trabajo(PULVERIZACION, tancadas="3"),
                 trabajo(TRACTOR, maquina="4"), trabajo(RALEO, unidades="5"),
                 trabajo(PODA, jornal="6")])
    assert [(g.grupo, g.unidad) for g in cruce.grupos] == [
        ("MANUALES", "horas_peon"), ("MANUALES", "plantas"),
        ("MAQUINARIA", "horas_tractor"), ("SANIDAD", "tancadas"),
        (None, "hectareas")]


# ─── Estados del mes ────────────────────────────────────────────────────────

def test_el_orden_de_urgencia():
    assert ESTADOS == ("pendiente_de_facturar", "con_diferencia", "falta_comprobante",
                       "sin_comparar", "facturada", "antes_del_corte")


def test_antes_del_corte_va_solo_y_no_supera():
    cruce = mes([trabajo(PODA, jornal="10")], [linea(PODA, "horas_peon", "50", adjuntos=0)],
                el_mes=date(2026, 7, 1))
    assert cruce.estados == ["antes_del_corte"]
    assert grupo(cruce, "MANUALES", "horas_peon").supera is False
    assert cruce.superan == set()
    assert cruce.diferencia_revisada is False


def test_el_mes_en_curso_se_controla_y_supera():
    cruce = mes([trabajo(PODA, jornal="10")], el_mes=OCTUBRE)
    assert cruce.estados == ["pendiente_de_facturar"]
    assert cruce.en_curso is True
    g = grupo(cruce, "MANUALES", "horas_peon")
    assert g.supera is True
    assert g.diferencia == D("-10")


def test_el_mes_en_curso_con_falta_comprobante_va_solo():
    lineas = [linea(PODA, "horas_peon", "10", comprobante_id=50, adjuntos=0,
                    fecha=date(2026, 10, 1), numero="0001-00000050")]
    cruce = mes([trabajo(PODA, jornal="10", mes=OCTUBRE)], lineas, el_mes=OCTUBRE)
    assert cruce.estados == ["falta_comprobante"]
    assert cruce.comprobantes_sin_adjunto == [
        {"id": 50, "tipo": "factura", "numero": "0001-00000050"}]


# ─── El período en curso (plan del 2026-10-17) ──────────────────────────────
# Hoy es el 17 de octubre: el Estado sale del período filtrado, también en el
# mes en curso, y `en_curso` dice si ese período todavía no terminó.

def test_la_quincena_pasada_del_mes_en_curso_se_controla_y_ya_termino():
    cruce = mes([trabajo(PODA, jornal="10", mes=OCTUBRE)], el_mes=OCTUBRE,
                desde=date(2026, 10, 1), hasta=date(2026, 10, 15))
    assert cruce.estados == ["pendiente_de_facturar"]
    assert cruce.en_curso is False


def test_un_periodo_que_no_termino_se_controla_igual_y_esta_en_curso():
    cruce = mes([trabajo(PODA, jornal="10", mes=OCTUBRE)], el_mes=OCTUBRE,
                desde=date(2026, 10, 16), hasta=date(2026, 10, 31))
    assert cruce.estados == ["pendiente_de_facturar"]
    assert cruce.en_curso is True


def test_un_periodo_que_termina_hoy_esta_en_curso():
    cruce = mes([trabajo(PODA, jornal="10", mes=OCTUBRE)],
                [linea(PODA, "horas_peon", "10", fecha=date(2026, 10, 1))], el_mes=OCTUBRE,
                desde=date(2026, 10, 1), hasta=date(2026, 10, 17))
    assert cruce.estados == ["facturada"]
    assert cruce.en_curso is True


def test_un_mes_que_ya_termino_no_esta_en_curso():
    cruce = mes([trabajo(PODA, jornal="10")])
    assert cruce.en_curso is False


def test_cruzar_dice_en_curso_por_mes_con_el_hasta_recortado():
    trabajado = [trabajo(PODA, jornal="10"), trabajo(PODA, jornal="10", mes=OCTUBRE)]
    cruces = cruzar(trabajado, [], TAREAS, umbral_pct=UMBRAL, mes_corte=MES_CORTE,
                    hoy=HOY,
                    desde=date(2026, 9, 16), hasta=date(2026, 10, 17))
    por_mes = {c.mes: (c.estados, c.en_curso) for c in cruces}
    assert por_mes == {SEPTIEMBRE: (["pendiente_de_facturar"], False),
                       OCTUBRE: (["pendiente_de_facturar"], True)}


def test_pendiente_de_facturar_va_solo():
    cruce = mes([trabajo(PODA, jornal="10")])
    assert cruce.estados == ["pendiente_de_facturar"]


def test_trabajo_no_facturable_sin_lineas_no_es_pendiente():
    cruce = mes([trabajo(INTERNA, jornal="10")])
    assert "pendiente_de_facturar" not in cruce.estados


def test_facturada_va_sola():
    cruce = mes([trabajo(PODA, jornal="10")], [linea(PODA, "horas_peon", "10")])
    assert cruce.estados == ["facturada"]
    assert cruce.diferencia_revisada is False


def test_con_diferencia():
    cruce = mes([trabajo(PODA, jornal="10")], [linea(PODA, "horas_peon", "20")])
    assert cruce.estados == ["con_diferencia"]


def test_con_diferencia_y_falta_comprobante():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "20", comprobante_id=60, adjuntos=0)])
    assert cruce.estados == ["con_diferencia", "falta_comprobante"]


def test_falta_comprobante_sin_diferencia_va_sola():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10", comprobante_id=61, adjuntos=0)])
    assert cruce.estados == ["falta_comprobante"]


def test_un_historico_sin_adjuntos_no_falta_comprobante():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10", es_historico=True, adjuntos=0)])
    assert cruce.estados == ["facturada"]
    assert cruce.comprobantes_sin_adjunto == []


def test_un_comprobante_que_solo_trae_lineas_que_no_cuentan_no_falta():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10", comprobante_id=70),
                 linea(PODA, "bins", "3", comprobante_id=71, adjuntos=0)])
    assert cruce.estados == ["facturada"]


def test_la_revision_que_cubre_deja_facturada_y_revisada():
    cruce = mes([trabajo(PODA, jornal="10")], [linea(PODA, "horas_peon", "20")],
                revisadas={("MANUALES", "horas_peon")})
    assert cruce.estados == ["facturada"]
    assert cruce.diferencia_revisada is True
    assert grupo(cruce, "MANUALES", "horas_peon").supera is True


def test_un_grupo_nuevo_que_supera_vuelve_a_con_diferencia():
    cruce = mes([trabajo(PODA, jornal="10"), trabajo(TRACTOR, maquina="5")],
                [linea(PODA, "horas_peon", "20"), linea(TRACTOR, "horas_tractor", "9")],
                revisadas={("MANUALES", "horas_peon")})
    assert cruce.estados == ["con_diferencia"]
    assert cruce.diferencia_revisada is False


def test_la_revision_es_por_grupo_y_unidad():
    cruce = mes([trabajo(PODA, jornal="10")], [linea(PODA, "horas_peon", "20")],
                revisadas={("MANUALES", "plantas")})
    assert cruce.estados == ["con_diferencia"]


def test_si_ninguna_supera_queda_facturada_sin_nota_aunque_haya_revision():
    cruce = mes([trabajo(PODA, jornal="10")], [linea(PODA, "horas_peon", "10")],
                revisadas={("MANUALES", "horas_peon")})
    assert cruce.estados == ["facturada"]
    assert cruce.diferencia_revisada is False


def test_la_tarea_sin_unidad_se_revisa_con_unidad_nula():
    cruce = mes([trabajo(SIN_UNIDAD, jornal="10"), trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10")],
                revisadas={("MANUALES", None)})
    assert cruce.estados == ["facturada"]
    assert cruce.diferencia_revisada is True


def test_sin_grupo_se_revisa_con_grupo_nulo():
    cruce = mes([trabajo(DESMALEZADO, unidades="2")], [linea(DESMALEZADO, "hectareas", "3")],
                revisadas={(None, "hectareas")})
    assert cruce.superan == {(None, "hectareas")}
    assert cruce.diferencia_revisada is True


def test_las_que_superan():
    cruce = mes([trabajo(PODA, jornal="10"), trabajo(TRACTOR, maquina="5")],
                [linea(PODA, "horas_peon", "20"), linea(TRACTOR, "horas_tractor", "5")])
    assert cruce.superan == {("MANUALES", "horas_peon")}


# ─── El filtro por día (spec de la E3a por grupo, decisiones 6 a 8) ─────────

DIA_1 = date(2026, 9, 1)
DIA_10 = date(2026, 9, 10)
DIA_15 = date(2026, 9, 15)
DIA_16 = date(2026, 9, 16)
DIA_30 = date(2026, 9, 30)


def test_con_desde_y_hasta_del_mes_entero_da_lo_mismo_que_sin_filtro():
    trabajado = [trabajo(PODA, jornal="10"), trabajo(RALEO, unidades="500")]
    lineas = [linea(PODA, "horas_peon", "20", comprobante_id=1),
              linea(RALEO, "plantas", "500", comprobante_id=2, fecha=DIA_16)]
    sin_filtro = mes(trabajado, lineas)
    con_filtro = mes(trabajado, lineas, desde=DIA_1, hasta=DIA_30)
    assert con_filtro == sin_filtro
    assert con_filtro.comprobantes_fuera == []
    assert all(not g.fuera_del_filtro for g in con_filtro.grupos)


@pytest.mark.parametrize("desde, hasta, cuenta", [
    (DIA_1, DIA_15, True),
    (DIA_1, DIA_30, True),
    (DIA_1, DIA_10, False),
])
def test_una_linea_del_1_entra_con_la_quincena_y_el_mes_y_no_con_del_1_al_10(
        desde, hasta, cuenta):
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10", fecha=DIA_1)], desde=desde, hasta=hasta)
    g = grupo(cruce, "MANUALES", "horas_peon")
    assert g.fuera_del_filtro is not cuenta
    assert (len(cruce.lineas) == 1) is cuenta


def test_lo_que_cae_en_parte_no_cuenta_y_su_grupo_queda_fuera_del_filtro():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10", "900", comprobante_id=80,
                       numero="0001-00001234")],
                desde=DIA_1, hasta=DIA_10)
    g = grupo(cruce, "MANUALES", "horas_peon")
    assert g.fuera_del_filtro is True
    assert (g.diferencia, g.diferencia_pct, g.supera) == (None, None, False)
    assert g.campo == D("10")
    assert cruce.lineas == []
    assert cruce.facturado_neto == D("0")
    assert cruce.superan == set()
    assert cruce.comprobantes_fuera == [
        {"id": 80, "tipo": "factura", "numero": "0001-00001234",
         "desde": DIA_1, "hasta": DIA_15}]


def test_el_grupo_mixto_no_se_compara_y_no_avisa():
    # RALEO entra entera (del 16 al 30) y PODA cae en parte: el grupo MANUALES
    # en horas no se compara aunque tenga una Línea adentro.
    cruce = mes([trabajo(PODA, jornal="10"), trabajo(RALEO, jornal="10"),
                 trabajo(TRACTOR, maquina="5")],
                [linea(PODA, "horas_peon", "10", fecha=DIA_1),
                 linea(RALEO, "horas_peon", "30", fecha=DIA_16),
                 linea(TRACTOR, "horas_tractor", "9", fecha=DIA_16)],
                desde=DIA_10, hasta=DIA_30)
    mixto = grupo(cruce, "MANUALES", "horas_peon")
    assert mixto.fuera_del_filtro is True
    assert mixto.facturado == D("30")
    assert (mixto.diferencia, mixto.diferencia_pct, mixto.supera) == (None, None, False)
    tractor = grupo(cruce, "MAQUINARIA", "horas_tractor")
    assert tractor.fuera_del_filtro is False
    assert tractor.supera is True
    assert cruce.superan == {("MAQUINARIA", "horas_tractor")}
    assert cruce.estados == ["con_diferencia"]


def test_una_linea_entera_afuera_se_ignora_sin_aviso():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10", fecha=DIA_16)],
                desde=DIA_1, hasta=DIA_15)
    assert cruce.comprobantes_fuera == []
    assert grupo(cruce, "MANUALES", "horas_peon").fuera_del_filtro is False
    assert cruce.estados == ["pendiente_de_facturar"]


def test_una_linea_en_parte_sin_partes_igual_da_su_grupo_fuera_del_filtro():
    cruce = mes([], [linea(PODA, "horas_peon", "10")], desde=DIA_1, hasta=DIA_10)
    g = grupo(cruce, "MANUALES", "horas_peon")
    assert g.fuera_del_filtro is True
    assert g.partes == 0


def test_con_todo_afuera_es_sin_comparar_y_no_pendiente_de_facturar():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10")], desde=DIA_1, hasta=DIA_10)
    assert cruce.estados == ["sin_comparar"]


def test_sin_comparar_lleva_falta_comprobante_al_lado():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10", comprobante_id=81, adjuntos=0,
                       numero="0001-00000081")],
                desde=DIA_1, hasta=DIA_10)
    assert cruce.estados == ["falta_comprobante", "sin_comparar"]
    assert cruce.comprobantes_sin_adjunto == [
        {"id": 81, "tipo": "factura", "numero": "0001-00000081"}]


def test_un_grupo_afuera_y_otro_solo_con_partes_es_con_diferencia():
    cruce = mes([trabajo(PODA, jornal="10"), trabajo(TRACTOR, maquina="5")],
                [linea(PODA, "horas_peon", "10")], desde=DIA_1, hasta=DIA_10)
    assert grupo(cruce, "MAQUINARIA", "horas_tractor").supera is True
    assert cruce.estados == ["con_diferencia"]


def test_una_nota_de_credito_en_parte_afuera_tampoco_cuenta():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10", comprobante_id=90),
                 linea(PODA, "horas_peon", "4", tipo="nota_credito", comprobante_id=91,
                       fecha=DIA_16, numero="0001-00000091")],
                desde=DIA_1, hasta=date(2026, 9, 20))
    g = grupo(cruce, "MANUALES", "horas_peon")
    assert g.fuera_del_filtro is True
    assert g.facturado == D("10")
    assert [c["id"] for c in cruce.comprobantes_fuera] == [91]
    assert cruce.comprobantes_fuera[0]["tipo"] == "nota_credito"
    assert (cruce.comprobantes_fuera[0]["desde"], cruce.comprobantes_fuera[0]["hasta"]) == (
        DIA_16, DIA_30)


def test_un_comprobante_con_lineas_del_1_y_del_16_cuenta_por_quincena():
    lineas = [linea(PODA, "horas_peon", "10", comprobante_id=95, fecha=DIA_1),
              linea(PODA, "horas_peon", "7", comprobante_id=95, fecha=DIA_16)]
    primera = mes([trabajo(PODA, jornal="10")], lineas, desde=DIA_1, hasta=DIA_15)
    assert grupo(primera, "MANUALES", "horas_peon").facturado == D("10")
    assert primera.comprobantes_fuera == []
    assert primera.estados == ["facturada"]


def test_un_comprobante_con_dos_quincenas_en_parte_avisa_una_vez_con_las_dos():
    lineas = [linea(PODA, "horas_peon", "10", comprobante_id=96, fecha=DIA_1),
              linea(PODA, "horas_peon", "7", comprobante_id=96, fecha=DIA_16)]
    cruce = mes([trabajo(PODA, jornal="10")], lineas,
                desde=date(2026, 9, 5), hasta=date(2026, 9, 20))
    assert [(c["id"], c["desde"], c["hasta"]) for c in cruce.comprobantes_fuera] == [
        (96, DIA_1, DIA_30)]


def test_los_comprobantes_fuera_van_por_periodo_y_por_id():
    lineas = [linea(PODA, "horas_peon", "1", comprobante_id=12, fecha=DIA_16),
              linea(PODA, "horas_peon", "1", comprobante_id=11, fecha=DIA_16),
              linea(RALEO, "horas_peon", "1", comprobante_id=13, fecha=DIA_1)]
    cruce = mes([], lineas, desde=date(2026, 9, 5), hasta=date(2026, 9, 20))
    assert [c["id"] for c in cruce.comprobantes_fuera] == [13, 11, 12]


def test_una_linea_que_no_cuenta_no_avisa_aunque_caiga_en_parte():
    cruce = mes([trabajo(PODA, jornal="10")],
                [linea(PODA, "bins", "3"), linea(INTERNA, "horas_peon", "2"),
                 linea(PODA, "horas_peon", "1", pendiente_de_facturar=True)],
                desde=DIA_1, hasta=DIA_10)
    assert cruce.comprobantes_fuera == []
    assert cruce.estados == ["pendiente_de_facturar"]


def test_en_un_mes_en_gris_el_grupo_queda_fuera_del_filtro_y_el_estado_no_cambia():
    julio = date(2026, 7, 1)
    cruce = mes([trabajo(PODA, jornal="10", mes=julio)],
                [linea(PODA, "horas_peon", "10", fecha=julio)],
                el_mes=julio, desde=julio, hasta=date(2026, 7, 10))
    assert grupo(cruce, "MANUALES", "horas_peon").fuera_del_filtro is True
    assert cruce.estados == ["antes_del_corte"]


def test_el_cruce_trae_su_recorte():
    cruce = mes([trabajo(PODA, jornal="10")], desde=DIA_1, hasta=DIA_10)
    assert (cruce.desde, cruce.hasta) == (DIA_1, DIA_10)
    entero = mes([trabajo(PODA, jornal="10")])
    assert (entero.desde, entero.hasta) == (DIA_1, DIA_30)


def test_cruzar_recorta_el_filtro_a_cada_mes():
    trabajado = [trabajo(PODA, jornal="10", mes=AGOSTO), trabajo(PODA, jornal="10")]
    lineas = [linea(PODA, "horas_peon", "10", fecha=date(2026, 8, 16), comprobante_id=1),
              linea(PODA, "horas_peon", "10", fecha=DIA_1, comprobante_id=2)]
    cruces = cruzar(trabajado, lineas, TAREAS, umbral_pct=UMBRAL, mes_corte=MES_CORTE,
                    hoy=HOY,
                    desde=date(2026, 8, 20), hasta=DIA_15)
    por_mes = {c.mes: c for c in cruces}
    assert (por_mes[AGOSTO].desde, por_mes[AGOSTO].hasta) == (
        date(2026, 8, 20), date(2026, 8, 31))
    assert [c["id"] for c in por_mes[AGOSTO].comprobantes_fuera] == [1]
    assert (por_mes[SEPTIEMBRE].desde, por_mes[SEPTIEMBRE].hasta) == (DIA_1, DIA_15)
    assert por_mes[SEPTIEMBRE].estados == ["facturada"]


# ─── cruzar(): todos los Clientes y meses del Resumen ───────────────────────

def test_cruzar_arma_un_cruce_por_cliente_y_mes_sin_tocar_lo_recibido():
    otro = 8
    trabajado = [trabajo(PODA, jornal="10"),
                 trabajo(PODA, jornal="4", mes=AGOSTO),
                 trabajo(SIN_UNIDAD, jornal="1", cliente_id=otro),
                 trabajo(SIN_UNIDAD, jornal="1")]
    lineas = [linea(PODA, "horas_peon", "10"),
              linea(TRACTOR, "horas_tractor", "3", cliente_id=otro, fecha=date(2026, 8, 16))]
    antes = (copy.deepcopy(trabajado), copy.deepcopy(lineas))
    cruces = cruzar(trabajado, lineas, TAREAS, umbral_pct=UMBRAL, mes_corte=MES_CORTE,
                    hoy=HOY,
                    revisiones={(CLIENTE, SEPTIEMBRE): {("MANUALES", None)}})
    assert [(c.cliente_id, c.mes) for c in cruces] == [
        (CLIENTE, AGOSTO), (otro, AGOSTO), (CLIENTE, SEPTIEMBRE), (otro, SEPTIEMBRE)]
    por_clave = {(c.cliente_id, c.mes): c for c in cruces}
    assert por_clave[(CLIENTE, SEPTIEMBRE)].diferencia_revisada is True
    assert por_clave[(otro, AGOSTO)].estados == ["con_diferencia"]
    assert por_clave[(CLIENTE, AGOSTO)].estados == ["pendiente_de_facturar"]
    assert tareas_sin_unidad(cruces) == [
        {"tarea_id": SIN_UNIDAD, "nombre": "ATADO", "clientes": 2}]
    assert (trabajado, lineas) == antes
