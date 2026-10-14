"""Las fechas del módulo: hoy en UTC-3 y las cuentas con meses (plan de la E3,
decisión 6 y paso A2).

`hoy()` se prueba con el reloj del módulo cambiado a mano, como `_reloj()` de
la caché del campo: así no depende del huso de la máquina que corre los tests.
"""
from datetime import date, datetime, timezone

import pytest

from app.modulos.facturacion import fechas
from app.modulos.facturacion.fechas import (
    fin_de_mes,
    hoy,
    leer_mes,
    mes_siguiente,
    meses,
    mismo_mes,
)


@pytest.fixture
def ahora(monkeypatch):
    """Fija el reloj del módulo en el instante (UTC) que el test elija."""
    def fijar(instante):
        monkeypatch.setattr(fechas, "_ahora", lambda: instante)
    return fijar


# ─── hoy() ──────────────────────────────────────────────────────────────────

def test_a_las_dos_utc_del_dia_1_todavia_es_el_ultimo_dia_del_mes_anterior(ahora):
    ahora(datetime(2026, 11, 1, 2, 0, tzinfo=timezone.utc))
    assert hoy() == date(2026, 10, 31)


def test_a_las_tres_utc_ya_es_el_dia_1(ahora):
    ahora(datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc))
    assert hoy() == date(2026, 11, 1)


def test_el_cambio_de_anio_tambien_va_en_utc_menos_3(ahora):
    ahora(datetime(2027, 1, 1, 2, 59, tzinfo=timezone.utc))
    assert hoy() == date(2026, 12, 31)


def test_sin_reemplazo_hoy_es_una_fecha():
    assert isinstance(hoy(), date)
    assert not isinstance(hoy(), datetime)


# ─── leer_mes ───────────────────────────────────────────────────────────────

def test_leer_mes_da_el_dia_1():
    assert leer_mes("2026-09") == date(2026, 9, 1)
    assert leer_mes("2026-12") == date(2026, 12, 1)
    assert leer_mes("2027-01") == date(2027, 1, 1)


@pytest.mark.parametrize("texto", [
    "2026-13", "2026-00", "2026-9", "x", "", "2026-09-01", " 2026-09", "26-09",
])
def test_leer_mes_rechaza_lo_que_no_es_aaaa_mm(texto):
    with pytest.raises(ValueError):
        leer_mes(texto)


# ─── Cuentas con meses ──────────────────────────────────────────────────────

def test_fin_de_mes():
    assert fin_de_mes(date(2026, 9, 1)) == date(2026, 9, 30)
    assert fin_de_mes(date(2026, 10, 16)) == date(2026, 10, 31)
    assert fin_de_mes(date(2026, 2, 1)) == date(2026, 2, 28)
    assert fin_de_mes(date(2028, 2, 10)) == date(2028, 2, 29)
    assert fin_de_mes(date(2026, 12, 1)) == date(2026, 12, 31)


def test_mes_siguiente_da_el_dia_1_del_mes_que_sigue():
    assert mes_siguiente(date(2026, 9, 1)) == date(2026, 10, 1)
    assert mes_siguiente(date(2026, 9, 30)) == date(2026, 10, 1)
    assert mes_siguiente(date(2026, 12, 15)) == date(2027, 1, 1)


def test_meses_es_inclusivo():
    assert meses(date(2026, 8, 1), date(2026, 10, 1)) == [
        date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1),
    ]


def test_meses_de_un_solo_mes():
    assert meses(date(2026, 9, 1), date(2026, 9, 1)) == [date(2026, 9, 1)]


def test_meses_cruza_el_anio():
    assert meses(date(2026, 11, 1), date(2027, 2, 1)) == [
        date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1),
    ]


def test_mismo_mes():
    assert mismo_mes(date(2026, 9, 1), date(2026, 9, 30))
    assert not mismo_mes(date(2026, 9, 30), date(2026, 10, 1))
    assert not mismo_mes(date(2026, 9, 1), date(2027, 9, 1))
