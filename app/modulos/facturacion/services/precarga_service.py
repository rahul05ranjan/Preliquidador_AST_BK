"""La Precarga de una Factura (spec de la E3b, Ticket 2, y el contrato de la
ruta 18 del plan de la E3).

Arma lo que la pantalla necesita para proponer una Factura de un Cliente en un
Período facturado:
- **lo trabajado**: una entrada por tarea con partes del Cliente en el
  período, con lo del maestro de tareas, la unidad propuesta y todas las
  medidas por unidad (`campo`), para que la pantalla cambie de unidad sin
  volver a pedir (decisión 7);
- **los precios**: el Precio sugerido por (tarea, unidad), con su Comprobante
  de origen (paso A7);
- **la Empresa sugerida**, la de la última Factura con empresa.

La unidad propuesta es la de la última Factura del Cliente por esa tarea, sin
las Notas de crédito; si no hay, la Unidad sugerida (decisión 8). Qué tareas
entran en la Factura (todas salvo las No facturable, hasta el tope de 15) lo
decide la pantalla: acá van todas las trabajadas, marcadas.

Los partes y el maestro de tareas van con la caché de la consulta; lo
facturado, fresco.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.modulos.facturacion import fechas
from app.modulos.facturacion.services.cruce import (
    MEDIDA_DE_UNIDAD, cantidad_en_unidad, medidas_por_tarea,
)
from app.modulos.facturacion.services.precios import (
    empresa_sugerida, precios_sugeridos, unidades_propuestas,
)
from app.modulos.facturacion.services.resumen_service import ResumenService


class ErrorPrecarga(Exception):
    mensaje = "No se pudo armar la Precarga."

    def __init__(self, mensaje: str | None = None):
        if mensaje:
            self.mensaje = mensaje
        super().__init__(self.mensaje)


class PeriodoInvalido(ErrorPrecarga):
    """422 `periodo_invalido`, con el campo que hay que mover: falta, mal
    escrito, Hasta antes de Desde o un período que cruza de mes."""

    def __init__(self, campo: str, mensaje: str):
        self.campo = campo
        super().__init__(mensaje)


class ClienteNoEncontrado(ErrorPrecarga):
    """404: el Cliente no está en el maestro (con las bajas) y no tiene ningún
    Comprobante. Es la misma regla que el Detalle."""
    mensaje = "No existe ese Cliente."


def _leer_dia(texto: str | None, campo: str) -> date:
    if texto is None or texto == "":
        raise PeriodoInvalido(campo, "Falta el período facturado.")
    try:
        return fechas.leer_dia(texto)
    except ValueError:
        raise PeriodoInvalido(
            campo, "La fecha va como AAAA-MM-DD, por ejemplo 2026-10-15.") from None


def leer_periodo(desde: str | None, hasta: str | None) -> tuple[date, date]:
    """El Período facturado de la Precarga, validado antes de leer nada. Los
    mensajes son los del alta de un Comprobante."""
    dia_desde = _leer_dia(desde, "desde")
    dia_hasta = _leer_dia(hasta, "hasta")
    if dia_hasta < dia_desde:
        raise PeriodoInvalido("hasta", "La fecha final no puede ser anterior a la inicial.")
    if not fechas.mismo_mes(dia_desde, dia_hasta):
        raise PeriodoInvalido("hasta", "El período tiene que quedar dentro de un mismo mes.")
    return dia_desde, dia_hasta


class PrecargaService:
    def __init__(self, db: Session, consulta):
        """`consulta` es la del campo (ConsultaExternaService o un doble): usa
        partes_de_cliente, tareas_cruce y clientes."""
        self.db = db
        self.consulta = consulta

    def precarga(self, cliente_id: int, desde: str | None, hasta: str | None) -> dict:
        """La ruta 18. Desde y Hasta van como "AAAA-MM-DD", los dos incluidos y
        dentro de un mismo mes. Valida el período y después el Cliente, antes
        de leer los partes."""
        dia_desde, dia_hasta = leer_periodo(desde, hasta)
        nombre = ResumenService(self.db, self.consulta).nombres_de_clientes(
            {cliente_id}).get(cliente_id)
        if nombre is None:
            raise ClienteNoEncontrado()

        partes = self.consulta.partes_de_cliente(cliente_id, dia_desde, dia_hasta)
        tareas = self.consulta.tareas_cruce()
        maestro = {t["tarea_id"]: t for t in tareas["filas"]}
        propuestas = unidades_propuestas(self.db, cliente_id)

        trabajado = []
        for tarea_id, medidas in medidas_por_tarea(partes["filas"]).items():
            tarea = maestro.get(tarea_id, {})
            sugerida = tarea.get("unidad_sugerida")
            trabajado.append({
                "tarea_id": tarea_id,
                "tarea_nombre": tarea.get("nombre"),
                "grupo_tarea": tarea.get("grupo_tarea"),
                "unidad_sugerida": sugerida,
                "unidad_propuesta": propuestas.get(tarea_id, sugerida),
                "no_facturable": bool(tarea.get("no_facturable", False)),
                "campo": {unidad: cantidad_en_unidad(medidas, unidad)
                          for unidad in MEDIDA_DE_UNIDAD},
            })
        trabajado.sort(key=lambda t: (t["tarea_nombre"] is None,
                                      t["tarea_nombre"] or "", t["tarea_id"]))

        return {
            "cliente_id": cliente_id,
            "cliente_nombre": nombre,
            "empresa_sugerida": empresa_sugerida(self.db, cliente_id),
            "leido_en": min(partes["leido_en"], tareas["leido_en"]),
            "trabajado": trabajado,
            "precios": sorted(precios_sugeridos(self.db, cliente_id).values(),
                              key=lambda p: (p["tarea_id"], p["unidad"])),
        }
