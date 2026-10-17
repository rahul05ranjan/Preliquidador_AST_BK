"""Endpoints del Resumen de Facturación (plan de la E3, sección 3.2, rutas 13
a 17).

  - **Resumen** (13) y **Detalle** (14), de la pantalla `resumen` con Ver.
  - **Revisión de diferencia**: dejarla (15) y deshacerla (16), con Editar en
    `resumen`. Las dos devuelven el Detalle, así la pantalla sigue sin
    pedirlo otra vez.
  - **Configuración** (17): el Umbral y el Mes de corte, sólo el Admin.

El Detalle y la Revisión reciben el filtro del Resumen (desde y hasta,
"AAAA-MM-DD", opcionales): se recortan al mes y sin ellos son del mes entero.

Las reglas viven en ResumenService; acá sólo se traducen sus excepciones al
código y al `detail` del contrato. Si el campo no responde, la consulta
levanta ExternaNoDisponible y `app/main.py` la convierte en 503.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db_propia
from app.modulos.facturacion.api.comprobantes import get_consulta_externa
from app.modulos.facturacion.permisos import (
    editar_configuracion, editar_resumen, ver_resumen,
)
from app.modulos.facturacion.schemas import (
    ConfiguracionEntrada, ConfiguracionSalida, DetalleResumen, Resumen,
    RevisionEntrada,
)
from app.modulos.facturacion.services.consulta_externa import ConsultaExternaService
from app.modulos.facturacion.services.resumen_service import (
    ClienteNoEncontrado, ConfiguracionInvalida, ErrorResumen, FechaInvalida,
    MesInvalido, NoRevisable, RangoInvalido, ResumenService, RevisionInvalida,
    SinRevision,
)

# Permisos por pantalla (ADR-0020), uno por endpoint, como en comprobantes.py.
# El mapa lo fija tests/facturacion/test_mapa_permisos.py.
router = APIRouter(
    prefix="/api/facturacion",
    tags=["Facturación"],
)


def get_resumen(
    db_propia: Session = Depends(get_db_propia),
    consulta: ConsultaExternaService = Depends(get_consulta_externa),
) -> ResumenService:
    # La misma get_consulta_externa de Comprobantes: un override sirve para
    # los dos routers.
    return ResumenService(db_propia, consulta)


# Los 422 del contrato llevan el campo que falla; los 409, sólo tipo y
# mensaje (GUIA, regla 15).
_TIPOS_422 = {
    MesInvalido: "mes_invalido",
    FechaInvalida: "fecha_invalida",
    RangoInvalido: "rango_invalido",
    RevisionInvalida: "revision_invalida",
    ConfiguracionInvalida: "configuracion_invalida",
}
_TIPOS_409 = {
    NoRevisable: "no_revisable",
    SinRevision: "sin_revision",
}


def _http(error: ErrorResumen) -> HTTPException:
    """La excepción del servicio, con el código y el `detail` del contrato
    (sección 3.2, "Errores"). Una que no esté acá es un error de programación
    y sigue de largo como 500, en vez de disfrazarse de otro código."""
    if isinstance(error, ClienteNoEncontrado):
        return HTTPException(status_code=404, detail=error.mensaje)
    tipo = _TIPOS_422.get(type(error))
    if tipo is not None:
        return HTTPException(status_code=422, detail={
            "tipo": tipo, "mensaje": error.mensaje, "campo": error.campo,
        })
    tipo = _TIPOS_409.get(type(error))
    if tipo is None:
        raise error
    return HTTPException(status_code=409, detail={"tipo": tipo, "mensaje": error.mensaje})


# ─── Resumen y Detalle (rutas 13 y 14) ──────────────────────────────────────

@router.get("/resumen", response_model=Resumen, dependencies=[Depends(ver_resumen)])
def resumen(
    desde: str | None = None,
    hasta: str | None = None,
    refrescar: bool = False,
    servicio: ResumenService = Depends(get_resumen),
):
    """Una fila por Cliente y mes, de desde a hasta ("AAAA-MM-DD", los dos
    incluidos; hasta 12 meses), cada mes recortado al filtro. Sin desde o
    hasta, el 422 `fecha_invalida`. Con refrescar, vuelve a leer el campo
    ("Volver a leer")."""
    try:
        return servicio.resumen(desde, hasta, refrescar=refrescar)
    except ErrorResumen as error:
        raise _http(error) from None


@router.get("/resumen/{cliente_id}/{mes}", response_model=DetalleResumen,
            dependencies=[Depends(ver_resumen)])
def detalle(
    cliente_id: int,
    mes: str,
    refrescar: bool = False,
    desde: str | None = None,
    hasta: str | None = None,
    servicio: ResumenService = Depends(get_resumen),
):
    """El Cruce de un Cliente en un mes ("AAAA-MM"), una fila por grupo de
    tareas y unidad, con sus tareas y hasta los partes del campo. Con desde y
    hasta, el del filtro recortado al mes."""
    try:
        return servicio.detalle(cliente_id, mes, refrescar=refrescar,
                                desde=desde, hasta=hasta)
    except ErrorResumen as error:
        raise _http(error) from None


# ─── Revisión de diferencia (rutas 15 y 16) ─────────────────────────────────

@router.post("/resumen/{cliente_id}/{mes}/revision", response_model=DetalleResumen,
             status_code=201)
def revisar(
    cliente_id: int,
    mes: str,
    entrada: RevisionEntrada,
    desde: str | None = None,
    hasta: str | None = None,
    usuario=Depends(editar_resumen),
    servicio: ResumenService = Depends(get_resumen),
):
    """Deja una Revisión en un mes Con diferencia, con el período del filtro
    recortado al mes, y sella quién la dejó."""
    try:
        return servicio.revisar(cliente_id, mes, entrada.comentario,
                                usuario_id=getattr(usuario, "id", None),
                                desde=desde, hasta=hasta)
    except ErrorResumen as error:
        raise _http(error) from None


@router.delete("/resumen/{cliente_id}/{mes}/revision", response_model=DetalleResumen)
def deshacer_revision(
    cliente_id: int,
    mes: str,
    desde: str | None = None,
    hasta: str | None = None,
    usuario=Depends(editar_resumen),
    servicio: ResumenService = Depends(get_resumen),
):
    """Deshace la Revisión vigente del período (el filtro recortado al mes):
    queda en el registro, con quién la deshizo. Cualquiera con Editar en
    `resumen` deshace la de otro."""
    try:
        return servicio.deshacer_revision(cliente_id, mes,
                                          usuario_id=getattr(usuario, "id", None),
                                          desde=desde, hasta=hasta)
    except ErrorResumen as error:
        raise _http(error) from None


# ─── Configuración (ruta 17) ────────────────────────────────────────────────

@router.put("/configuracion", response_model=ConfiguracionSalida)
def cambiar_configuracion(
    entrada: ConfiguracionEntrada,
    usuario=Depends(editar_configuracion),
    servicio: ResumenService = Depends(get_resumen),
):
    """El Umbral y el Mes de corte. No hay GET aparte: el Resumen y el
    Detalle traen los dos valores (decisión 4)."""
    try:
        return servicio.cambiar_configuracion(
            entrada.umbral_pct, entrada.mes_corte,
            usuario_id=getattr(usuario, "id", None))
    except ErrorResumen as error:
        raise _http(error) from None
