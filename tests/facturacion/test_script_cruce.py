"""El script de aceptación del Cruce contra Power BI (spec de la E3a por
grupo, decisión 9; antes, plan de la E3, decisión 7 y paso A11).

Lo que cuidan estos tests:
- el CSV principal es una fila por (Cliente, mes, grupo, unidad), la misma
  línea del Resumen: sale del cálculo del servicio (las mismas líneas que
  resumen(), en su orden) y no de una cuenta propia;
- el segundo CSV, por tarea, trae la medida "como Power BI" (la de la Unidad
  sugerida) al lado de la del módulo (la de la unidad de la fila), para
  separar las diferencias esperables de los errores;
- --desde y --hasta van en meses y el campo se lee por día, del 1 del primer
  mes al último día del último;
- lo facturado sale del lector del servicio y pasa por el motor: una Nota de
  crédito resta cantidad y neto, y la cosecha no entra;
- la salida sólo se escribe dentro de fuentes/, que está fuera de git: una
  ruta afuera se rechaza antes de abrir ninguna base;
- se imprime el aviso de que la salida tiene nombres de clientes.

El script se carga desde su archivo. Ningún test se conecta a una base real
ni al campo: la sesión propia es SQLite en memoria, la consulta del campo es
falsa y fuentes/ es una carpeta temporal. Datos inventados.
"""
import csv
import importlib.util
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.modulos.facturacion import fechas
from app.modulos.facturacion.models import (
    Comprobante, Configuracion, LineaComprobante, RevisionDiferencia, RevisionGrupo,
)
from app.modulos.facturacion.services import consulta_externa
from app.modulos.facturacion.services.resumen_service import ResumenService

D = Decimal

RUTA_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "cruce_facturacion.py"

SEPTIEMBRE = date(2026, 9, 1)
AGOSTO = date(2026, 8, 1)
JULIO = date(2026, 7, 1)

PODA = 101          # sugerida horas de peón, grupo MANUALES
ATADO = 102         # sugerida horas de peón, grupo MANUALES
RALEO = 103         # sugerida plantas, sin grupo
CARGA_BINS = 108    # sugerida de cosecha
DESMALEZADO = 110   # sugerida hectáreas, grupo PULVERIZACIÓN
UNO, DOS = 1, 2

ENCABEZADOS_GRUPOS = [
    "cliente_id", "cliente", "mes", "desde", "hasta", "estado",
    "diferencia_revisada", "lineas_superan", "grupo", "unidad", "campo",
    "facturado", "diferencia", "diferencia_pct", "supera", "fuera_del_filtro",
]
ENCABEZADOS_TAREAS = [
    "cliente_id", "cliente", "mes", "grupo", "tarea_id", "tarea", "unidad",
    "unidad_sugerida", "medida_como_power_bi", "medida_del_modulo",
    "cantidad_facturada", "neto",
]


def _cargar_script():
    spec = importlib.util.spec_from_file_location("cruce_facturacion", RUTA_SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def script():
    return _cargar_script()


@pytest.fixture(autouse=True)
def hoy_15_de_octubre(monkeypatch):
    # Octubre es el mes en curso: septiembre ya se controla.
    monkeypatch.setattr(fechas, "_ahora",
                        lambda: datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc))


@pytest.fixture(autouse=True)
def cache_limpia():
    consulta_externa.invalidar_cache()
    yield
    consulta_externa.invalidar_cache()


@pytest.fixture()
def fuentes(script, tmp_path, monkeypatch):
    carpeta = tmp_path / "fuentes"
    carpeta.mkdir()
    monkeypatch.setattr(script, "FUENTES", carpeta)
    return carpeta


@pytest.fixture()
def fabrica():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine)
    yield fabrica
    engine.dispose()


class ConsultaFalsa:
    """El campo: clientes, el maestro de tareas y lo trabajado por mes."""

    CLIENTES = [
        {"id": UNO, "nombre": "CLIENTE UNO", "activo": True},
        {"id": DOS, "nombre": "CLIENTE DOS", "activo": False},
    ]
    TAREAS = [
        {"tarea_id": PODA, "nombre": "PODA", "grupo_tarea": "MANUALES",
         "unidad_sugerida": "horas_peon", "no_facturable": False},
        {"tarea_id": ATADO, "nombre": "ATADO", "grupo_tarea": "MANUALES",
         "unidad_sugerida": "horas_peon", "no_facturable": False},
        {"tarea_id": RALEO, "nombre": "RALEO", "grupo_tarea": None,
         "unidad_sugerida": "plantas", "no_facturable": False},
        {"tarea_id": CARGA_BINS, "nombre": "CARGA DE BINS", "grupo_tarea": "COSECHA",
         "unidad_sugerida": "bins", "no_facturable": False},
        {"tarea_id": DESMALEZADO, "nombre": "DESMALEZADO", "grupo_tarea": "PULVERIZACIÓN",
         "unidad_sugerida": "hectareas", "no_facturable": False},
    ]

    def __init__(self, trabajado):
        self.trabajado = trabajado
        self.pedidos = []

    def clientes(self, incluir_baja=False):
        return [c for c in self.CLIENTES if incluir_baja or c["activo"]]

    def trabajado_por_mes(self, desde, hasta):
        """Por días, como el campo desde el filtro por día: cada fila trae el
        día en que se trabajó, que no sale (el campo agrupa por mes)."""
        self.pedidos.append((desde, hasta))
        return {"leido_en": datetime(2026, 10, 15, 12, 0), "filas": [
            {k: v for k, v in f.items() if k != "dia"} for f in self.trabajado
            if desde <= f["dia"] <= hasta]}

    def tareas_cruce(self):
        return {"leido_en": datetime(2026, 10, 15, 12, 0), "filas": list(self.TAREAS)}


def _trabajo(cliente_id, tarea_id, mes, *, jornal="0", maquina="0", unidades="0",
             tancadas="0", partes=1, dia=20):
    """Una fila de lo trabajado en el mes; `dia` es el día del mes en que se
    trabajó (por defecto el 20, en la 2.ª quincena)."""
    return {"cliente_id": cliente_id, "tarea_id": tarea_id, "mes": mes,
            "dia": mes.replace(day=dia),
            "horas_jornal": D(jornal), "horas_maquina": D(maquina),
            "unidades": D(unidades), "tancadas": D(tancadas), "partes": partes}


_numeros = iter(range(1, 10_000))


def _comprobante(fabrica, cliente_id, lineas, *, tipo="factura"):
    """Un Comprobante con sus Líneas, cada una (tarea_id, unidad, fecha,
    cantidad, importe). Histórico, para que no avise Falta comprobante."""
    n = next(_numeros)
    sesion = fabrica()
    try:
        sesion.add(Comprobante(
            tipo=tipo, cliente_id=cliente_id, cliente_nombre=f"COPIA {cliente_id}",
            empresa_emisora="EMPRESA UNO", numero=f"A {n:04d}",
            fecha=date(2026, 10, 2), es_historico=True, pendiente_de_facturar=False,
            clave_identidad=f"P|{n}",
            lineas=[
                LineaComprobante(
                    orden=i, fecha=fecha, tarea_id=tarea_id,
                    tarea_nombre=f"TAREA {tarea_id}", unidad=unidad,
                    cantidad=D(cantidad), precio_unitario=D("1"), importe=D(importe))
                for i, (tarea_id, unidad, fecha, cantidad, importe) in enumerate(lineas, 1)
            ]))
        sesion.commit()
    finally:
        sesion.close()


def _corte_en(fabrica, mes, umbral="5"):
    sesion = fabrica()
    try:
        sesion.add(Configuracion(id=1, umbral_pct=D(umbral), mes_corte=mes,
                                 actualizado_en=datetime(2026, 10, 1, 12, 0)))
        sesion.commit()
    finally:
        sesion.close()


def _sin_base():
    raise AssertionError("no tenía que abrir ninguna base")


def _correr(script, fabrica, consulta, *argumentos):
    return script.main([str(a) for a in argumentos], abrir_sesion=fabrica,
                       consulta=consulta)


def _leer_csv(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo, delimiter=";"))


def _tareas(salida: Path) -> Path:
    """El CSV por tarea, al lado del principal."""
    return salida.with_name(salida.stem + "-tareas" + salida.suffix)


def _fila(filas, cliente, mes, tarea, unidad):
    elegidas = [f for f in filas if (f["cliente"], f["mes"], f["tarea"], f["unidad"])
                == (cliente, mes, tarea, unidad)]
    assert len(elegidas) == 1, filas
    return elegidas[0]


def _linea(filas, cliente, mes, grupo, unidad):
    elegidas = [f for f in filas if (f["cliente"], f["mes"], f["grupo"], f["unidad"])
                == (cliente, mes, grupo, unidad)]
    assert len(elegidas) == 1, filas
    return elegidas[0]


# ─── El CSV por grupo: lo mismo que el Resumen ──────────────────────────────

def _datos_variados(fabrica):
    """Julio antes del corte; agosto con un Cliente Pendiente de facturar;
    septiembre con un grupo de dos tareas que cierra, Sin grupo en dos
    unidades (una supera), una Nota de crédito y una pulverización por
    hectárea sin campo."""
    _corte_en(fabrica, AGOSTO)
    consulta = ConsultaFalsa([
        _trabajo(UNO, PODA, JULIO, jornal="10"),
        _trabajo(DOS, PODA, AGOSTO, jornal="8"),
        _trabajo(UNO, PODA, SEPTIEMBRE, jornal="30", partes=3),
        _trabajo(UNO, ATADO, SEPTIEMBRE, jornal="10", dia=5),
        _trabajo(UNO, RALEO, SEPTIEMBRE, jornal="12.5", unidades="400", partes=2),
    ])
    _comprobante(fabrica, UNO, [(PODA, "horas_peon", date(2026, 7, 1), "11", "1100")])
    _comprobante(fabrica, UNO, [
        (PODA, "horas_peon", date(2026, 9, 16), "28", "2800"),
        (ATADO, "horas_peon", date(2026, 9, 1), "12", "1200"),
        (RALEO, "horas_peon", date(2026, 9, 1), "12", "1200"),
        (RALEO, "plantas", date(2026, 9, 16), "400", "800"),
        (DESMALEZADO, "hectareas", date(2026, 9, 16), "3", "900"),
    ])
    _comprobante(fabrica, UNO, [(RALEO, "plantas", date(2026, 9, 16), "100", "200")],
                 tipo="nota_credito")
    return consulta


def test_el_csv_por_grupo_da_las_mismas_lineas_que_el_resumen(script, fabrica, fuentes):
    consulta = _datos_variados(fabrica)
    salida = fuentes / "cruce.csv"

    assert _correr(script, fabrica, consulta, "--desde", "2026-07", "--hasta", "2026-09",
                   "--salida", salida) == 0

    sesion = fabrica()
    try:
        resumen = ResumenService(sesion, ConsultaFalsa(consulta.trabajado)).resumen(
            "2026-07-01", "2026-09-30")
    finally:
        sesion.close()
    esperado = [
        [str(f["cliente_id"]), f["cliente_nombre"], f["mes"].strftime("%Y-%m"),
         f["desde"].isoformat(), f["hasta"].isoformat(), ", ".join(f["estados"]),
         "sí" if f["diferencia_revisada"] else "no", str(f["lineas_superan"]),
         g["grupo"], g["unidad"] or "", script._numero(g["campo"]),
         script._numero(g["facturado"]), script._numero(g["diferencia"]),
         script._numero(g["diferencia_pct"]), "sí" if g["supera"] else "no",
         "sí" if g["fuera_del_filtro"] else "no"]
        for f in resumen["filas"] for g in f["grupos"]
    ]
    filas = _leer_csv(salida)

    assert list(filas[0]) == ENCABEZADOS_GRUPOS
    assert [list(f.values()) for f in filas] == esperado
    # Los casos que el Resumen tiene que traer, para que la igualdad no sea
    # entre dos listas vacías.
    assert len(esperado) == 6


def test_cada_linea_trae_campo_facturado_diferencia_supera_y_el_estado(
        script, fabrica, fuentes):
    consulta = _datos_variados(fabrica)
    salida = fuentes / "cruce.csv"

    _correr(script, fabrica, consulta, "--desde", "2026-07", "--hasta", "2026-09",
            "--salida", salida)

    filas = _leer_csv(salida)
    # El orden del Resumen: el mes más nuevo primero; dentro, por grupo, Sin
    # grupo al final, y por unidad.
    assert [(f["cliente"], f["mes"], f["grupo"], f["unidad"]) for f in filas] == [
        ("CLIENTE UNO", "2026-09", "MANUALES", "horas_peon"),
        ("CLIENTE UNO", "2026-09", "PULVERIZACIÓN", "hectareas"),
        ("CLIENTE UNO", "2026-09", "Sin grupo", "horas_peon"),
        ("CLIENTE UNO", "2026-09", "Sin grupo", "plantas"),
        ("CLIENTE DOS", "2026-08", "MANUALES", "horas_peon"),
        ("CLIENTE UNO", "2026-07", "MANUALES", "horas_peon"),
    ]
    # Dos tareas del mismo grupo: 30 + 10 trabajadas, 28 + 12 facturadas.
    assert _linea(filas, "CLIENTE UNO", "2026-09", "MANUALES", "horas_peon") == {
        "cliente_id": "1", "cliente": "CLIENTE UNO", "mes": "2026-09",
        "desde": "2026-09-01", "hasta": "2026-09-30",
        "estado": "con_diferencia", "diferencia_revisada": "no", "lineas_superan": "2",
        "grupo": "MANUALES", "unidad": "horas_peon", "campo": "40", "facturado": "40",
        "diferencia": "0", "diferencia_pct": "0", "supera": "no",
        "fuera_del_filtro": "no"}
    # Facturado por hectárea sin campo: supera y el Dif. % va vacío (la raya).
    hectareas = _linea(filas, "CLIENTE UNO", "2026-09", "PULVERIZACIÓN", "hectareas")
    assert (hectareas["campo"], hectareas["facturado"], hectareas["diferencia"],
            hectareas["diferencia_pct"], hectareas["supera"]) == ("0", "3", "3", "", "sí")
    # La Nota de crédito resta: 400 - 100 plantas contra 400 trabajadas.
    plantas = _linea(filas, "CLIENTE UNO", "2026-09", "Sin grupo", "plantas")
    assert (plantas["facturado"], plantas["diferencia"], plantas["diferencia_pct"],
            plantas["supera"]) == ("300", "-100", "-25", "sí")
    # El RALEO en horas de peón: 12 contra 12,5, por debajo del Umbral.
    peon = _linea(filas, "CLIENTE UNO", "2026-09", "Sin grupo", "horas_peon")
    assert (peon["campo"], peon["diferencia"], peon["diferencia_pct"], peon["supera"]) == (
        "12,5", "-0,5", "-4", "no")
    pendiente = _linea(filas, "CLIENTE DOS", "2026-08", "MANUALES", "horas_peon")
    assert (pendiente["estado"], pendiente["facturado"]) == ("pendiente_de_facturar", "0")
    julio = _linea(filas, "CLIENTE UNO", "2026-07", "MANUALES", "horas_peon")
    assert (julio["estado"], julio["diferencia"], julio["supera"]) == (
        "antes_del_corte", "1", "no")


def test_una_revision_vigente_sale_como_revisada(script, fabrica, fuentes):
    _corte_en(fabrica, AGOSTO)
    consulta = ConsultaFalsa([_trabajo(UNO, PODA, SEPTIEMBRE, jornal="10")])
    _comprobante(fabrica, UNO, [(PODA, "horas_peon", date(2026, 9, 1), "20", "2000")])
    sesion = fabrica()
    try:
        sesion.add(RevisionDiferencia(
            cliente_id=UNO, mes=SEPTIEMBRE, desde=SEPTIEMBRE, hasta=date(2026, 9, 30),
            comentario="Se facturó el doble a propósito.",
            creada_en=datetime(2026, 10, 3, 12, 0),
            grupos=[RevisionGrupo(grupo="MANUALES", unidad="horas_peon")]))
        sesion.commit()
    finally:
        sesion.close()
    salida = fuentes / "cruce.csv"

    _correr(script, fabrica, consulta, "--desde", "2026-09", "--hasta", "2026-09",
            "--salida", salida)

    [fila] = _leer_csv(salida)
    assert (fila["estado"], fila["diferencia_revisada"], fila["supera"]) == (
        "facturada", "sí", "sí")


# ─── El CSV por tarea, para Power BI ────────────────────────────────────────

def test_cada_tarea_trae_la_medida_como_power_bi_y_la_del_modulo(script, fabrica, fuentes):
    # RALEO tiene sugerida plantas (Power BI mide unidades), pero se facturó
    # en horas de peón: el módulo la mide en horas de jornal.
    consulta = ConsultaFalsa([
        _trabajo(UNO, RALEO, SEPTIEMBRE, jornal="12.5", unidades="400", partes=3),
        _trabajo(UNO, PODA, SEPTIEMBRE, jornal="40", partes=2),
    ])
    _comprobante(fabrica, UNO, [
        (RALEO, "horas_peon", date(2026, 9, 1), "12", "1200"),
        (PODA, "horas_peon", date(2026, 9, 16), "40", "4000.5"),
    ])
    salida = fuentes / "cruce.csv"

    assert _correr(script, fabrica, consulta, "--desde", "2026-09", "--hasta", "2026-09",
                   "--salida", salida) == 0

    filas = _leer_csv(_tareas(salida))
    assert list(filas[0]) == ENCABEZADOS_TAREAS
    raleo = _fila(filas, "CLIENTE UNO", "2026-09", "RALEO", "horas_peon")
    assert raleo == {
        "cliente_id": "1", "cliente": "CLIENTE UNO", "mes": "2026-09",
        "grupo": "Sin grupo", "tarea_id": str(RALEO), "tarea": "RALEO",
        "unidad": "horas_peon", "unidad_sugerida": "plantas",
        "medida_como_power_bi": "400", "medida_del_modulo": "12,5",
        "cantidad_facturada": "12", "neto": "1200,00"}
    poda = _fila(filas, "CLIENTE UNO", "2026-09", "PODA", "horas_peon")
    assert (poda["grupo"], poda["medida_como_power_bi"], poda["medida_del_modulo"],
            poda["cantidad_facturada"], poda["neto"]) == (
        "MANUALES", "40", "40", "40", "4000,50")
    assert consulta.pedidos == [(SEPTIEMBRE, date(2026, 9, 30))]


def test_las_tareas_suman_lo_mismo_que_su_linea_por_grupo(script, fabrica, fuentes):
    consulta = _datos_variados(fabrica)
    salida = fuentes / "cruce.csv"

    _correr(script, fabrica, consulta, "--desde", "2026-07", "--hasta", "2026-09",
            "--salida", salida)

    tareas = _leer_csv(_tareas(salida))
    manuales = [f for f in tareas if (f["cliente"], f["mes"], f["grupo"])
                == ("CLIENTE UNO", "2026-09", "MANUALES")]
    assert [(f["tarea"], f["medida_del_modulo"], f["cantidad_facturada"]) for f in manuales] == [
        ("ATADO", "10", "12"), ("PODA", "30", "28")]


def test_una_tarea_sin_facturar_sale_con_su_unidad_sugerida(script, fabrica, fuentes):
    consulta = ConsultaFalsa([_trabajo(DOS, PODA, AGOSTO, jornal="8")])
    salida = fuentes / "cruce.csv"

    _correr(script, fabrica, consulta, "--desde", "2026-08", "--hasta", "2026-09",
            "--salida", salida)

    fila = _fila(_leer_csv(_tareas(salida)), "CLIENTE DOS", "2026-08", "PODA", "horas_peon")
    assert (fila["medida_como_power_bi"], fila["medida_del_modulo"],
            fila["cantidad_facturada"], fila["neto"]) == ("8", "8", "0", "0,00")


def test_la_nota_de_credito_resta_cantidad_y_neto(script, fabrica, fuentes):
    consulta = ConsultaFalsa([_trabajo(UNO, RALEO, SEPTIEMBRE, unidades="10")])
    _comprobante(fabrica, UNO, [(RALEO, "plantas", date(2026, 9, 1), "10", "25")])
    _comprobante(fabrica, UNO, [(RALEO, "plantas", date(2026, 9, 1), "4", "10")],
                 tipo="nota_credito")
    salida = fuentes / "cruce.csv"

    _correr(script, fabrica, consulta, "--desde", "2026-09", "--hasta", "2026-09",
            "--salida", salida)

    fila = _fila(_leer_csv(_tareas(salida)), "CLIENTE UNO", "2026-09", "RALEO", "plantas")
    assert (fila["cantidad_facturada"], fila["neto"]) == ("6", "15,00")
    [linea] = _leer_csv(salida)
    assert linea["facturado"] == "6"


def test_la_cosecha_no_entra(script, fabrica, fuentes):
    # Trabajo de una tarea con sugerida de cosecha y una Línea en bins: ni una
    # ni otra dan fila. Lo demás del mes sí sale.
    consulta = ConsultaFalsa([
        _trabajo(UNO, CARGA_BINS, SEPTIEMBRE, unidades="30"),
        _trabajo(UNO, PODA, SEPTIEMBRE, jornal="5"),
    ])
    _comprobante(fabrica, UNO, [
        (CARGA_BINS, "bins", date(2026, 9, 1), "30", "3000"),
        (PODA, "bins", date(2026, 9, 1), "2", "200"),
    ])
    salida = fuentes / "cruce.csv"

    _correr(script, fabrica, consulta, "--desde", "2026-09", "--hasta", "2026-09",
            "--salida", salida)

    tareas = _leer_csv(_tareas(salida))
    assert [(f["tarea"], f["unidad"]) for f in tareas] == [("PODA", "horas_peon")]
    assert tareas[0]["neto"] == "0,00"
    grupos = _leer_csv(salida)
    assert [(f["grupo"], f["unidad"]) for f in grupos] == [("MANUALES", "horas_peon")]


# ─── Los meses de la línea de comandos ─────────────────────────────────────

def test_el_ultimo_mes_se_lee_entero(script, fabrica, fuentes):
    # --desde y --hasta van en meses, y el campo se lee por día: del 1 del
    # primer mes al último día del último. Lo trabajado el 30 de septiembre
    # tiene que entrar.
    consulta = ConsultaFalsa([
        _trabajo(UNO, PODA, AGOSTO, jornal="8", dia=1),
        _trabajo(UNO, PODA, SEPTIEMBRE, jornal="5", dia=30),
    ])
    salida = fuentes / "cruce.csv"

    assert _correr(script, fabrica, consulta, "--desde", "2026-08", "--hasta", "2026-09",
                   "--salida", salida) == 0

    assert consulta.pedidos == [(AGOSTO, date(2026, 9, 30))]
    filas = _leer_csv(salida)
    assert {f["mes"] for f in filas} == {"2026-08", "2026-09"}
    assert {(f["desde"], f["hasta"]) for f in filas} == {
        ("2026-08-01", "2026-08-31"), ("2026-09-01", "2026-09-30")}


@pytest.mark.parametrize("argumentos", [
    ["--desde", "2025-09", "--hasta", "2026-09"],   # 13 meses
    ["--desde", "2026-10", "--hasta", "2026-11"],   # pasa del mes en curso
])
def test_un_rango_que_el_resumen_no_acepta_sale_con_1_sin_leer_el_campo(
        script, fabrica, fuentes, capsys, argumentos):
    consulta = ConsultaFalsa([])

    assert _correr(script, fabrica, consulta, *argumentos) == 1

    assert consulta.pedidos == []
    assert list(fuentes.iterdir()) == []
    assert "No se escribió nada" in capsys.readouterr().out


# ─── La salida y el aviso ───────────────────────────────────────────────────

@pytest.mark.parametrize("afuera", ["otra/cruce.csv", "fuentes/../cruce.csv"])
def test_una_salida_fuera_de_fuentes_se_rechaza_sin_abrir_ninguna_base(
        script, fuentes, tmp_path, capsys, afuera):
    salida = tmp_path / afuera

    salida_del_script = script.main(
        ["--desde", "2026-09", "--hasta", "2026-09", "--salida", str(salida)],
        abrir_sesion=_sin_base, consulta=_sin_base)

    assert salida_del_script == 1
    assert not salida.exists()
    assert not _tareas(salida).exists()
    assert "fuentes" in capsys.readouterr().out


def test_por_defecto_escribe_los_dos_csv_dentro_de_fuentes(script, fabrica, fuentes):
    consulta = ConsultaFalsa([_trabajo(UNO, PODA, SEPTIEMBRE, jornal="5")])

    assert _correr(script, fabrica, consulta, "--desde", "2026-08",
                   "--hasta", "2026-09") == 0

    escritos = sorted(p.name for p in fuentes.iterdir())
    assert escritos == ["cruce-2026-08-2026-09-tareas.csv", "cruce-2026-08-2026-09.csv"]
    assert len(_leer_csv(fuentes / "cruce-2026-08-2026-09.csv")) == 1
    assert len(_leer_csv(fuentes / "cruce-2026-08-2026-09-tareas.csv")) == 1


def test_se_imprime_el_aviso_de_nombres_de_clientes(script, fabrica, fuentes, capsys):
    consulta = ConsultaFalsa([_trabajo(UNO, PODA, SEPTIEMBRE, jornal="5")])

    _correr(script, fabrica, consulta, "--desde", "2026-09", "--hasta", "2026-09",
            "--salida", fuentes / "cruce.csv")

    consola = capsys.readouterr().out
    assert "nombres de clientes" in consola
    assert "nunca se pega" in consola
    # Por consola no salen los nombres: sólo van al CSV.
    assert "CLIENTE UNO" not in consola


@pytest.mark.parametrize("argumentos", [
    ["--desde", "2026-13", "--hasta", "2026-09"],
    ["--desde", "2026-09", "--hasta", "2026-08"],
])
def test_un_rango_invalido_sale_con_1_sin_abrir_ninguna_base(script, fuentes, capsys,
                                                              argumentos):
    assert script.main(argumentos, abrir_sesion=_sin_base, consulta=_sin_base) == 1
    assert list(fuentes.iterdir()) == []
