"""Las fechas del módulo: qué día es hoy y las cuentas con meses.

Un mes se representa con su día 1 (`date`). Hoy va en UTC-3 fijo, en este
único lugar: no se conoce el huso del VPS, así que `date.today()` no sirve, y
`zoneinfo` pediría `tzdata`, una dependencia nueva (plan de la E3, decisión 6).
"""

import calendar
import re
from datetime import date, datetime, timedelta, timezone

HUSO = timezone(timedelta(hours=-3))

_MES = re.compile(r"\d{4}-\d{2}")


def _ahora() -> datetime:
    """El reloj del módulo, en UTC; los tests lo reemplazan."""
    return datetime.now(timezone.utc)


def hoy() -> date:
    """La fecha de hoy en UTC-3."""
    return _ahora().astimezone(HUSO).date()


def leer_mes(texto: str) -> date:
    """"AAAA-MM" al día 1 de ese mes. Cualquier otra forma da ValueError."""
    if not isinstance(texto, str) or not _MES.fullmatch(texto):
        raise ValueError(f"Mes inválido: {texto!r}. Va como AAAA-MM.")
    anio, mes = int(texto[:4]), int(texto[5:])
    if not 1 <= mes <= 12:
        raise ValueError(f"Mes inválido: {texto!r}. Va como AAAA-MM.")
    return date(anio, mes, 1)


def fin_de_mes(fecha: date) -> date:
    """El último día del mes de la fecha."""
    return fecha.replace(day=calendar.monthrange(fecha.year, fecha.month)[1])


def mes_siguiente(fecha: date) -> date:
    """El día 1 del mes que sigue al de la fecha."""
    return fin_de_mes(fecha) + timedelta(days=1)


def meses(desde: date, hasta: date) -> list[date]:
    """El día 1 de cada mes entre los de desde y hasta, los dos incluidos."""
    resultado = []
    actual = desde.replace(day=1)
    while actual <= hasta:
        resultado.append(actual)
        actual = mes_siguiente(actual)
    return resultado


def mismo_mes(a: date, b: date) -> bool:
    return (a.year, a.month) == (b.year, b.month)
