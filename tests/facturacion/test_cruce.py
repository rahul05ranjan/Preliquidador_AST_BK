"""El motor del Cruce (plan de la E3, decisión 6, paso A5).

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

# El corte en agosto y el mes en curso en octubre: septiembre se controla.
MES_CORTE = AGOSTO
MES_EN_CURSO = OCTUBRE
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
        umbral=UMBRAL, tareas=TAREAS):
    """El Cruce de CLIENTE en un mes."""
    return cruzar_mes(
        cliente_id=CLIENTE, mes=el_mes,
        trabajado=medidas_por_tarea(trabajado), lineas=list(lineas),
        tareas=tareas, umbral_pct=umbral, mes_corte=MES_CORTE,
        mes_en_curso=MES_EN_CURSO, revisadas=revisadas)


def fila(cruce, tarea_id, unidad="*"):
    encontradas = [f for f in cruce.filas
                   if f.tarea_id == tarea_id and (unidad == "*" or f.unidad == unidad)]
    assert len(encontradas) == 1, encontradas
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
    assert fila(cruce, PODA).supera is supera


def test_diferencia_y_porcentaje():
    cruce = mes([trabajo(PODA, jornal="80")], [linea(PODA, "horas_peon", "100")])
    f = fila(cruce, PODA)
    assert f.diferencia == D("20")
    assert f.diferencia_pct == D("25.00")


# ─── La tabla "Supera" ──────────────────────────────────────────────────────

def test_con_partes_y_campo_cero_sin_facturado_supera():
    cruce = mes([trabajo(PODA, jornal="0", maquina="5")])
    f = fila(cruce, PODA)
    assert f.campo == D("0")
    assert f.diferencia_pct is None
    assert f.supera is True


def test_la_tarea_sin_unidad_no_tiene_campo_supera_y_va_al_aviso():
    cruce = mes([trabajo(SIN_UNIDAD, jornal="10")],
                [linea(PODA, "horas_peon", "1")])
    f = fila(cruce, SIN_UNIDAD)
    assert f.unidad is None
    assert f.sin_unidad_sugerida is True
    assert f.campo is None
    assert f.diferencia is None and f.diferencia_pct is None
    assert f.supera is True
    assert tareas_sin_unidad([cruce]) == [
        {"tarea_id": SIN_UNIDAD, "nombre": "ATADO", "clientes": 1}]


def test_con_campo_cero_y_algo_facturado_supera():
    cruce = mes([trabajo(PODA, jornal="0", maquina="3")],
                [linea(PODA, "horas_peon", "4")])
    assert fila(cruce, PODA).supera is True


def test_facturado_sin_partes_supera():
    cruce = mes([], [linea(PODA, "horas_peon", "4")])
    f = fila(cruce, PODA)
    assert f.partes == 0
    assert f.campo == D("0")
    assert f.supera is True


def test_sin_partes_y_facturado_cero_no_hay_fila():
    cruce = mes([], [linea(PODA, "horas_peon", "4", "400"),
                     linea(PODA, "horas_peon", "4", "400", tipo="nota_credito")])
    assert cruce.filas == []


# ─── Columnas del Resumen ───────────────────────────────────────────────────

def test_las_columnas_suman_por_unidad_y_la_tarea_sin_unidad_no_suma():
    cruce = mes([trabajo(PODA, jornal="10"),
                 trabajo(TRACTOR, jornal="3", maquina="6"),
                 trabajo(RALEO, jornal="8", unidades="500"),
                 trabajo(DESMALEZADO, unidades="2.5"),
                 trabajo(PULVERIZACION, tancadas="12"),
                 trabajo(SIN_UNIDAD, jornal="99")],
                [linea(RALEO, "horas_peon", "8"), linea(RALEO, "plantas", "500")])
    assert cruce.columnas == {
        "horas_peon": D("18"),   # PODA 10 + RALEO en horas 8
        "horas_tractor": D("6"),
        "plantas": D("500"),
        "hectareas": D("2.5"),
        "tancadas": D("12"),
    }


# ─── Estados del mes ────────────────────────────────────────────────────────

def test_el_orden_de_urgencia():
    assert ESTADOS == ("pendiente_de_facturar", "con_diferencia", "falta_comprobante",
                       "facturada", "mes_en_curso", "antes_del_corte")


def test_antes_del_corte_va_solo_y_no_supera():
    cruce = mes([trabajo(PODA, jornal="10")], [linea(PODA, "horas_peon", "50", adjuntos=0)],
                el_mes=date(2026, 7, 1))
    assert cruce.estados == ["antes_del_corte"]
    assert fila(cruce, PODA).supera is False
    assert cruce.diferencia_revisada is False


def test_mes_en_curso_solo_y_no_supera():
    cruce = mes([trabajo(PODA, jornal="10")], el_mes=OCTUBRE)
    assert cruce.estados == ["mes_en_curso"]
    assert fila(cruce, PODA).supera is False


def test_mes_en_curso_con_falta_comprobante():
    lineas = [linea(PODA, "horas_peon", "10", comprobante_id=50, adjuntos=0,
                    fecha=date(2026, 10, 1), numero="0001-00000050")]
    cruce = mes([trabajo(PODA, jornal="10", mes=OCTUBRE)], lineas, el_mes=OCTUBRE)
    assert cruce.estados == ["falta_comprobante", "mes_en_curso"]
    assert cruce.comprobantes_sin_adjunto == [
        {"id": 50, "tipo": "factura", "numero": "0001-00000050"}]


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
                revisadas={(PODA, "horas_peon")})
    assert cruce.estados == ["facturada"]
    assert cruce.diferencia_revisada is True
    assert fila(cruce, PODA).supera is True


def test_una_tarea_nueva_que_supera_vuelve_a_con_diferencia():
    cruce = mes([trabajo(PODA, jornal="10"), trabajo(TRACTOR, maquina="5")],
                [linea(PODA, "horas_peon", "20"), linea(TRACTOR, "horas_tractor", "9")],
                revisadas={(PODA, "horas_peon")})
    assert cruce.estados == ["con_diferencia"]
    assert cruce.diferencia_revisada is False


def test_la_revision_es_por_tarea_y_unidad():
    cruce = mes([trabajo(PODA, jornal="10")], [linea(PODA, "horas_peon", "20")],
                revisadas={(PODA, "plantas")})
    assert cruce.estados == ["con_diferencia"]


def test_si_ninguna_supera_queda_facturada_sin_nota_aunque_haya_revision():
    cruce = mes([trabajo(PODA, jornal="10")], [linea(PODA, "horas_peon", "10")],
                revisadas={(PODA, "horas_peon")})
    assert cruce.estados == ["facturada"]
    assert cruce.diferencia_revisada is False


def test_la_tarea_sin_unidad_se_revisa_con_unidad_nula():
    cruce = mes([trabajo(SIN_UNIDAD, jornal="10"), trabajo(PODA, jornal="10")],
                [linea(PODA, "horas_peon", "10")],
                revisadas={(SIN_UNIDAD, None)})
    assert cruce.estados == ["facturada"]
    assert cruce.diferencia_revisada is True


def test_las_que_superan():
    cruce = mes([trabajo(PODA, jornal="10"), trabajo(TRACTOR, maquina="5")],
                [linea(PODA, "horas_peon", "20"), linea(TRACTOR, "horas_tractor", "5")])
    assert cruce.superan == {(PODA, "horas_peon")}


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
                    mes_en_curso=MES_EN_CURSO,
                    revisiones={(CLIENTE, SEPTIEMBRE): {(SIN_UNIDAD, None)}})
    assert [(c.cliente_id, c.mes) for c in cruces] == [
        (CLIENTE, AGOSTO), (otro, AGOSTO), (CLIENTE, SEPTIEMBRE), (otro, SEPTIEMBRE)]
    por_clave = {(c.cliente_id, c.mes): c for c in cruces}
    assert por_clave[(CLIENTE, SEPTIEMBRE)].diferencia_revisada is True
    assert por_clave[(otro, AGOSTO)].estados == ["con_diferencia"]
    assert por_clave[(CLIENTE, AGOSTO)].estados == ["pendiente_de_facturar"]
    assert tareas_sin_unidad(cruces) == [
        {"tarea_id": SIN_UNIDAD, "nombre": "ATADO", "clientes": 2}]
    assert (trabajado, lineas) == antes
