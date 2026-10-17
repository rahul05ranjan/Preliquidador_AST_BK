"""El módulo Facturación en el registro y sus cuatro pantallas (plan de la E1,
D1, y plan de la E3, decisión 1).

Las claves de pantalla se guardan en la base (rol_permiso.pantalla) y no
cambian. El orden es el del editor de roles. Las claves retiradas no se
reutilizan nunca, porque un rol con permisos viejos ganaría la pantalla nueva:
`unidad` (Unidad de medida por defecto) se retiró el 2026-10-12, porque la
Unidad sugerida se lee del sistema de campo
(docs/superpowers/plans/2026-10-12-unidad-desde-campo.md); `pendientes` y
`cruce` se retiraron el 2026-10-14, porque el Resumen reemplaza a las dos
(docs/superpowers/plans/2026-10-14-facturacion-e3.md).
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.auth import get_usuario_actual
from app.main import app
from app.modulos import REGISTRO, activos
from app.modulos.facturacion import MODULO
from app.modulos.facturacion.permisos import PANTALLAS

# (clave, nombre, editable), en el orden del editor de roles.
CATALOGO_FACTURACION = [
    ("resumen", "Resumen", True),
    ("comprobantes", "Comprobantes", True),
    ("equivalencias", "Equivalencias", True),
    ("panel", "Panel", False),
]


def test_el_modulo_esta_registrado_y_activo():
    assert MODULO.clave == "facturacion"
    assert MODULO.activo is True
    assert MODULO in REGISTRO
    assert MODULO in activos()


CLAVES_RETIRADAS = ("unidad", "pendientes", "cruce")


def test_las_cuatro_pantallas_del_catalogo():
    assert [(p.clave, p.nombre, p.editable) for p in PANTALLAS] == CATALOGO_FACTURACION
    assert MODULO.pantallas == PANTALLAS
    assert all(p.requiere == () for p in PANTALLAS)
    editable = {p.clave: p.editable for p in PANTALLAS}
    assert editable["resumen"] is True, "Editar en Resumen es dejar o deshacer una Revisión"
    assert editable["panel"] is False


def test_las_claves_retiradas_no_se_reutilizan():
    claves = {p.clave for p in PANTALLAS}
    reutilizadas = [c for c in CLAVES_RETIRADAS if c in claves]
    assert not reutilizadas, (
        f"claves retiradas que volvieron al catálogo: {reutilizadas}. "
        "No se reutilizan nunca: un rol con permisos viejos ganaría la pantalla nueva"
    )


def test_auth_modulos_publica_las_cuatro_en_orden():
    usuario = SimpleNamespace(id=1, nombre="T", email="t@t.com", rol="admin", activo=True, modulos=[])
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    try:
        r = TestClient(app).get("/api/auth/modulos")
    finally:
        app.dependency_overrides.pop(get_usuario_actual, None)
    assert r.status_code == 200
    por_clave = {m["clave"]: m for m in r.json()}
    pantallas = por_clave["facturacion"]["pantallas"]
    assert [(p["clave"], p["nombre"], p["editable"]) for p in pantallas] == CATALOGO_FACTURACION
    assert all(p["requiere"] == [] for p in pantallas)
    assert not {p["clave"] for p in pantallas} & set(CLAVES_RETIRADAS)
