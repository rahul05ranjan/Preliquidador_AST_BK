"""El script de aceptación del Cruce contra Power BI (plan de la E3,
decisión 7 y paso A11).

Lo que cuidan estos tests:
- cada fila del CSV (Cliente, mes, tarea y unidad) trae la medida "como Power
  BI" (la de la Unidad sugerida) al lado de la del módulo (la de la unidad de
  la fila), para separar las diferencias esperables de los errores;
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
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.modulos.facturacion.models import Comprobante, LineaComprobante

D = Decimal

RUTA_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "cruce_facturacion.py"

SEPTIEMBRE = date(2026, 9, 1)
AGOSTO = date(2026, 8, 1)

PODA = 101          # sugerida horas de peón
RALEO = 103         # sugerida plantas
CARGA_BINS = 108    # sugerida de cosecha
UNO, DOS = 1, 2


def _cargar_script():
    spec = importlib.util.spec_from_file_location("cruce_facturacion", RUTA_SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def script():
    return _cargar_script()


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
        {"tarea_id": RALEO, "nombre": "RALEO", "grupo_tarea": None,
         "unidad_sugerida": "plantas", "no_facturable": False},
        {"tarea_id": CARGA_BINS, "nombre": "CARGA DE BINS", "grupo_tarea": "COSECHA",
         "unidad_sugerida": "bins", "no_facturable": False},
    ]

    def __init__(self, trabajado):
        self.trabajado = trabajado
        self.pedidos = []

    def clientes(self, incluir_baja=False):
        return [c for c in self.CLIENTES if incluir_baja or c["activo"]]

    def trabajado_por_mes(self, desde, hasta):
        self.pedidos.append((desde, hasta))
        return {"leido_en": datetime(2026, 10, 15, 12, 0), "filas": [
            f for f in self.trabajado
            if desde.replace(day=1) <= f["mes"] <= hasta.replace(day=1)]}

    def tareas_cruce(self):
        return {"leido_en": datetime(2026, 10, 15, 12, 0), "filas": list(self.TAREAS)}


def _trabajo(cliente_id, tarea_id, mes, *, jornal="0", maquina="0", unidades="0",
             tancadas="0", partes=1):
    return {"cliente_id": cliente_id, "tarea_id": tarea_id, "mes": mes,
            "horas_jornal": D(jornal), "horas_maquina": D(maquina),
            "unidades": D(unidades), "tancadas": D(tancadas), "partes": partes}


_numeros = iter(range(1, 10_000))


def _comprobante(fabrica, cliente_id, lineas, *, tipo="factura"):
    """Un Comprobante con sus Líneas, cada una (tarea_id, unidad, fecha,
    cantidad, importe)."""
    n = next(_numeros)
    sesion = fabrica()
    try:
        sesion.add(Comprobante(
            tipo=tipo, cliente_id=cliente_id, cliente_nombre=f"COPIA {cliente_id}",
            empresa_emisora="EMPRESA UNO", numero=f"A {n:04d}",
            fecha=date(2026, 10, 2), es_historico=False, pendiente_de_facturar=False,
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


def _sin_base():
    raise AssertionError("no tenía que abrir ninguna base")


def _correr(script, fabrica, consulta, *argumentos):
    return script.main([str(a) for a in argumentos], abrir_sesion=fabrica,
                       consulta=consulta)


def _leer_csv(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo, delimiter=";"))


def _fila(filas, cliente, mes, tarea, unidad):
    elegidas = [f for f in filas if (f["cliente"], f["mes"], f["tarea"], f["unidad"])
                == (cliente, mes, tarea, unidad)]
    assert len(elegidas) == 1, filas
    return elegidas[0]


# ─── Las filas del CSV ──────────────────────────────────────────────────────

def test_cada_fila_trae_la_medida_como_power_bi_y_la_del_modulo(script, fabrica, fuentes):
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

    filas = _leer_csv(salida)
    assert list(filas[0]) == [
        "cliente_id", "cliente", "mes", "grupo", "tarea_id", "tarea", "unidad",
        "unidad_sugerida", "medida_como_power_bi", "medida_del_modulo",
        "cantidad_facturada", "neto"]
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
    assert consulta.pedidos == [(SEPTIEMBRE, SEPTIEMBRE)]


def test_una_tarea_sin_facturar_sale_con_su_unidad_sugerida(script, fabrica, fuentes):
    consulta = ConsultaFalsa([_trabajo(DOS, PODA, AGOSTO, jornal="8")])
    salida = fuentes / "cruce.csv"

    _correr(script, fabrica, consulta, "--desde", "2026-08", "--hasta", "2026-09",
            "--salida", salida)

    fila = _fila(_leer_csv(salida), "CLIENTE DOS", "2026-08", "PODA", "horas_peon")
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

    fila = _fila(_leer_csv(salida), "CLIENTE UNO", "2026-09", "RALEO", "plantas")
    assert (fila["cantidad_facturada"], fila["neto"]) == ("6", "15,00")


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

    filas = _leer_csv(salida)
    assert [(f["tarea"], f["unidad"]) for f in filas] == [("PODA", "horas_peon")]
    assert all(f["unidad"] not in ("bins", "bins_c", "bins_m", "viajes") for f in filas)
    assert filas[0]["neto"] == "0,00"


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
    assert "fuentes" in capsys.readouterr().out


def test_por_defecto_escribe_dentro_de_fuentes(script, fabrica, fuentes):
    consulta = ConsultaFalsa([_trabajo(UNO, PODA, SEPTIEMBRE, jornal="5")])

    assert _correr(script, fabrica, consulta, "--desde", "2026-08",
                   "--hasta", "2026-09") == 0

    escritos = list(fuentes.iterdir())
    assert len(escritos) == 1
    assert escritos[0].suffix == ".csv"
    assert len(_leer_csv(escritos[0])) == 1


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
