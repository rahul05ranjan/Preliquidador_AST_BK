"""La lectura del campo para el Cruce (plan de la E3, decisión 6, paso A4).

El SQL es de MySQL y no corre en SQLite: acá se prueba lo que el módulo pone y
saca de la base —qué ramas tiene la consulta de partes, qué deja afuera, cómo
filtra el rango, qué parámetros manda y cómo arma cada fila— y la caché de 10
minutos con su hora de lectura. El SQL real corre en el smoke contra `testing`
(F4). Datos inventados.
"""
import re
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.modulos.facturacion.services import consulta_externa
from app.modulos.facturacion.services.consulta_externa import (
    QUERY_PARTES_DE_CLIENTE,
    QUERY_TAREAS_CON_BAJA,
    QUERY_TRABAJADO_POR_MES,
    ConsultaExternaService,
    invalidar_cache,
    invalidar_cache_cruce,
)


class ResultadoFalso:
    def __init__(self, filas):
        self._filas = filas

    def fetchall(self):
        return list(self._filas)


class SesionFalsa:
    """Anota con qué la llamaron y devuelve las filas que se le pasaron."""

    def __init__(self, filas=()):
        self.filas = filas
        self.llamadas = []

    def execute(self, query, params=None):
        self.llamadas.append((query, params))
        return ResultadoFalso(self.filas)


class Reloj:
    """Reemplaza el reloj de la caché: avanza sólo cuando el test lo pide."""

    def __init__(self, ahora=1000.0):
        self.ahora = ahora

    def __call__(self):
        return self.ahora


class Hora:
    """Reemplaza ahora_utc: la hora que se anota como leido_en."""

    def __init__(self, ahora):
        self.ahora = ahora

    def __call__(self):
        return self.ahora


LEIDA = datetime(2026, 10, 14, 13, 5, 0)


@pytest.fixture(autouse=True)
def cache_limpia():
    invalidar_cache()
    yield
    invalidar_cache()


@pytest.fixture
def reloj(monkeypatch):
    r = Reloj()
    monkeypatch.setattr(consulta_externa, "_reloj", r)
    return r


@pytest.fixture
def hora(monkeypatch):
    h = Hora(LEIDA)
    monkeypatch.setattr(consulta_externa, "ahora_utc", h)
    return h


def _sql(query) -> str:
    return " ".join(str(query).split())


def _where(sql: str) -> list[str]:
    """Cada WHERE de la consulta, hasta el GROUP BY de su rama."""
    return re.findall(r"WHERE (.*?) GROUP BY", sql)


CONSULTAS = [QUERY_TRABAJADO_POR_MES, QUERY_PARTES_DE_CLIENTE]
IDS = ["trabajado", "partes"]


# ─── El SQL ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", CONSULTAS, ids=IDS)
def test_el_sql_tiene_las_tres_ramas_del_cruce(query):
    sql = _sql(query)
    assert "FROM laa_pdpulverizadas pdpulve" in sql
    assert "INNER JOIN laa_pdpulverizadasregistros pregistros" in sql
    assert "FROM laa_pdmaquinarias pdmaquinarias" in sql
    assert "INNER JOIN laa_pdmaquinariasregistros mregistros" in sql
    assert "FROM laa_pdtareasmanuales pdtareas" in sql
    assert "INNER JOIN laa_pdtareasmanualesregistros tregistros" in sql
    assert sql.count("UNION ALL") == 2


@pytest.mark.parametrize("query", CONSULTAS, ids=IDS)
def test_el_sql_no_tiene_cosecha_ni_el_tractor_2(query):
    sql = _sql(query)
    assert "pdcosechas" not in sql
    assert "cosecha" not in sql.lower()
    for columna in ("trancadas2", "hsjornal2", "hsmaquina2", "tractor2"):
        assert columna not in sql


@pytest.mark.parametrize("query", CONSULTAS, ids=IDS)
def test_el_rango_es_semiabierto_y_sin_date_en_el_filtro(query):
    sql = _sql(query)
    filtros = _where(sql)
    assert len(filtros) == 3
    for filtro in filtros:
        assert "DATE(" not in filtro
        assert "BETWEEN" not in filtro
    assert "pdpulve.fecha >= :desde AND pdpulve.fecha < :hasta_exclusivo" in sql
    assert ("pdmaquinarias.fecha >= :desde AND pdmaquinarias.fecha < :hasta_exclusivo"
            in sql)
    assert "pdtareas.fecha >= :desde AND pdtareas.fecha < :hasta_exclusivo" in sql


@pytest.mark.parametrize("query", CONSULTAS, ids=IDS)
def test_las_bajas_se_filtran_en_cabecera_y_en_registro(query):
    sql = _sql(query)
    assert "pregistros.estado <> 9" in sql and "pdpulve.estado <> 9" in sql
    assert "mregistros.estado <> 9" in sql and "pdmaquinarias.estado <> 9" in sql
    assert "tregistros.estado <> 9" in sql and "pdtareas.estado <> 9" in sql


@pytest.mark.parametrize("query", CONSULTAS, ids=IDS)
def test_las_cuatro_medidas_pasan_por_regexp_antes_de_convertir(query):
    sql = _sql(query)
    for campo in ("pregistros.trancadas1", "pregistros.hsjornal1",
                  "pregistros.hsmaquina1",
                  "mregistros.hsjornal", "mregistros.hsmaquina", "mregistros.unidades",
                  "tregistros.hsjornal", "tregistros.unidades"):
        assert f"CASE WHEN TRIM({campo}) REGEXP '^[0-9]*[.]?[0-9]+$'" in sql, campo
        assert f"CAST(TRIM({campo}) AS DECIMAL(" in sql, campo


@pytest.mark.parametrize("query", CONSULTAS, ids=IDS)
def test_pulverizacion_es_una_fila_por_parte_con_unidades_en_cero(query):
    sql = _sql(query)
    # Como la consulta de Power BI: en pulverización las unidades son 0 y no
    # se lee la columna de la cabecera.
    pulverizacion = sql.split("UNION ALL")[0]
    assert "FROM laa_pdpulverizadas pdpulve" in pulverizacion
    assert "0 AS unidades" in pulverizacion
    assert "pdpulve.unidades" not in sql
    assert "SUM(CASE WHEN TRIM(pregistros.trancadas1)" in sql
    assert "GROUP BY pdpulve.id" in sql
    # Maquinaria y tareas manuales, por cabecera y tarea.
    assert "GROUP BY pdmaquinarias.id, mregistros.tarea" in sql
    assert "GROUP BY pdtareas.id, tregistros.tarea" in sql


@pytest.mark.parametrize("query", CONSULTAS, ids=IDS)
def test_el_supervisor_y_la_finca_salen_con_los_joins_de_preliquidacion(query):
    sql = _sql(query)
    assert "LEFT JOIN ast_users supervisor ON supervisor.id = pdpulve.supervisor" in sql
    assert ("LEFT JOIN laa_supervisores supervisores ON pdmaquinarias.supervisor = "
            "supervisores.idusuario") in sql
    assert ("LEFT JOIN laa_supervisores supervisores ON supervisores.idusuario = "
            "pdtareas.supervisor") in sql
    assert sql.count("LEFT JOIN laa_fincas fincas") == 3


def test_el_sql_de_trabajado_agrupa_por_cliente_tarea_anio_y_mes():
    sql = _sql(QUERY_TRABAJADO_POR_MES)
    assert "GROUP BY p.cliente_id, p.tarea_id, YEAR(p.fecha), MONTH(p.fecha)" in sql
    assert "COUNT(*) AS partes" in sql
    assert ":cliente_id" not in sql


def test_el_sql_de_partes_filtra_el_cliente_en_cada_rama():
    sql = _sql(QUERY_PARTES_DE_CLIENTE)
    assert "pdpulve.cliente = :cliente_id" in sql
    assert "pdmaquinarias.cliente = :cliente_id" in sql
    assert "pdtareas.cliente = :cliente_id" in sql


# ─── Lo que manda y lo que arma ─────────────────────────────────────────────

def test_trabajado_por_mes_manda_el_dia_siguiente_al_hasta_como_hasta_exclusivo(hora):
    # Por día (spec de la E3a por grupo, decisión 6): una sola consulta para
    # todo el filtro, agrupada por mes en la base.
    externa = SesionFalsa()
    servicio = ConsultaExternaService(externa)
    servicio.trabajado_por_mes(date(2025, 11, 1), date(2025, 12, 31))
    servicio.trabajado_por_mes(date(2025, 11, 20), date(2025, 12, 10))

    (query, p1), (_, p2) = externa.llamadas
    assert query is QUERY_TRABAJADO_POR_MES
    assert p1 == {"desde": date(2025, 11, 1), "hasta_exclusivo": date(2026, 1, 1)}
    assert p2 == {"desde": date(2025, 11, 20), "hasta_exclusivo": date(2025, 12, 11)}


def test_partes_de_cliente_manda_el_dia_siguiente_al_hasta_como_hasta_exclusivo(hora):
    externa = SesionFalsa()
    servicio = ConsultaExternaService(externa)
    servicio.partes_de_cliente(7, date(2026, 9, 1), date(2026, 9, 30))
    servicio.partes_de_cliente(7, date(2026, 9, 1), date(2026, 9, 15))

    (q1, p1), (_, p2) = externa.llamadas
    assert q1 is QUERY_PARTES_DE_CLIENTE
    # Del mes entero: el primer día del mes siguiente.
    assert p1 == {"cliente_id": 7, "desde": date(2026, 9, 1),
                  "hasta_exclusivo": date(2026, 10, 1)}
    # De una quincena (la Precarga).
    assert p2 == {"cliente_id": 7, "desde": date(2026, 9, 1),
                  "hasta_exclusivo": date(2026, 9, 16)}


def test_trabajado_por_mes_arma_cada_fila_y_un_none_se_lee_como_0(hora):
    externa = SesionFalsa(filas=[
        (7, 12, 2026, 9, Decimal("10.50"), Decimal("2.00"), None, Decimal("3.00"), 4),
        (8, 15, 2026, 8, None, None, Decimal("1.25"), None, 1),
    ])
    lectura = ConsultaExternaService(externa).trabajado_por_mes(
        date(2026, 8, 1), date(2026, 9, 1))

    assert lectura == {"leido_en": LEIDA, "filas": [
        {"cliente_id": 7, "tarea_id": 12, "mes": date(2026, 9, 1),
         "horas_jornal": Decimal("10.50"), "horas_maquina": Decimal("2.00"),
         "unidades": Decimal("0"), "tancadas": Decimal("3.00"), "partes": 4},
        {"cliente_id": 8, "tarea_id": 15, "mes": date(2026, 8, 1),
         "horas_jornal": Decimal("0"), "horas_maquina": Decimal("0"),
         "unidades": Decimal("1.25"), "tancadas": Decimal("0"), "partes": 1},
    ]}


def test_partes_de_cliente_arma_un_parte_por_fila_con_la_fecha_sin_hora(hora):
    externa = SesionFalsa(filas=[
        (datetime(2026, 9, 2, 3, 0), 12, "FINCA A", "SUPERVISOR UNO",
         Decimal("8.00"), None, None, None),
        (date(2026, 9, 3), 15, None, None, None, Decimal("1.50"),
         Decimal("2.00"), Decimal("4.00")),
    ])
    lectura = ConsultaExternaService(externa).partes_de_cliente(
        7, date(2026, 9, 1), date(2026, 9, 30))

    assert lectura == {"leido_en": LEIDA, "filas": [
        {"fecha": date(2026, 9, 2), "tarea_id": 12, "donde": "FINCA A",
         "supervisor": "SUPERVISOR UNO", "horas_jornal": Decimal("8.00"),
         "horas_maquina": Decimal("0"), "unidades": Decimal("0"),
         "tancadas": Decimal("0")},
        {"fecha": date(2026, 9, 3), "tarea_id": 15, "donde": None,
         "supervisor": None, "horas_jornal": Decimal("0"),
         "horas_maquina": Decimal("1.50"), "unidades": Decimal("2.00"),
         "tancadas": Decimal("4.00")},
    ]}


def test_tareas_cruce_lee_el_maestro_con_las_bajas(hora):
    externa = SesionFalsa(filas=[(5, "TAREA A", "G;P;PLANTA")])
    lectura = ConsultaExternaService(externa).tareas_cruce()

    query, _ = externa.llamadas[0]
    assert query is QUERY_TAREAS_CON_BAJA
    assert lectura == {"leido_en": LEIDA, "filas": [
        {"tarea_id": 5, "nombre": "TAREA A", "grupo_tarea": "G",
         "unidad_sugerida": "plantas", "no_facturable": False}]}


# ─── La caché ───────────────────────────────────────────────────────────────

LECTURAS = [
    lambda s: s.trabajado_por_mes(date(2026, 8, 1), date(2026, 9, 30)),
    lambda s: s.partes_de_cliente(7, date(2026, 9, 1), date(2026, 9, 30)),
    lambda s: s.tareas_cruce(),
]
IDS_LECTURAS = ["trabajado_por_mes", "partes_de_cliente", "tareas_cruce"]


@pytest.mark.parametrize("llamar", LECTURAS, ids=IDS_LECTURAS)
def test_la_segunda_llamada_dentro_de_10_minutos_no_consulta(reloj, hora, llamar):
    externa = SesionFalsa()
    primera = llamar(ConsultaExternaService(externa))
    reloj.ahora += 599
    segunda = llamar(ConsultaExternaService(externa))

    assert segunda == primera
    assert len(externa.llamadas) == 1


@pytest.mark.parametrize("llamar", LECTURAS, ids=IDS_LECTURAS)
def test_con_el_reloj_adelantado_600_segundos_vuelve_a_consultar(reloj, hora, llamar):
    externa = SesionFalsa()
    llamar(ConsultaExternaService(externa))
    reloj.ahora += 600
    llamar(ConsultaExternaService(externa))

    assert len(externa.llamadas) == 2


@pytest.mark.parametrize("llamar", LECTURAS, ids=IDS_LECTURAS)
def test_leido_en_es_la_hora_de_la_lectura_y_no_la_de_la_llamada(reloj, hora, llamar):
    externa = SesionFalsa()
    llamar(ConsultaExternaService(externa))
    hora.ahora = datetime(2026, 10, 14, 13, 9, 0)
    reloj.ahora += 240

    assert llamar(ConsultaExternaService(externa))["leido_en"] == LEIDA


def test_la_cache_de_partes_es_por_cliente_y_rango(reloj, hora):
    externa = SesionFalsa()
    servicio = ConsultaExternaService(externa)
    servicio.partes_de_cliente(7, date(2026, 9, 1), date(2026, 9, 30))
    servicio.partes_de_cliente(8, date(2026, 9, 1), date(2026, 9, 30))
    servicio.partes_de_cliente(7, date(2026, 9, 1), date(2026, 9, 15))
    servicio.partes_de_cliente(7, date(2026, 9, 1), date(2026, 9, 30))

    assert len(externa.llamadas) == 3


def test_invalidar_cache_cruce_borra_lo_del_cruce_y_no_clientes_ni_empresas(reloj, hora):
    externa = SesionFalsa(filas=[])
    clientes = SesionFalsa(filas=[(1, "CLIENTE UNO")])
    sueldos = SesionFalsa(filas=[("EMPRESA A",)])
    ConsultaExternaService(clientes, sueldos).clientes()
    ConsultaExternaService(clientes, sueldos).empresas()
    ConsultaExternaService(clientes).fincas_de_cliente(7)
    for llamar in LECTURAS:
        llamar(ConsultaExternaService(externa))

    invalidar_cache_cruce()

    ConsultaExternaService(clientes, sueldos).clientes()
    ConsultaExternaService(clientes, sueldos).empresas()
    ConsultaExternaService(clientes).fincas_de_cliente(7)
    for llamar in LECTURAS:
        llamar(ConsultaExternaService(externa))

    # Clientes, empresas y fincas siguen en la caché; las tres del Cruce se
    # vuelven a leer.
    assert len(clientes.llamadas) == 2
    assert len(sueldos.llamadas) == 1
    assert len(externa.llamadas) == 6
