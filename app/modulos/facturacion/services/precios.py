"""El Precio sugerido, la empresa sugerida y la unidad propuesta de un Cliente
(plan de la E3, paso A7, el contrato de la ruta 18 y la decisión 8 de la spec
de la E3b).

Salen de las Facturas del Cliente en la base propia, leídas siempre frescas:
- **Cuentan** las Facturas, también las del histórico.
- **No cuentan** las Notas de crédito ni los históricos pendientes de
  facturar, que no son lo que se cobró.

"La última" sigue el orden de la ruta 18: el mes de la Línea descendente,
después la fecha del Comprobante descendente y después su id descendente. Se
ordena en Python, como `historico.conciliar`, para que un Comprobante sin
fecha (un histórico) quede igual de último en SQLite y en MySQL.

Lo usan el Detalle (para valorizar lo que no tiene Facturas en el mes) y la
Precarga.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modulos.facturacion.models import Comprobante, LineaComprobante
from app.modulos.facturacion.services.reglas_comprobante import FACTURA

# Un Comprobante sin fecha (sólo un histórico puede no tenerla) queda detrás de
# cualquiera con fecha del mismo mes: no hay cómo saber si es más nuevo.
_SIN_FECHA = date.min


def _lineas_de_facturas(db: Session, cliente_id: int) -> list:
    """Las Líneas de las Facturas que cuentan para sugerir, con lo de su
    Comprobante."""
    return db.execute(
        select(Comprobante.id, Comprobante.numero, Comprobante.fecha,
               Comprobante.empresa_emisora, LineaComprobante.orden,
               LineaComprobante.fecha, LineaComprobante.tarea_id,
               LineaComprobante.unidad, LineaComprobante.precio_unitario)
        .join(LineaComprobante, LineaComprobante.comprobante_id == Comprobante.id)
        .where(Comprobante.cliente_id == cliente_id,
               Comprobante.tipo == FACTURA,
               Comprobante.pendiente_de_facturar.is_(False))
    ).all()


def _orden(mes_linea: date, fecha_comprobante: date | None, comprobante_id: int) -> tuple:
    """La clave del orden de la ruta 18: la mayor es la última."""
    return (mes_linea.replace(day=1), fecha_comprobante or _SIN_FECHA, comprobante_id)


def precios_sugeridos(db: Session, cliente_id: int) -> dict[tuple[int, str], dict]:
    """El Precio sugerido de cada (tarea_id, unidad) que el Cliente tiene
    facturada: el precio unitario de la última Factura que la trae.

    Devuelve {(tarea_id, unidad): {tarea_id, unidad, precio_unitario,
    comprobante_id, numero, fecha}}, donde `fecha` es la del Comprobante (None
    en un histórico sin fecha). Los valores son los `precios` de la ruta 18.
    Si la misma (tarea, unidad) aparece dos veces en esa Factura, vale la
    última Línea por orden.

    Si ese último precio es 0 o menos, la (tarea, unidad) no tiene Precio
    sugerido y no se devuelve, sin buscar una Factura anterior (paso A7b,
    decisión del usuario): un precio 0 suele ser un error de carga."""
    mejores: dict[tuple[int, str], tuple] = {}
    for (comprobante_id, numero, fecha, _empresa, orden, fecha_linea, tarea_id,
         unidad, precio_unitario) in _lineas_de_facturas(db, cliente_id):
        clave = (*_orden(fecha_linea, fecha, comprobante_id), orden)
        actual = mejores.get((tarea_id, unidad))
        if actual is None or clave > actual[0]:
            mejores[(tarea_id, unidad)] = (clave, {
                "tarea_id": tarea_id, "unidad": unidad,
                "precio_unitario": precio_unitario,
                "comprobante_id": comprobante_id, "numero": numero, "fecha": fecha,
            })
    return {par: precio for par, (_clave, precio) in mejores.items()
            if precio["precio_unitario"] > 0}


def unidades_propuestas(db: Session, cliente_id: int) -> dict[int, str]:
    """La unidad propuesta de cada tarea que el Cliente tiene facturada:
    {tarea_id: unidad} de la última Línea de Factura que la trae, con el
    mismo orden que el Precio sugerido (decisión 8 de la spec de la E3b).

    No mira el precio: una unidad cobrada a 0 sigue siendo la unidad en la
    que se le factura. Una tarea sin Facturas no figura, y la Precarga usa
    su Unidad sugerida."""
    mejores: dict[int, tuple] = {}
    for (comprobante_id, _numero, fecha, _empresa, orden, fecha_linea, tarea_id,
         unidad, _precio) in _lineas_de_facturas(db, cliente_id):
        clave = (*_orden(fecha_linea, fecha, comprobante_id), orden)
        actual = mejores.get(tarea_id)
        if actual is None or clave > actual[0]:
            mejores[tarea_id] = (clave, unidad)
    return {tarea_id: unidad for tarea_id, (_clave, unidad) in mejores.items()}


def empresa_sugerida(db: Session, cliente_id: int) -> str | None:
    """La Empresa emisora de la última Factura del Cliente que tiene empresa,
    o None si ninguna tiene (los históricos no traen empresa).

    Una Factura es tan nueva como su Línea más nueva: el mismo orden que el
    Precio sugerido, a nivel de Comprobante."""
    mejor = None
    for (comprobante_id, _numero, fecha, empresa, _orden_linea, fecha_linea,
         _tarea_id, _unidad, _precio) in _lineas_de_facturas(db, cliente_id):
        if not empresa:
            continue
        clave = _orden(fecha_linea, fecha, comprobante_id)
        if mejor is None or clave > mejor[0]:
            mejor = (clave, empresa)
    return mejor[1] if mejor else None
