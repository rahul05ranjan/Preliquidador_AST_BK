"""El Precio sugerido y la empresa sugerida (plan de la E3, paso A7, y el
contrato de la ruta 18), sobre SQLite en memoria.

Lo que se cuida acá: por cada (tarea, unidad) gana la última Factura del
mismo Cliente, en el orden de la ruta 18 (mes de la Línea descendente,
después la fecha del Comprobante descendente, después el id descendente);
las Notas de crédito, los históricos pendientes de facturar y los otros
Clientes no cuentan, y los históricos sí; si esa última Factura tiene precio
0 o menos, no hay Precio sugerido (paso A7b); y la empresa sugerida es la de
la última Factura que tiene empresa. Datos inventados.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.modulos.facturacion.models import Comprobante, LineaComprobante
from app.modulos.facturacion.services.precios import (
    empresa_sugerida, precios_sugeridos,
)

D = Decimal

PODA = 101
RALEO = 103

UNO, DOS = 1, 2

AGOSTO_1 = date(2026, 8, 1)
SEPTIEMBRE_1 = date(2026, 9, 1)
SEPTIEMBRE_16 = date(2026, 9, 16)
OCTUBRE_1 = date(2026, 10, 1)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)()
    yield sesion
    sesion.close()
    engine.dispose()


_numeros = iter(range(1, 10_000))


def comprobante(db, lineas, *, cliente_id=UNO, tipo="factura", fecha=None,
                empresa="EMPRESA UNO", es_historico=False,
                pendiente_de_facturar=False, id=None):
    """Un Comprobante con sus Líneas, cada una (tarea_id, unidad, fecha de la
    Línea, precio unitario). La cantidad y el importe no importan acá."""
    n = next(_numeros)
    c = Comprobante(
        id=id, tipo=tipo, cliente_id=cliente_id, cliente_nombre=f"COPIA {cliente_id}",
        empresa_emisora=empresa, numero=f"A {n:04d}", fecha=fecha,
        es_historico=es_historico, pendiente_de_facturar=pendiente_de_facturar,
        clave_identidad=f"P|{n}",
        lineas=[
            LineaComprobante(
                orden=i, fecha=fecha_linea, tarea_id=tarea_id,
                tarea_nombre=f"TAREA {tarea_id}", unidad=unidad, cantidad=D("1"),
                precio_unitario=D(precio), importe=D(precio))
            for i, (tarea_id, unidad, fecha_linea, precio) in enumerate(lineas, 1)
        ],
    )
    db.add(c)
    db.commit()
    return c


def precio(db, tarea_id, unidad, cliente_id=UNO):
    return precios_sugeridos(db, cliente_id)[(tarea_id, unidad)]["precio_unitario"]


# ─── Precio sugerido ────────────────────────────────────────────────────────

def test_sin_facturas_no_hay_precios(db):
    assert precios_sugeridos(db, UNO) == {}


def test_gana_la_ultima_factura_del_cliente_por_tarea_y_unidad(db):
    vieja = comprobante(db, [(PODA, "horas_peon", AGOSTO_1, "100"),
                             (RALEO, "plantas", AGOSTO_1, "7")],
                        fecha=date(2026, 8, 20))
    nueva = comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "120"),
                             (PODA, "hectareas", SEPTIEMBRE_1, "900")],
                        fecha=date(2026, 9, 20))

    precios = precios_sugeridos(db, UNO)

    assert precios == {
        (PODA, "horas_peon"): {
            "tarea_id": PODA, "unidad": "horas_peon", "precio_unitario": D("120"),
            "comprobante_id": nueva.id, "numero": nueva.numero,
            "fecha": date(2026, 9, 20)},
        # La misma tarea en otra unidad es otro precio.
        (PODA, "hectareas"): {
            "tarea_id": PODA, "unidad": "hectareas", "precio_unitario": D("900"),
            "comprobante_id": nueva.id, "numero": nueva.numero,
            "fecha": date(2026, 9, 20)},
        # Una (tarea, unidad) que la última Factura no trae sale de la anterior.
        (RALEO, "plantas"): {
            "tarea_id": RALEO, "unidad": "plantas", "precio_unitario": D("7"),
            "comprobante_id": vieja.id, "numero": vieja.numero,
            "fecha": date(2026, 8, 20)},
    }


def test_las_notas_de_credito_no_cuentan(db):
    comprobante(db, [(PODA, "horas_peon", AGOSTO_1, "100")], fecha=date(2026, 8, 20))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "5")], tipo="nota_credito",
                fecha=date(2026, 9, 20))

    assert precio(db, PODA, "horas_peon") == D("100")


def test_los_pendientes_de_facturar_no_cuentan(db):
    comprobante(db, [(PODA, "horas_peon", AGOSTO_1, "100")], fecha=date(2026, 8, 20))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "130")], empresa=None,
                es_historico=True, pendiente_de_facturar=True)

    assert precio(db, PODA, "horas_peon") == D("100")


def test_los_otros_clientes_no_cuentan(db):
    comprobante(db, [(PODA, "horas_peon", AGOSTO_1, "100")], fecha=date(2026, 8, 20))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "150")], cliente_id=DOS,
                fecha=date(2026, 9, 20))

    assert precio(db, PODA, "horas_peon") == D("100")
    assert precio(db, PODA, "horas_peon", cliente_id=DOS) == D("150")


def test_los_historicos_cuentan(db):
    comprobante(db, [(PODA, "horas_peon", AGOSTO_1, "100")], fecha=date(2026, 8, 20))
    historico = comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_16, "110")],
                            empresa=None, es_historico=True, fecha=date(2026, 9, 25))

    assert precios_sugeridos(db, UNO)[(PODA, "horas_peon")]["comprobante_id"] == historico.id


# ─── Desempate: el orden de la ruta 18 ──────────────────────────────────────

def test_manda_el_mes_de_la_linea_antes_que_la_fecha_del_comprobante(db):
    # La Factura de fecha más nueva factura un mes más viejo: gana la otra.
    comprobante(db, [(PODA, "horas_peon", AGOSTO_1, "100")], fecha=date(2026, 10, 30))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "120")], fecha=date(2026, 9, 20))

    assert precio(db, PODA, "horas_peon") == D("120")


def test_en_el_mismo_mes_la_quincena_no_desempata(db):
    # Las dos Líneas son de septiembre: el 16 no gana al 1 por ser más nuevo;
    # decide la fecha del Comprobante.
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_16, "100")], fecha=date(2026, 9, 20))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "120")], fecha=date(2026, 9, 28))

    assert precio(db, PODA, "horas_peon") == D("120")


def test_en_el_mismo_mes_gana_la_fecha_del_comprobante_aunque_su_id_sea_menor(db):
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "120")], id=10,
                fecha=date(2026, 9, 28))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "100")], id=20,
                fecha=date(2026, 9, 20))

    assert precio(db, PODA, "horas_peon") == D("120")


def test_con_el_mismo_mes_y_la_misma_fecha_gana_el_id_mayor(db):
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "120")], id=20,
                fecha=date(2026, 9, 20))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "100")], id=10,
                fecha=date(2026, 9, 20))

    assert precio(db, PODA, "horas_peon") == D("120")


def test_un_historico_sin_fecha_pierde_contra_uno_con_fecha_del_mismo_mes(db):
    # Sin fecha no se sabe si es más nuevo: queda último, aunque su id sea mayor.
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "120")], id=10,
                fecha=date(2026, 9, 20))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "100")], id=20, fecha=None,
                empresa=None, es_historico=True)

    assert precio(db, PODA, "horas_peon") == D("120")


def test_dos_lineas_iguales_en_una_factura_gana_la_ultima(db):
    # Misma tarea y unidad dos veces en la misma Factura (por ejemplo, en dos
    # fincas): vale la última del Comprobante.
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "100"),
                     (PODA, "horas_peon", SEPTIEMBRE_1, "120")],
                fecha=date(2026, 9, 20))

    assert precio(db, PODA, "horas_peon") == D("120")


# ─── Precio 0 o menos: sin precio (A7b) ─────────────────────────────────────

@pytest.mark.parametrize("precio_ultimo", ["0", "-50"])
def test_si_la_ultima_factura_tiene_precio_0_o_menos_no_hay_precio(db, precio_ultimo):
    # Un precio 0 suele ser un error de carga: no se sugiere, y tampoco se
    # busca una Factura anterior, aunque tenga precio.
    comprobante(db, [(PODA, "horas_peon", AGOSTO_1, "100")], fecha=date(2026, 8, 20))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, precio_ultimo),
                     (RALEO, "plantas", SEPTIEMBRE_1, "7")],
                fecha=date(2026, 9, 20))

    precios = precios_sugeridos(db, UNO)

    assert (PODA, "horas_peon") not in precios
    # Las otras (tarea, unidad) de esa misma Factura siguen sugiriendo.
    assert precios[(RALEO, "plantas")]["precio_unitario"] == D("7")


def test_un_precio_0_no_cambia_la_empresa_sugerida(db):
    comprobante(db, [(PODA, "horas_peon", AGOSTO_1, "100")], empresa="EMPRESA UNO",
                fecha=date(2026, 8, 20))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "0")], empresa="EMPRESA DOS",
                fecha=date(2026, 9, 20))

    assert empresa_sugerida(db, UNO) == "EMPRESA DOS"


# ─── Empresa sugerida ───────────────────────────────────────────────────────

def test_sin_facturas_no_hay_empresa(db):
    assert empresa_sugerida(db, UNO) is None


def test_la_empresa_es_la_de_la_ultima_factura_con_empresa(db):
    comprobante(db, [(PODA, "horas_peon", AGOSTO_1, "100")], empresa="EMPRESA UNO",
                fecha=date(2026, 8, 20))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "100")], empresa="EMPRESA DOS",
                fecha=date(2026, 9, 20))
    # Más nuevos, pero no cuentan: un histórico sin empresa, una Nota de
    # crédito y una Factura de otro Cliente.
    comprobante(db, [(PODA, "horas_peon", OCTUBRE_1, "100")], empresa=None,
                es_historico=True, fecha=date(2026, 10, 20))
    comprobante(db, [(PODA, "horas_peon", OCTUBRE_1, "100")], tipo="nota_credito",
                empresa="EMPRESA TRES", fecha=date(2026, 10, 21))
    comprobante(db, [(PODA, "horas_peon", OCTUBRE_1, "100")], cliente_id=DOS,
                empresa="EMPRESA CUATRO", fecha=date(2026, 10, 22))

    assert empresa_sugerida(db, UNO) == "EMPRESA DOS"
    assert empresa_sugerida(db, DOS) == "EMPRESA CUATRO"


def test_la_ultima_factura_para_la_empresa_sigue_el_mismo_orden(db):
    # Fecha de Comprobante más nueva, pero factura un mes más viejo: gana la otra.
    comprobante(db, [(PODA, "horas_peon", AGOSTO_1, "100")], empresa="EMPRESA UNO",
                fecha=date(2026, 10, 30))
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "100")], empresa="EMPRESA DOS",
                fecha=date(2026, 9, 20))

    assert empresa_sugerida(db, UNO) == "EMPRESA DOS"


def test_solo_historicos_sin_empresa_no_sugieren_empresa(db):
    comprobante(db, [(PODA, "horas_peon", SEPTIEMBRE_1, "100")], empresa=None,
                es_historico=True, fecha=date(2026, 9, 20))

    assert empresa_sugerida(db, UNO) is None
