"""Los endpoints del Resumen, el Detalle, la Revisión de diferencia y la
configuración (plan de la E3, sección 3.2, rutas 13 a 17; paso A10).

Las reglas ya están probadas en test_resumen_service, test_detalle y
test_revision. Acá se prueba lo que agrega la capa HTTP: quién entra a qué,
los códigos y el `detail` de cada error del contrato, y cómo sale el cuerpo
(los decimales como texto, los meses como "AAAA-MM", los días del filtro como
"AAAA-MM-DD" y sólo las claves del contrato). Primero con un servicio doble, sin base ni red; al final, con el
servicio de verdad sobre SQLite y la consulta del campo falsa del Detalle.

Hoy es el 10 de noviembre de 2026: noviembre es el mes en curso y, con el
corte inicial en octubre, octubre se controla. Datos inventados.
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
from app.core.database import Base, ExternaNoDisponible, get_db_propia
from app.core.models import Usuario
from app.main import app
from app.modulos.facturacion import fechas
from app.modulos.facturacion.api import comprobantes as api_comprobantes
from app.modulos.facturacion.api import resumen as api
from app.modulos.facturacion.services import consulta_externa
from app.modulos.facturacion.services.resumen_service import (
    ClienteNoEncontrado, ConfiguracionInvalida, FechaInvalida, MesInvalido, NoRevisable,
    RangoInvalido, ResumenService, RevisionInvalida, SinRevision,
)
from tests.facturacion import test_detalle as detalle_a8

F = "/api/facturacion"
D = Decimal

# ─── Lo que devuelve el servicio doble ──────────────────────────────────────
# Con los tipos del servicio de verdad: Decimal, date y datetime. Cada dict
# trae una clave de más ("sobra"), que el schema tiene que dejar afuera.

LINEA = {
    "grupo": "MANUALES", "unidad": "horas_peon", "campo": D("120.50"),
    "facturado": D("130"), "diferencia": D("9.50"), "diferencia_pct": D("7.88"),
    "supera": True, "fuera_del_filtro": False, "sobra": "no va",
}
# Facturado sin campo: sin unidad de medida del campo, sin diferencia ni %.
LINEA_SIN_CAMPO = {
    "grupo": "Sin grupo", "unidad": "hectareas", "campo": D("0"),
    "facturado": D("4.25"), "diferencia": D("4.25"), "diferencia_pct": None,
    "supera": True,
}
# Una Línea cae en parte afuera del filtro: sin diferencia, ni %, ni supera.
LINEA_FUERA = {
    "grupo": "MAQUINARIA", "unidad": "horas_tractor", "campo": D("8"),
    "facturado": D("0"), "diferencia": None, "diferencia_pct": None,
    "supera": False, "fuera_del_filtro": True,
}
FILA = {
    "cliente_id": 12, "cliente_nombre": "CLIENTE UNO", "mes": date(2026, 10, 1),
    "desde": date(2026, 10, 1), "hasta": date(2026, 10, 10), "en_curso": False,
    "grupos": [LINEA, LINEA_SIN_CAMPO, LINEA_FUERA], "lineas_superan": 2,
    "estados": ["con_diferencia", "falta_comprobante"],
    "diferencia_revisada": False,
    "comprobantes_sin_adjunto": [{"id": 5, "tipo": "factura", "numero": "A 0001"}],
    "comprobantes_fuera": [{"id": 6, "tipo": "factura", "numero": "A 0002",
                            "desde": date(2026, 10, 1), "hasta": date(2026, 10, 15),
                            "sobra": "no va"}],
    "sobra": "no va",
}
RESUMEN = {
    "umbral_pct": D("5.00"), "mes_corte": date(2026, 10, 1),
    "mes_en_curso": date(2026, 11, 1), "leido_en": datetime(2026, 11, 10, 13, 30),
    "actualizado_en": datetime(2026, 11, 10, 16, 0),
    "actualizado_por_nombre": "PERSONA DE PRUEBA",
    "filas": [FILA],
    "tareas_sin_unidad": [{"tarea_id": 106, "nombre": "ATADO", "clientes": 2}],
    "sobra": "no va",
}
TAREA = {
    "tarea_id": 101, "tarea_nombre": "PODA",
    "sin_unidad_sugerida": False, "en_varias_unidades": False,
    "campo": D("100"), "precio": D("50.0000"),
    "partes": [{"fecha": date(2026, 10, 3), "donde": "FINCA A",
                "supervisor": "SUPERVISOR A", "cantidad": D("100")}],
    "sobra": "no va",
}
SIN_UNIDAD = {
    **TAREA, "tarea_id": 106, "tarea_nombre": "ATADO",
    "sin_unidad_sugerida": True, "campo": None, "precio": None,
    "partes": [{"fecha": date(2026, 10, 4), "donde": None, "supervisor": None,
                "cantidad": None}],
}
GRUPO_DETALLE = {
    "grupo": "MANUALES", "unidad": "horas_peon", "campo": D("100"),
    "facturado": D("150"), "diferencia": D("50"), "diferencia_pct": D("50.00"),
    "supera": True, "tareas": [TAREA], "sobra": "no va",
}
SIN_UNIDAD_DETALLE = {
    **GRUPO_DETALLE, "grupo": "Sin grupo", "unidad": None, "campo": None,
    "facturado": D("0"), "diferencia": None, "diferencia_pct": None,
    "tareas": [SIN_UNIDAD],
}
DETALLE = {
    "cliente_id": 12, "cliente_nombre": "CLIENTE UNO", "mes": date(2026, 10, 1),
    "desde": date(2026, 10, 1), "hasta": date(2026, 10, 15), "en_curso": False,
    "umbral_pct": D("5.00"), "mes_corte": date(2026, 10, 1),
    "leido_en": datetime(2026, 11, 10, 13, 30),
    "estados": ["facturada"], "diferencia_revisada": True, "se_puede_revisar": False,
    "comprobantes": [{"id": 5, "tipo": "factura", "numero": "A 0001",
                      "cantidad_adjuntos": 1, "es_historico": False}],
    "grupos": [GRUPO_DETALLE, SIN_UNIDAD_DETALLE],
    "total": {"campo_pesos": D("5000.00"), "facturado_pesos": D("7500.00"),
              "diferencia_pesos": D("2500.00"), "diferencia_pct": D("50.00"),
              "tareas_sin_precio": 1},
    "revision": {"id": 7, "comentario": "Explicada.",
                 "desde": date(2026, 10, 1), "hasta": date(2026, 10, 31),
                 "creada_en": datetime(2026, 11, 10, 15, 0),
                 "creada_por_nombre": "PERSONA DE PRUEBA",
                 "grupos": [{"grupo": "MANUALES", "unidad": "horas_peon"}]},
    "sobra": "no va",
}
CONFIGURACION = {
    "umbral_pct": D("7.50"), "mes_corte": date(2026, 9, 1),
    "actualizado_en": datetime(2026, 11, 10, 16, 0),
    "actualizado_por_nombre": "PERSONA DE PRUEBA", "sobra": "no va",
}

# Las claves de cada respuesta, copiadas de la sección 3.2 del plan.
CLAVES_RESUMEN = {"umbral_pct", "mes_corte", "mes_en_curso", "leido_en", "filas",
                  "tareas_sin_unidad", "actualizado_en", "actualizado_por_nombre"}
CLAVES_FILA = {"cliente_id", "cliente_nombre", "mes", "desde", "hasta", "en_curso", "grupos",
               "lineas_superan", "estados", "diferencia_revisada",
               "comprobantes_sin_adjunto", "comprobantes_fuera"}
CLAVES_LINEA = {"grupo", "unidad", "campo", "facturado", "diferencia", "diferencia_pct",
                "supera", "fuera_del_filtro"}
CLAVES_COMPROBANTE_FUERA = {"id", "tipo", "numero", "desde", "hasta"}
CLAVES_DETALLE = {"cliente_id", "cliente_nombre", "mes", "desde", "hasta", "en_curso",
                  "umbral_pct", "mes_corte",
                  "leido_en", "estados", "diferencia_revisada", "se_puede_revisar",
                  "comprobantes", "grupos", "total", "revision"}
CLAVES_GRUPO_DETALLE = CLAVES_LINEA | {"tareas"}
CLAVES_TAREA = {"tarea_id", "tarea_nombre", "sin_unidad_sugerida",
                "en_varias_unidades", "campo", "precio", "partes"}
CLAVES_TOTAL = {"campo_pesos", "facturado_pesos", "diferencia_pesos",
                "diferencia_pct", "tareas_sin_precio"}
CLAVES_REVISION = {"id", "comentario", "desde", "hasta", "creada_en", "creada_por_nombre",
                   "grupos"}
CLAVES_CONFIGURACION = {"umbral_pct", "mes_corte", "actualizado_en",
                        "actualizado_por_nombre"}


class ServicioFalso:
    """El ResumenService con lo justo: anota lo que recibe y, si se le da un
    error, lo levanta en cualquier operación."""

    def __init__(self, error=None):
        self.error = error
        self.llamadas = []

    def _anotar(self, *llamada):
        self.llamadas.append(llamada)
        if self.error is not None:
            raise self.error

    def resumen(self, desde, hasta, refrescar=False):
        self._anotar("resumen", desde, hasta, refrescar)
        return RESUMEN

    def detalle(self, cliente_id, mes, refrescar=False, desde=None, hasta=None):
        self._anotar("detalle", cliente_id, mes, refrescar, desde, hasta)
        return DETALLE

    def revisar(self, cliente_id, mes, comentario, usuario_id, desde=None, hasta=None):
        self._anotar("revisar", cliente_id, mes, comentario, usuario_id, desde, hasta)
        return DETALLE

    def deshacer_revision(self, cliente_id, mes, usuario_id, desde=None, hasta=None):
        self._anotar("deshacer", cliente_id, mes, usuario_id, desde, hasta)
        return DETALLE

    def cambiar_configuracion(self, umbral_pct, mes_corte, usuario_id):
        self._anotar("configuracion", umbral_pct, mes_corte, usuario_id)
        return CONFIGURACION


def _persona(*permisos, rol="usuario", id_=42):
    """Una persona con un rol armado a mano, como en test_api_comprobantes."""
    return SimpleNamespace(
        id=id_, nombre="Test", email="t@t.com", rol=rol, activo=True,
        roles=[SimpleNamespace(nombre="Rol de prueba", permisos=[
            SimpleNamespace(modulo=m, pantalla=p, nivel=n) for m, p, n in permisos
        ])],
    )


REVISORA = _persona(("facturacion", "resumen", "editar"))
LECTORA = _persona(("facturacion", "resumen", "ver"))
# Edita Comprobantes, pero no tiene el Resumen.
SOLO_COMPROBANTES = _persona(("facturacion", "comprobantes", "editar"))
ADMIN = SimpleNamespace(id=1, nombre="A", email="a@t.com", rol="admin",
                        activo=True, roles=[])

CONFIG_ENTRADA = {"umbral_pct": "7.5", "mes_corte": "2026-09"}

# Las cinco rutas: (método, ruta, cuerpo).
RESUMEN_GET = ("GET", "/resumen?desde=2026-09-01&hasta=2026-10-31", None)
DETALLE_GET = ("GET", "/resumen/12/2026-10", None)
REVISAR = ("POST", "/resumen/12/2026-10/revision", {"comentario": "Explicada."})
DESHACER = ("DELETE", "/resumen/12/2026-10/revision", None)
CONFIGURAR = ("PUT", "/configuracion", CONFIG_ENTRADA)
RUTAS = [RESUMEN_GET, DETALLE_GET, REVISAR, DESHACER, CONFIGURAR]
IDS = ["13_resumen", "14_detalle", "15_revisar", "16_deshacer", "17_configuracion"]


@pytest.fixture(autouse=True)
def _limpiar():
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def hoy_10_de_noviembre(monkeypatch):
    monkeypatch.setattr(fechas, "_ahora",
                        lambda: datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc))


@pytest.fixture(autouse=True)
def cache_limpia():
    consulta_externa.invalidar_cache()
    yield
    consulta_externa.invalidar_cache()


def _cliente(persona=REVISORA, servicio=None):
    if persona is not None:
        app.dependency_overrides[get_usuario_actual] = lambda: persona
    app.dependency_overrides[api.get_resumen] = lambda: servicio or ServicioFalso()
    return TestClient(app)


def _pedir(c, metodo, ruta, cuerpo):
    kwargs = {"json": cuerpo} if cuerpo is not None else {}
    return c.request(metodo, f"{F}{ruta}", **kwargs)


# ─── Lo que devuelve ────────────────────────────────────────────────────────

def test_el_resumen_sale_con_la_forma_del_contrato():
    servicio = ServicioFalso()
    r = _cliente(servicio=servicio).get(
        f"{F}/resumen",
        params={"desde": "2026-09-16", "hasta": "2026-10-10", "refrescar": "true"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == CLAVES_RESUMEN
    assert cuerpo["umbral_pct"] == "5.00"
    # Los meses van como "AAAA-MM", como en la ruta y en el listado de la E2.
    assert cuerpo["mes_corte"] == "2026-10"
    assert cuerpo["mes_en_curso"] == "2026-11"
    assert cuerpo["leido_en"] == "2026-11-10T13:30:00"
    assert cuerpo["actualizado_en"] == "2026-11-10T16:00:00"
    assert cuerpo["actualizado_por_nombre"] == "PERSONA DE PRUEBA"
    assert cuerpo["tareas_sin_unidad"] == [{"tarea_id": 106, "nombre": "ATADO", "clientes": 2}]
    fila = cuerpo["filas"][0]
    assert set(fila) == CLAVES_FILA
    assert fila["mes"] == "2026-10"
    # El período de la fila, en días: el filtro recortado al mes.
    assert (fila["desde"], fila["hasta"]) == ("2026-10-01", "2026-10-10")
    assert fila["en_curso"] is False
    # Las líneas (grupo, unidad), con los decimales como texto y sin pesos.
    assert fila["lineas_superan"] == 2
    assert [set(l) for l in fila["grupos"]] == [CLAVES_LINEA] * 3
    assert fila["grupos"][0] == {
        "grupo": "MANUALES", "unidad": "horas_peon", "campo": "120.50",
        "facturado": "130", "diferencia": "9.50", "diferencia_pct": "7.88",
        "supera": True, "fuera_del_filtro": False}
    # Facturado sin campo: el % en raya (null); sin la clave, no está fuera.
    assert fila["grupos"][1]["diferencia_pct"] is None
    assert fila["grupos"][1]["fuera_del_filtro"] is False
    assert fila["grupos"][2] == {
        "grupo": "MAQUINARIA", "unidad": "horas_tractor", "campo": "8",
        "facturado": "0", "diferencia": None, "diferencia_pct": None,
        "supera": False, "fuera_del_filtro": True}
    assert fila["estados"] == ["con_diferencia", "falta_comprobante"]
    assert fila["comprobantes_sin_adjunto"] == [{"id": 5, "tipo": "factura", "numero": "A 0001"}]
    assert fila["comprobantes_fuera"] == [
        {"id": 6, "tipo": "factura", "numero": "A 0002",
         "desde": "2026-10-01", "hasta": "2026-10-15"}]
    assert servicio.llamadas == [("resumen", "2026-09-16", "2026-10-10", True)]


def test_sin_refrescar_el_resumen_usa_la_cache():
    servicio = ServicioFalso()
    r = _cliente(servicio=servicio).get(f"{F}/resumen?desde=2026-09-01&hasta=2026-10-31")
    assert r.status_code == 200
    assert servicio.llamadas == [("resumen", "2026-09-01", "2026-10-31", False)]


def test_el_detalle_sale_con_la_forma_del_contrato():
    servicio = ServicioFalso()
    r = _cliente(servicio=servicio).get(f"{F}/resumen/12/2026-10?refrescar=true")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == CLAVES_DETALLE
    assert cuerpo["mes"] == "2026-10"
    assert (cuerpo["desde"], cuerpo["hasta"]) == ("2026-10-01", "2026-10-15")
    assert cuerpo["en_curso"] is False
    assert cuerpo["mes_corte"] == "2026-10"
    assert cuerpo["umbral_pct"] == "5.00"
    assert cuerpo["comprobantes"] == [{"id": 5, "tipo": "factura", "numero": "A 0001",
                                       "cantidad_adjuntos": 1, "es_historico": False}]
    # Una fila por (grupo, unidad), con la diferencia y "supera"; sus tareas,
    # con la Cantidad del campo, el precio y los partes.
    assert [set(g) for g in cuerpo["grupos"]] == [CLAVES_GRUPO_DETALLE] * 2
    manuales = cuerpo["grupos"][0]
    assert (manuales["grupo"], manuales["unidad"], manuales["campo"], manuales["facturado"],
            manuales["diferencia"], manuales["diferencia_pct"], manuales["supera"]) == (
        "MANUALES", "horas_peon", "100", "150", "50", "50.00", True)
    poda = manuales["tareas"][0]
    assert set(poda) == CLAVES_TAREA
    assert (poda["campo"], poda["precio"]) == ("100", "50.0000")
    assert poda["partes"] == [{"fecha": "2026-10-03", "donde": "FINCA A",
                               "supervisor": "SUPERVISOR A", "cantidad": "100"}]
    # Una fila sin unidad: sin campo, sin diferencia y sin %; su tarea, sin
    # campo y sin precio.
    sin_unidad = cuerpo["grupos"][1]
    assert (sin_unidad["grupo"], sin_unidad["unidad"], sin_unidad["campo"],
            sin_unidad["diferencia"], sin_unidad["diferencia_pct"]) == (
        "Sin grupo", None, None, None, None)
    atado = sin_unidad["tareas"][0]
    assert (atado["sin_unidad_sugerida"], atado["campo"], atado["precio"]) == (
        True, None, None)
    assert atado["partes"][0]["cantidad"] is None
    assert set(cuerpo["total"]) == CLAVES_TOTAL
    assert cuerpo["total"]["campo_pesos"] == "5000.00"
    assert cuerpo["total"]["tareas_sin_precio"] == 1
    assert set(cuerpo["revision"]) == CLAVES_REVISION
    assert cuerpo["revision"]["creada_en"] == "2026-11-10T15:00:00"
    # El período, en días (AAAA-MM-DD), para el aviso del Detalle.
    assert (cuerpo["revision"]["desde"], cuerpo["revision"]["hasta"]) == (
        "2026-10-01", "2026-10-31")
    assert cuerpo["revision"]["grupos"] == [{"grupo": "MANUALES", "unidad": "horas_peon"}]
    assert servicio.llamadas == [("detalle", 12, "2026-10", True, None, None)]


def test_dejar_una_revision_responde_201_con_el_detalle_y_sella_quien():
    servicio = ServicioFalso()
    r = _cliente(servicio=servicio).post(f"{F}/resumen/12/2026-10/revision",
                                         json={"comentario": "Explicada."})
    assert r.status_code == 201, r.text
    assert set(r.json()) == CLAVES_DETALLE
    assert servicio.llamadas == [("revisar", 12, "2026-10", "Explicada.", 42, None, None)]


def test_una_revision_sin_comentario_llega_al_servicio_que_decide():
    """Sin `comentario` no es la lista de FastAPI: el servicio lo rechaza con el
    422 del contrato, con su campo."""
    servicio = ServicioFalso()
    r = _cliente(servicio=servicio).post(f"{F}/resumen/12/2026-10/revision", json={})
    assert r.status_code == 201
    assert servicio.llamadas == [("revisar", 12, "2026-10", None, 42, None, None)]


def test_deshacer_responde_200_con_el_detalle_y_sella_quien():
    servicio = ServicioFalso()
    r = _cliente(servicio=servicio).delete(f"{F}/resumen/12/2026-10/revision")
    assert r.status_code == 200, r.text
    assert set(r.json()) == CLAVES_DETALLE
    assert servicio.llamadas == [("deshacer", 12, "2026-10", 42, None, None)]


def test_el_detalle_y_la_revision_pasan_desde_y_hasta_al_servicio():
    servicio = ServicioFalso()
    c = _cliente(servicio=servicio)
    periodo = "desde=2026-10-01&hasta=2026-10-15"
    assert c.get(f"{F}/resumen/12/2026-10?{periodo}").status_code == 200
    assert c.post(f"{F}/resumen/12/2026-10/revision?{periodo}",
                  json={"comentario": "Explicada."}).status_code == 201
    assert c.delete(f"{F}/resumen/12/2026-10/revision?{periodo}").status_code == 200
    assert servicio.llamadas == [
        ("detalle", 12, "2026-10", False, "2026-10-01", "2026-10-15"),
        ("revisar", 12, "2026-10", "Explicada.", 42, "2026-10-01", "2026-10-15"),
        ("deshacer", 12, "2026-10", 42, "2026-10-01", "2026-10-15"),
    ]


def test_la_configuracion_responde_200_con_quien_y_cuando():
    servicio = ServicioFalso()
    r = _cliente(ADMIN, servicio=servicio).put(f"{F}/configuracion", json=CONFIG_ENTRADA)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == CLAVES_CONFIGURACION
    assert cuerpo == {"umbral_pct": "7.50", "mes_corte": "2026-09",
                      "actualizado_en": "2026-11-10T16:00:00",
                      "actualizado_por_nombre": "PERSONA DE PRUEBA"}
    # El Umbral llega como Decimal exacto y el mes como texto: lo lee el servicio.
    assert servicio.llamadas == [("configuracion", D("7.5"), "2026-09", 1)]


def test_si_el_campo_no_responde_es_503():
    """Lo traduce app/main.py; acá sólo se mira que la excepción llegue."""
    servicio = ServicioFalso(error=ExternaNoDisponible("El sistema de campo no respondió."))
    r = _cliente(servicio=servicio).get(f"{F}/resumen?desde=2026-09-01&hasta=2026-10-31")
    assert r.status_code == 503
    assert r.json()["detail"] == "El sistema de campo no respondió."


# ─── Los errores del contrato ───────────────────────────────────────────────

ERRORES = [
    (RESUMEN_GET, FechaInvalida("desde"), 422,
     {"tipo": "fecha_invalida", "campo": "desde"}),
    (RESUMEN_GET, RangoInvalido("hasta", "La fecha final no puede pasar del mes en curso."),
     422, {"tipo": "rango_invalido", "campo": "hasta"}),
    (DETALLE_GET, MesInvalido("mes"), 422, {"tipo": "mes_invalido", "campo": "mes"}),
    (DETALLE_GET, FechaInvalida("hasta"), 422, {"tipo": "fecha_invalida", "campo": "hasta"}),
    (REVISAR, RangoInvalido("desde", "El período elegido no toca este mes."), 422,
     {"tipo": "rango_invalido", "campo": "desde"}),
    (REVISAR, RevisionInvalida("Falta el comentario."), 422,
     {"tipo": "revision_invalida", "campo": "comentario"}),
    (REVISAR, NoRevisable("Ningún grupo supera el Umbral."), 409,
     {"tipo": "no_revisable"}),
    (DESHACER, SinRevision(), 409, {"tipo": "sin_revision"}),
    (CONFIGURAR, ConfiguracionInvalida("umbral_pct", "El Umbral tiene que ser mayor que 0."),
     422, {"tipo": "configuracion_invalida", "campo": "umbral_pct"}),
]


@pytest.mark.parametrize("ruta, error, codigo, esperado", ERRORES,
                         ids=[f"{e['tipo']}_{r[0]}" for r, _, _, e in ERRORES])
def test_cada_error_sale_con_su_codigo_y_su_detail(ruta, error, codigo, esperado):
    r = _pedir(_cliente(ADMIN, servicio=ServicioFalso(error=error)), *ruta)
    assert r.status_code == codigo, r.text
    detail = r.json()["detail"]
    assert {k: detail[k] for k in esperado} == esperado
    assert detail["mensaje"] == error.mensaje
    assert set(detail) == {"tipo", "mensaje"} | ({"campo"} if "campo" in esperado else set())


@pytest.mark.parametrize("ruta", [DETALLE_GET, REVISAR, DESHACER],
                         ids=["14_detalle", "15_revisar", "16_deshacer"])
def test_un_cliente_que_no_existe_es_404_con_texto(ruta):
    r = _pedir(_cliente(servicio=ServicioFalso(error=ClienteNoEncontrado())), *ruta)
    assert r.status_code == 404
    assert r.json()["detail"] == "No existe ese Cliente."


# ─── Permisos ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("metodo, ruta, cuerpo", RUTAS, ids=IDS)
def test_sin_sesion_es_401(metodo, ruta, cuerpo):
    servicio = ServicioFalso()
    r = _pedir(_cliente(persona=None, servicio=servicio), metodo, ruta, cuerpo)
    assert r.status_code == 401
    assert servicio.llamadas == []


@pytest.mark.parametrize("metodo, ruta, cuerpo", RUTAS, ids=IDS)
def test_quien_solo_tiene_comprobantes_no_entra(metodo, ruta, cuerpo):
    servicio = ServicioFalso()
    r = _pedir(_cliente(SOLO_COMPROBANTES, servicio=servicio), metodo, ruta, cuerpo)
    assert r.status_code == 403
    assert servicio.llamadas == []


@pytest.mark.parametrize("metodo, ruta, cuerpo", [RESUMEN_GET, DETALLE_GET],
                         ids=IDS[:2])
def test_quien_ve_el_resumen_lo_lee(metodo, ruta, cuerpo):
    assert _pedir(_cliente(LECTORA), metodo, ruta, cuerpo).status_code == 200


@pytest.mark.parametrize("metodo, ruta, cuerpo", [REVISAR, DESHACER], ids=IDS[2:4])
def test_quien_solo_ve_el_resumen_no_revisa(metodo, ruta, cuerpo):
    servicio = ServicioFalso()
    r = _pedir(_cliente(LECTORA, servicio=servicio), metodo, ruta, cuerpo)
    assert r.status_code == 403
    assert servicio.llamadas == []


def test_editar_el_resumen_no_alcanza_para_la_configuracion():
    """El Umbral y el Mes de corte los cambia sólo el Admin (decisión 4)."""
    servicio = ServicioFalso()
    r = _pedir(_cliente(REVISORA, servicio=servicio), *CONFIGURAR)
    assert r.status_code == 403
    assert servicio.llamadas == []


def test_el_admin_entra_a_todo_sin_roles():
    for metodo, ruta, cuerpo in RUTAS:
        r = _pedir(_cliente(ADMIN), metodo, ruta, cuerpo)
        assert r.status_code in (200, 201), (metodo, ruta, r.text)


# ─── Con el servicio de verdad ──────────────────────────────────────────────

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
def real(db):
    """Un cliente HTTP con el ResumenService de verdad y una persona admin
    guardada en la base, para que la Revisión y la configuración tengan
    quién. La consulta del campo va por get_consulta_externa, la misma de
    Comprobantes: un solo override sirve para los dos routers."""
    usuario = Usuario(nombre="PERSONA DE PRUEBA", email="persona@prueba.test",
                      password="x", rol="admin")
    db.add(usuario)
    db.commit()
    consulta = detalle_a8.ConsultaFalsa()
    app.dependency_overrides[get_usuario_actual] = lambda: SimpleNamespace(
        id=usuario.id, nombre=usuario.nombre, email=usuario.email, rol="admin",
        activo=True, roles=[])
    app.dependency_overrides[api_comprobantes.get_consulta_externa] = lambda: consulta
    app.dependency_overrides[get_db_propia] = lambda: db
    return SimpleNamespace(c=TestClient(app), db=db, consulta=consulta)


def _con_diferencia(real, cliente_id=detalle_a8.UNO):
    """Octubre Con diferencia: PODA trabajó 100 horas y se facturaron 150
    (supera); RALEO, 300 plantas facturadas justas. Con PDF."""
    real.consulta.parte(cliente_id, detalle_a8.PODA, date(2026, 10, 3), jornal="100")
    real.consulta.parte(cliente_id, detalle_a8.RALEO, date(2026, 10, 5), unidades="300")
    detalle_a8.comprobante(
        real.db, cliente_id,
        [(detalle_a8.PODA, "horas_peon", date(2026, 10, 1), "150", "7500"),
         (detalle_a8.RALEO, "plantas", date(2026, 10, 1), "300", "900")],
        adjuntos=1)


def test_de_punta_a_punta_los_schemas_aceptan_lo_que_devuelve_el_servicio(real):
    """Los dobles de arriba copian el contrato; acá se mira que lo que arma el
    servicio real pase por los schemas de salida en las cinco rutas, y que la
    Revisión y su deshacer se encadenen como en la pantalla."""
    _con_diferencia(real)
    c = real.c

    r = c.get(f"{F}/resumen?desde=2026-10-01&hasta=2026-10-31")
    assert r.status_code == 200, r.text
    resumen = r.json()
    assert set(resumen) == CLAVES_RESUMEN
    assert (resumen["umbral_pct"], resumen["mes_corte"], resumen["mes_en_curso"]) == (
        "5.00", "2026-10", "2026-11")
    fila = resumen["filas"][0]
    assert set(fila) == CLAVES_FILA
    assert (fila["cliente_id"], fila["mes"], fila["estados"]) == (
        detalle_a8.UNO, "2026-10", ["con_diferencia"])
    assert [(l["grupo"], l["unidad"], l["campo"], l["facturado"], l["supera"])
            for l in fila["grupos"]] == [
        ("MANUALES", "horas_peon", "100", "150.00", True),
        ("MANUALES", "plantas", "300", "300.00", False)]
    assert fila["lineas_superan"] == 1

    ruta = f"{F}/resumen/{detalle_a8.UNO}/2026-10"
    r = c.get(ruta)
    assert r.status_code == 200, r.text
    detalle = r.json()
    assert set(detalle) == CLAVES_DETALLE
    assert detalle["se_puede_revisar"] is True
    assert detalle["revision"] is None
    assert all(set(g) == CLAVES_GRUPO_DETALLE for g in detalle["grupos"])
    assert [(g["grupo"], g["unidad"], g["supera"]) for g in detalle["grupos"]] == [
        ("MANUALES", "horas_peon", True), ("MANUALES", "plantas", False)]
    tareas = [t for g in detalle["grupos"] for t in g["tareas"]]
    assert all(set(t) == CLAVES_TAREA for t in tareas)
    assert set(detalle["total"]) == CLAVES_TOTAL

    # La Revisión: el 422 del contrato, después el 201 y, otra vez, el 409.
    r = c.post(f"{ruta}/revision", json={"comentario": "   "})
    assert r.status_code == 422
    assert r.json()["detail"]["tipo"] == "revision_invalida"
    assert r.json()["detail"]["campo"] == "comentario"

    r = c.post(f"{ruta}/revision", json={"comentario": "  El campo cargó de menos.  "})
    assert r.status_code == 201, r.text
    revisado = r.json()
    assert revisado["diferencia_revisada"] is True
    assert revisado["estados"] == ["facturada"]
    assert set(revisado["revision"]) == CLAVES_REVISION
    assert revisado["revision"]["comentario"] == "El campo cargó de menos."
    assert revisado["revision"]["creada_por_nombre"] == "PERSONA DE PRUEBA"
    assert revisado["revision"]["grupos"] == [{"grupo": "MANUALES", "unidad": "horas_peon"}]
    assert (revisado["revision"]["desde"], revisado["revision"]["hasta"]) == (
        "2026-10-01", "2026-10-31")
    # La Revisión guardada por la API cubre el mes entero: el Resumen del mes
    # la toma.
    fila = c.get(f"{F}/resumen?desde=2026-10-01&hasta=2026-10-31").json()["filas"][0]
    assert (fila["estados"], fila["diferencia_revisada"]) == (["facturada"], True)

    r = c.post(f"{ruta}/revision", json={"comentario": "Otra vez."})
    assert r.status_code == 409
    assert r.json()["detail"]["tipo"] == "no_revisable"

    # Deshacer: 200 con el Detalle y, otra vez, el 409.
    r = c.delete(f"{ruta}/revision")
    assert r.status_code == 200, r.text
    assert r.json()["revision"] is None
    assert r.json()["estados"] == ["con_diferencia"]
    r = c.delete(f"{ruta}/revision")
    assert r.status_code == 409
    assert r.json()["detail"]["tipo"] == "sin_revision"

    # La configuración: 200 con quién y cuándo, y el Resumen la usa.
    r = c.put(f"{F}/configuracion", json={"umbral_pct": "60", "mes_corte": "2026-09"})
    assert r.status_code == 200, r.text
    configuracion = r.json()
    assert set(configuracion) == CLAVES_CONFIGURACION
    assert (configuracion["umbral_pct"], configuracion["mes_corte"],
            configuracion["actualizado_por_nombre"]) == ("60.00", "2026-09", "PERSONA DE PRUEBA")
    resumen = c.get(f"{F}/resumen?desde=2026-10-01&hasta=2026-10-31").json()
    assert resumen["umbral_pct"] == "60.00"
    assert resumen["filas"][0]["estados"] == ["facturada"]


def test_el_resumen_trae_el_ultimo_cambio_de_la_configuracion(real):
    """El pie del Resumen muestra quién y cuándo cambió la configuración
    (A10b). Sin cambios, los dos llegan null; después de un PUT, la fecha y
    el nombre de quien la cambió."""
    _con_diferencia(real)
    c = real.c

    r = c.get(f"{F}/resumen?desde=2026-10-01&hasta=2026-10-31")
    assert r.status_code == 200, r.text
    resumen = r.json()
    assert resumen["actualizado_en"] is None
    assert resumen["actualizado_por_nombre"] is None

    r = c.put(f"{F}/configuracion", json={"umbral_pct": "60", "mes_corte": "2026-09"})
    assert r.status_code == 200, r.text
    cambio = r.json()

    r = c.get(f"{F}/resumen?desde=2026-10-01&hasta=2026-10-31")
    assert r.status_code == 200, r.text
    resumen = r.json()
    assert resumen["actualizado_en"] is not None
    assert resumen["actualizado_en"] == cambio["actualizado_en"]
    assert resumen["actualizado_por_nombre"] == "PERSONA DE PRUEBA"


@pytest.mark.parametrize("ruta, tipo, campo", [
    ("/resumen/1/2026-13", "mes_invalido", "mes"),
    ("/resumen?desde=2026-10&hasta=2026-10-31", "fecha_invalida", "desde"),
    ("/resumen?desde=2026-13-01&hasta=2026-10-31", "fecha_invalida", "desde"),
    ("/resumen?desde=2026-10-01", "fecha_invalida", "hasta"),
    ("/resumen/1/2026-10?desde=2026-10-1", "fecha_invalida", "desde"),
], ids=["detalle_mes", "resumen_mes_solo", "resumen_desde", "resumen_sin_hasta",
        "detalle_desde"])
def test_una_fecha_mal_escrita_es_422_con_su_tipo(real, ruta, tipo, campo):
    r = real.c.get(f"{F}{ruta}")
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["tipo"] == tipo
    assert detail["campo"] == campo
    assert detail["mensaje"]


def test_un_rango_que_toca_13_meses_es_422_rango_invalido(real):
    r = real.c.get(f"{F}/resumen?desde=2025-10-31&hasta=2026-10-01")
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["tipo"] == "rango_invalido"
    assert detail["campo"] == "desde"
    assert detail["mensaje"]
    # 12 meses sí.
    assert real.c.get(f"{F}/resumen?desde=2025-11-01&hasta=2026-10-31").status_code == 200


def test_del_1_al_10_la_fila_avisa_y_la_quincena_se_revisa_aparte(real):
    """De punta a punta, con el filtro por día: Otro período del 1 al 10
    deja todo afuera (Sin comparar, con el Comprobante y su período); la
    Revisión de la 1.ª quincena se guarda con ese período y no cubre el mes
    entero."""
    _con_diferencia(real)
    c = real.c

    r = c.get(f"{F}/resumen?desde=2026-10-01&hasta=2026-10-10")
    assert r.status_code == 200, r.text
    [fila] = r.json()["filas"]
    assert (fila["desde"], fila["hasta"], fila["estados"]) == (
        "2026-10-01", "2026-10-10", ["sin_comparar"])
    assert all(l["fuera_del_filtro"] for l in fila["grupos"])
    [fuera] = fila["comprobantes_fuera"]
    assert set(fuera) == CLAVES_COMPROBANTE_FUERA
    assert (fuera["tipo"], fuera["desde"], fuera["hasta"]) == (
        "factura", "2026-10-01", "2026-10-15")

    ruta = f"{F}/resumen/{detalle_a8.UNO}/2026-10"
    quincena = "desde=2026-10-01&hasta=2026-10-15"
    r = c.post(f"{ruta}/revision?{quincena}", json={"comentario": "Explicada."})
    assert r.status_code == 201, r.text
    assert (r.json()["desde"], r.json()["hasta"]) == ("2026-10-01", "2026-10-15")
    assert (r.json()["revision"]["desde"], r.json()["revision"]["hasta"]) == (
        "2026-10-01", "2026-10-15")
    mes = c.get(f"{F}/resumen?desde=2026-10-01&hasta=2026-10-31").json()["filas"][0]
    assert (mes["estados"], mes["diferencia_revisada"]) == (["con_diferencia"], False)

    r = c.delete(f"{ruta}/revision?{quincena}")
    assert r.status_code == 200, r.text
    assert r.json()["revision"] is None


def test_la_fila_y_el_detalle_traen_si_el_periodo_esta_en_curso(real):
    """Hoy es el 10 de noviembre: la 1.ª quincena de noviembre todavía no
    terminó y se controla igual (Pendiente de facturar), con `en_curso`;
    octubre ya terminó (plan del 2026-10-17)."""
    _con_diferencia(real)
    real.consulta.parte(detalle_a8.UNO, detalle_a8.PODA, date(2026, 11, 3), jornal="8")
    c = real.c

    r = c.get(f"{F}/resumen?desde=2026-10-01&hasta=2026-11-15")
    assert r.status_code == 200, r.text
    por_mes = {f["mes"]: (f["estados"], f["en_curso"]) for f in r.json()["filas"]}
    assert por_mes == {"2026-11": (["pendiente_de_facturar"], True),
                       "2026-10": (["con_diferencia"], False)}

    ruta = f"{F}/resumen/{detalle_a8.UNO}"
    r = c.get(f"{ruta}/2026-11?desde=2026-11-01&hasta=2026-11-15")
    assert r.status_code == 200, r.text
    assert (r.json()["estados"], r.json()["en_curso"]) == (["pendiente_de_facturar"], True)
    r = c.get(f"{ruta}/2026-10")
    assert r.status_code == 200, r.text
    assert r.json()["en_curso"] is False


def test_una_configuracion_invalida_es_422_con_el_campo(real):
    r = real.c.put(f"{F}/configuracion", json={"umbral_pct": "5", "mes_corte": "2026-12"})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["tipo"] == "configuracion_invalida"
    assert detail["campo"] == "mes_corte"
