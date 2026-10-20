"""La Precarga de una Factura nueva (spec de la E3b, Ticket 2, y el contrato
de la ruta 18 del plan de la E3), sobre SQLite en memoria y con la consulta
del campo falsa del Detalle.

Lo que se cuida acá:
- el período: falta, mal escrito, dado vuelta o cruzando de mes es un 422
  `periodo_invalido` con su campo, antes de leer el campo;
- lo trabajado: una entrada por tarea con partes del Cliente en el período
  (una quincena no trae la otra mitad), con todas las medidas por unidad;
- la unidad propuesta (decisión 8): la de la última Factura del Cliente por
  esa tarea, sin contar las Notas de crédito ni los pendientes de facturar;
  si no hay, la Unidad sugerida;
- los precios y la Empresa sugerida salen de `precios.py` (paso A7);
- el 404 de un Cliente que no existe, y quién entra: Editar en
  `comprobantes`.

Hoy es el 10 de noviembre de 2026. Datos inventados.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_usuario_actual
from app.core.database import Base, get_db_propia
from app.main import app
from app.modulos.facturacion import fechas
from app.modulos.facturacion.api import comprobantes as api_comprobantes
from app.modulos.facturacion.services import consulta_externa
from app.modulos.facturacion.services.precarga_service import (
    ClienteNoEncontrado, PeriodoInvalido, PrecargaService,
)
from app.modulos.facturacion.services.precios import empresa_sugerida, precios_sugeridos
from tests.facturacion import test_detalle as detalle_a8
from tests.facturacion import test_precios as precios_a7

D = Decimal
F = "/api/facturacion"

UNO, DOS, TRES = detalle_a8.UNO, detalle_a8.DOS, detalle_a8.TRES
SIN_NADA = detalle_a8.SIN_NADA
PODA = detalle_a8.PODA                # horas de peón
RALEO = detalle_a8.RALEO              # plantas
ATADO = detalle_a8.ATADO              # sin Unidad sugerida
INTERNA = detalle_a8.INTERNA          # No facturable
RASTREADO = detalle_a8.RASTREADO      # horas de tractor

OCTUBRE_1, OCTUBRE_15, OCTUBRE_16, OCTUBRE_31 = (
    "2026-10-01", "2026-10-15", "2026-10-16", "2026-10-31")


@pytest.fixture(autouse=True)
def hoy_10_de_noviembre(monkeypatch):
    monkeypatch.setattr(fechas, "_ahora",
                        lambda: datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc))


@pytest.fixture(autouse=True)
def cache_limpia():
    consulta_externa.invalidar_cache()
    yield
    consulta_externa.invalidar_cache()
    app.dependency_overrides.clear()


@pytest.fixture()
def db():
    # StaticPool y sin chequeo de hilo: TestClient corre el endpoint en otro
    # hilo y la base en memoria tiene que ser la misma conexión.
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)()
    yield sesion
    sesion.close()
    engine.dispose()


@pytest.fixture()
def consulta():
    return detalle_a8.ConsultaFalsa()


@pytest.fixture()
def servicio(db, consulta):
    return PrecargaService(db, consulta)


def _por_tarea(precarga):
    return {t["tarea_id"]: t for t in precarga["trabajado"]}


# ─── El período ─────────────────────────────────────────────────────────────

FALTA = "Falta el período facturado."
MAL_ESCRITA = "La fecha va como AAAA-MM-DD, por ejemplo 2026-10-15."
DADO_VUELTA = "La fecha final no puede ser anterior a la inicial."
CRUZA = "El período tiene que quedar dentro de un mismo mes."


@pytest.mark.parametrize("desde, hasta, campo, mensaje", [
    (None, OCTUBRE_15, "desde", FALTA),
    ("", OCTUBRE_15, "desde", FALTA),
    (OCTUBRE_1, None, "hasta", FALTA),
    ("2026-10-1x", OCTUBRE_15, "desde", MAL_ESCRITA),
    (OCTUBRE_1, "15/10/2026", "hasta", MAL_ESCRITA),
    (OCTUBRE_15, OCTUBRE_1, "hasta", DADO_VUELTA),
    ("2026-09-16", OCTUBRE_15, "hasta", CRUZA),
], ids=["sin_desde", "desde_vacio", "sin_hasta", "desde_mal", "hasta_mal",
        "dado_vuelta", "cruza_de_mes"])
def test_un_periodo_invalido_no_lee_el_campo(servicio, consulta, desde, hasta,
                                              campo, mensaje):
    with pytest.raises(PeriodoInvalido) as error:
        servicio.precarga(UNO, desde, hasta)
    assert (error.value.campo, error.value.mensaje) == (campo, mensaje)
    assert consulta.lecturas == []


# ─── Lo trabajado ───────────────────────────────────────────────────────────

def test_una_quincena_no_trae_la_otra_mitad(servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="10")
    consulta.parte(UNO, PODA, date(2026, 10, 15), jornal="2")
    consulta.parte(UNO, PODA, date(2026, 10, 16), jornal="5")
    consulta.parte(UNO, RALEO, date(2026, 10, 20), unidades="300")

    primera = _por_tarea(servicio.precarga(UNO, OCTUBRE_1, OCTUBRE_15))
    segunda = _por_tarea(servicio.precarga(UNO, OCTUBRE_16, OCTUBRE_31))

    assert set(primera) == {PODA}
    assert primera[PODA]["campo"]["horas_peon"] == D("12")
    assert set(segunda) == {PODA, RALEO}
    assert segunda[PODA]["campo"]["horas_peon"] == D("5")
    assert ("partes", UNO, date(2026, 10, 1), date(2026, 10, 15)) in consulta.lecturas


def test_campo_trae_una_medida_por_unidad(servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="8", maquina="3",
                   unidades="120", tancadas="2")
    consulta.parte(UNO, PODA, date(2026, 10, 4), jornal="1.5")

    tarea = _por_tarea(servicio.precarga(UNO, OCTUBRE_1, OCTUBRE_31))[PODA]

    assert tarea["campo"] == {
        "horas_peon": D("9.5"), "horas_tractor": D("3"), "plantas": D("120"),
        "hectareas": D("120"), "tancadas": D("2"),
    }


def test_una_entrada_por_tarea_trabajada_del_cliente(servicio, consulta):
    """Con lo del maestro de tareas. Las No facturable vienen marcadas: la
    pantalla decide qué hace con ellas. Lo de otro Cliente no entra."""
    consulta.parte(UNO, RASTREADO, date(2026, 10, 2), maquina="4")
    consulta.parte(UNO, INTERNA, date(2026, 10, 2), jornal="6")
    consulta.parte(UNO, ATADO, date(2026, 10, 2), jornal="1")
    consulta.parte(DOS, RALEO, date(2026, 10, 2), unidades="50")

    precarga = servicio.precarga(UNO, OCTUBRE_1, OCTUBRE_31)
    tareas = _por_tarea(precarga)

    assert set(tareas) == {RASTREADO, INTERNA, ATADO}
    assert {k: v for k, v in tareas[RASTREADO].items() if k != "campo"} == {
        "tarea_id": RASTREADO, "tarea_nombre": "RASTREADO",
        "grupo_tarea": "MAQUINARIA", "unidad_sugerida": "horas_tractor",
        "unidad_propuesta": "horas_tractor", "no_facturable": False,
    }
    assert tareas[INTERNA]["no_facturable"] is True
    assert tareas[ATADO]["unidad_propuesta"] is None
    assert precarga["cliente_id"] == UNO
    assert precarga["cliente_nombre"] == "CLIENTE UNO"
    assert precarga["leido_en"] == min(detalle_a8.LEIDO_PARTES, detalle_a8.LEIDO_TAREAS)


# ─── La unidad propuesta (decisión 8) ───────────────────────────────────────

def test_la_unidad_propuesta_es_la_de_la_ultima_factura_y_salta_las_notas(
        servicio, consulta, db):
    """PODA va en horas de peón, pero a este Cliente la última Factura se la
    cobró en horas de tractor; una Nota y un pendiente de facturar más nuevos
    no cuentan. Una Factura de otro Cliente tampoco. RALEO no tiene Facturas
    y queda con la Unidad sugerida."""
    precios_a7.comprobante(db, [(PODA, "plantas", date(2026, 8, 1), "5")],
                           fecha=date(2026, 8, 20))
    precios_a7.comprobante(db, [(PODA, "horas_tractor", date(2026, 9, 1), "90")],
                           fecha=date(2026, 9, 20))
    precios_a7.comprobante(db, [(PODA, "hectareas", date(2026, 10, 1), "70")],
                           tipo="nota_credito", fecha=date(2026, 10, 20))
    precios_a7.comprobante(db, [(PODA, "tancadas", date(2026, 10, 1), "70")],
                           es_historico=True, pendiente_de_facturar=True)
    precios_a7.comprobante(db, [(RALEO, "hectareas", date(2026, 10, 1), "70")],
                           cliente_id=DOS, fecha=date(2026, 10, 20))
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="10", maquina="4")
    consulta.parte(UNO, RALEO, date(2026, 10, 3), unidades="300")

    tareas = _por_tarea(servicio.precarga(UNO, OCTUBRE_1, OCTUBRE_31))

    assert tareas[PODA]["unidad_propuesta"] == "horas_tractor"
    assert tareas[PODA]["unidad_sugerida"] == "horas_peon"
    assert tareas[RALEO]["unidad_propuesta"] == "plantas"


def test_la_ultima_factura_sigue_el_orden_de_la_ruta_18(servicio, consulta, db):
    """El mes de la Línea manda sobre la fecha del Comprobante; en el mismo
    Comprobante, la última Línea por orden."""
    precios_a7.comprobante(db, [(PODA, "plantas", date(2026, 9, 1), "5")],
                           fecha=date(2026, 10, 30))
    precios_a7.comprobante(db, [(PODA, "horas_peon", date(2026, 10, 1), "90"),
                                (PODA, "hectareas", date(2026, 10, 1), "80")],
                           fecha=date(2026, 10, 2))
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="10")

    tareas = _por_tarea(servicio.precarga(UNO, OCTUBRE_1, OCTUBRE_31))

    assert tareas[PODA]["unidad_propuesta"] == "hectareas"


# ─── Precios y empresa (paso A7) ────────────────────────────────────────────

def test_los_precios_y_la_empresa_salen_de_las_facturas_del_cliente(
        servicio, consulta, db):
    precios_a7.comprobante(db, [(PODA, "horas_peon", date(2026, 9, 1), "100"),
                                (PODA, "horas_tractor", date(2026, 9, 1), "250")],
                           fecha=date(2026, 9, 20), empresa="EMPRESA DOS")
    precios_a7.comprobante(db, [(RALEO, "plantas", date(2026, 9, 1), "7")],
                           fecha=date(2026, 9, 25), empresa="EMPRESA TRES")
    precios_a7.comprobante(db, [(PODA, "horas_peon", date(2026, 10, 1), "999")],
                           tipo="nota_credito", fecha=date(2026, 10, 20),
                           empresa="EMPRESA NOTA")
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="10")

    precarga = servicio.precarga(UNO, OCTUBRE_1, OCTUBRE_31)

    esperados = sorted(precios_sugeridos(db, UNO).values(),
                       key=lambda p: (p["tarea_id"], p["unidad"]))
    assert sorted(precarga["precios"], key=lambda p: (p["tarea_id"], p["unidad"])) == esperados
    assert {(p["tarea_id"], p["unidad"], p["precio_unitario"]) for p in precarga["precios"]} == {
        (PODA, "horas_peon", D("100")), (PODA, "horas_tractor", D("250")),
        (RALEO, "plantas", D("7"))}
    assert precarga["empresa_sugerida"] == empresa_sugerida(db, UNO) == "EMPRESA TRES"


def test_sin_facturas_no_hay_precios_ni_empresa(servicio, consulta):
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="10")

    precarga = servicio.precarga(UNO, OCTUBRE_1, OCTUBRE_31)

    assert precarga["precios"] == []
    assert precarga["empresa_sugerida"] is None


# ─── El Cliente ─────────────────────────────────────────────────────────────

def test_un_cliente_que_no_existe_es_404_antes_de_leer_los_partes(servicio, consulta):
    with pytest.raises(ClienteNoEncontrado):
        servicio.precarga(SIN_NADA, OCTUBRE_1, OCTUBRE_31)
    assert not any(lectura[0] == "partes" for lectura in consulta.lecturas)


def test_un_cliente_de_baja_igual_se_precarga(servicio):
    """El Resumen muestra los de baja; su Precarga se abre (el alta es la que
    rechaza al Cliente de baja)."""
    assert servicio.precarga(TRES, OCTUBRE_1, OCTUBRE_31)["cliente_nombre"] == "CLIENTE TRES"


# ─── La ruta 18 ─────────────────────────────────────────────────────────────

def _persona(*permisos):
    return SimpleNamespace(
        id=42, nombre="Test", email="t@t.com", rol="usuario", activo=True,
        roles=[SimpleNamespace(nombre="Rol de prueba", permisos=[
            SimpleNamespace(modulo=m, pantalla=p, nivel=n) for m, p, n in permisos])])


EDITORA = _persona(("facturacion", "comprobantes", "editar"))
LECTORA = _persona(("facturacion", "comprobantes", "ver"))
# Edita el Resumen, pero no Comprobantes.
REVISORA = _persona(("facturacion", "resumen", "editar"))


def _cliente(persona, db, consulta):
    app.dependency_overrides[get_usuario_actual] = lambda: persona
    app.dependency_overrides[api_comprobantes.get_consulta_externa] = lambda: consulta
    app.dependency_overrides[get_db_propia] = lambda: db
    return TestClient(app)


def _precarga(c, cliente_id=UNO, desde=OCTUBRE_1, hasta=OCTUBRE_31):
    params = {"cliente_id": cliente_id}
    if desde is not None:
        params["desde"] = desde
    if hasta is not None:
        params["hasta"] = hasta
    return c.get(f"{F}/precarga", params=params)


def test_la_ruta_sale_con_la_forma_del_contrato(db, consulta):
    precios_a7.comprobante(db, [(PODA, "horas_peon", date(2026, 9, 1), "100.50")],
                           fecha=date(2026, 9, 20), empresa="EMPRESA DOS")
    consulta.parte(UNO, PODA, date(2026, 10, 3), jornal="10.25")

    r = _precarga(_cliente(EDITORA, db, consulta))

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"cliente_id", "cliente_nombre", "empresa_sugerida",
                           "leido_en", "trabajado", "precios"}
    assert cuerpo["empresa_sugerida"] == "EMPRESA DOS"
    (tarea,) = cuerpo["trabajado"]
    assert set(tarea) == {"tarea_id", "tarea_nombre", "grupo_tarea", "unidad_sugerida",
                          "unidad_propuesta", "no_facturable", "campo"}
    assert tarea["campo"] == {"horas_peon": "10.25", "horas_tractor": "0",
                              "plantas": "0", "hectareas": "0", "tancadas": "0"}
    (precio,) = cuerpo["precios"]
    # La columna guarda cuatro decimales.
    assert precio["precio_unitario"] == "100.5000"
    assert precio["fecha"] == "2026-09-20"
    assert set(precio) == {"tarea_id", "unidad", "precio_unitario", "comprobante_id",
                           "numero", "fecha"}


def test_un_periodo_invalido_es_422_con_su_campo(db, consulta):
    r = _precarga(_cliente(EDITORA, db, consulta), desde="2026-09-16", hasta=OCTUBRE_15)

    assert r.status_code == 422
    assert r.json()["detail"] == {"tipo": "periodo_invalido", "mensaje": CRUZA,
                                  "campo": "hasta"}


def test_sin_periodo_es_422_con_su_campo(db, consulta):
    r = _precarga(_cliente(EDITORA, db, consulta), desde=None)

    assert r.status_code == 422
    assert r.json()["detail"] == {"tipo": "periodo_invalido", "mensaje": FALTA,
                                  "campo": "desde"}


def test_un_cliente_que_no_existe_es_404(db, consulta):
    r = _precarga(_cliente(EDITORA, db, consulta), cliente_id=SIN_NADA)

    assert r.status_code == 404
    assert r.json()["detail"] == "No existe ese Cliente."


@pytest.mark.parametrize("persona", [LECTORA, REVISORA], ids=["solo_ver", "solo_resumen"])
def test_sin_editar_comprobantes_es_403_sin_leer_el_campo(db, consulta, persona):
    r = _precarga(_cliente(persona, db, consulta))

    assert r.status_code == 403
    assert consulta.lecturas == []
