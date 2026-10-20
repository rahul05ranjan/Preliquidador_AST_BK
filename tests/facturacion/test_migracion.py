"""Las migraciones de Facturación: la 001 creó facturacion_tarea, la 002 la borra,
la 003 crea las tablas de Comprobantes (E2), la 004 las de la configuración y la
Revisión de diferencia (E3), la 005 borra los permisos guardados de las
pantallas retiradas `pendientes` y `cruce`, la 006 pasa la Revisión a grupos
y le suma su período (spec de la E3a por grupo) y la 007 le suma al
Comprobante su Período facturado (spec de la E3b).

Se leen los `.sql` como texto, sin base, como en tests/core/test_migracion_roles.py.
Desde el 2026-10-12 la Unidad sugerida se lee del sistema de campo
(docs/superpowers/plans/2026-10-12-unidad-desde-campo.md): la tabla sale del
modelo y ningún código la lee, así que el backend de esta versión arranca con
la tabla todavía en la base y la 002 se aplica después del reinicio.
"""
import re
from pathlib import Path

import pytest

# Importar app.main registra en Base.metadata las tablas del núcleo y las de
# los módulos activos, igual que al arrancar la app.
import app.main  # noqa: F401
from app.core.database import Base

RAIZ = Path(__file__).resolve().parents[2]
CARPETA = RAIZ / "migrations" / "facturacion"
M001 = CARPETA / "001_unidad_por_tarea.sql"
M002 = CARPETA / "002_borrar_unidad_por_tarea.sql"
M003 = CARPETA / "003_comprobantes.sql"
M004 = CARPETA / "004_resumen.sql"
M005 = CARPETA / "005_borrar_pendientes_y_cruce.sql"
M006 = CARPETA / "006_revision_por_grupo.sql"
M007 = CARPETA / "007_periodo_facturado.sql"
ORDEN = RAIZ / "migrations" / "ORDEN.txt"


def _sql(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _entradas_de_orden() -> list[str]:
    return [
        linea.split()[0] for linea in _sql(ORDEN).splitlines()
        if linea.strip() and not linea.strip().startswith("#")
    ]


def _sentencias(sql: str) -> list[str]:
    """Corta como el aplicador (por `;`, salteando los trozos que son sólo
    comentarios) y deja cada sentencia sin sus líneas de comentario y con los
    espacios colapsados."""
    sentencias = []
    for trozo in sql.split(";"):
        lineas = [
            linea.strip() for linea in trozo.splitlines()
            if linea.strip() and not linea.strip().startswith("--")
        ]
        if lineas:
            sentencias.append(re.sub(r"\s+", " ", " ".join(lineas)))
    return sentencias


# 1. La trampa del aplicador: corta el archivo por `;`, así que lo que siga a un
#    `;` en una línea comentada quedaría sin `--` y se ejecutaría.

@pytest.mark.parametrize(
    "ruta", [M001, M002, M003, M004, M005, M006, M007],
    ids=["001", "002", "003", "004", "005", "006", "007"],
)
def test_ninguna_linea_comentada_tiene_punto_y_coma(ruta):
    malas = [
        linea for linea in _sql(ruta).splitlines()
        if linea.strip().startswith("--") and ";" in linea
    ]
    assert malas == []


# 2. La 002 borra los permisos guardados de `unidad` y la tabla, y nada más.

def test_sentencias_de_la_002():
    assert _sentencias(_sql(M002)) == [
        "DELETE FROM rol_permiso WHERE modulo = 'facturacion' AND pantalla = 'unidad'",
        "DROP TABLE IF EXISTS facturacion_tarea",
    ]


# 3. La 002 va con el deploy, después del reinicio del backend.

def test_la_002_no_es_diferible():
    assert "-- NO DIFERIBLE" in _sql(M002)


# 4. En una base nueva corre la 001 y después la 002, que la borra. No se pide
#    que la 002 sea la última: la E2 suma la 003.

def test_la_002_va_despues_de_la_001_en_orden():
    entradas = [
        linea.split()[0] for linea in _sql(ORDEN).splitlines()
        if linea.strip() and not linea.strip().startswith("#")
    ]
    assert "facturacion/001_unidad_por_tarea.sql" in entradas
    assert "facturacion/002_borrar_unidad_por_tarea.sql" in entradas
    assert (
        entradas.index("facturacion/002_borrar_unidad_por_tarea.sql")
        > entradas.index("facturacion/001_unidad_por_tarea.sql")
    )


# 5. El modelo ya no declara la tabla: el chequeo de tablas del arranque no la
#    pide, y el backend arranca con o sin ella en la base.

def test_el_modelo_no_declara_facturacion_tarea():
    assert "facturacion_tarea" not in Base.metadata.tables


# 6. El código nuevo no lee la tabla: si la leyera, la 002 lo rompería.

def test_ningun_py_de_app_ni_de_scripts_nombra_la_tabla():
    nombran = [
        str(ruta.relative_to(RAIZ))
        for carpeta in ("app", "scripts")
        for ruta in (RAIZ / carpeta).rglob("*.py")
        if "facturacion_tarea" in ruta.read_text(encoding="utf-8")
    ]
    assert nombran == []


# 7. La 005 borra los permisos guardados de las pantallas retiradas, y nada más.

def test_sentencias_de_la_005():
    assert _sentencias(_sql(M005)) == [
        "DELETE FROM rol_permiso WHERE modulo = 'facturacion' "
        "AND pantalla IN ('pendientes', 'cruce')",
    ]


# 8. Las dos van con el deploy: la 004 antes del reinicio y la 005 después.

@pytest.mark.parametrize("ruta", [M004, M005], ids=["004", "005"])
def test_la_004_y_la_005_no_son_diferibles(ruta):
    assert "-- NO DIFERIBLE" in _sql(ruta)


# 9. En ORDEN.txt, la 004 después de la 003 y la 005 después de la 004.

def test_la_004_y_la_005_van_en_orden():
    entradas = _entradas_de_orden()
    m003 = "facturacion/003_comprobantes.sql"
    m004 = "facturacion/004_resumen.sql"
    m005 = "facturacion/005_borrar_pendientes_y_cruce.sql"
    assert m004 in entradas and m005 in entradas
    assert entradas.index(m003) < entradas.index(m004) < entradas.index(m005)


# 10. Las columnas de cada CREATE TABLE de la 004, con lo que les cambia la
#     006, son las del modelo, con el patrón de tests/core/test_migracion_roles.py.

CREATE_TABLE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\)\s*ENGINE", re.IGNORECASE | re.DOTALL
)
NO_SON_COLUMNAS = {"UNIQUE", "CONSTRAINT", "PRIMARY", "KEY", "INDEX", "FOREIGN", "REFERENCES"}


def _tablas_creadas(sql: str) -> dict[str, set]:
    tablas = {}
    for nombre, cuerpo in CREATE_TABLE.findall(sql):
        columnas = set()
        for linea in cuerpo.splitlines():
            palabras = linea.strip().split()
            if (
                palabras and not palabras[0].startswith("--")
                and palabras[0].upper() not in NO_SON_COLUMNAS
            ):
                columnas.add(palabras[0])
        tablas[nombre] = columnas
    return tablas


def test_columnas_de_las_tablas_de_la_004_coinciden_con_los_modelos():
    tablas = _tablas_creadas(_sql(M004))
    assert set(tablas) == {
        "facturacion_configuracion", "facturacion_revision", "facturacion_revision_tarea",
    }
    # La 006 borra la tabla por tarea y le suma el período a la Revisión.
    assert "facturacion_revision_tarea" not in Base.metadata.tables
    del tablas["facturacion_revision_tarea"]
    tablas["facturacion_revision"] |= {"desde", "hasta"}
    for nombre, columnas in tablas.items():
        del_modelo = set(Base.metadata.tables[nombre].columns.keys())
        assert columnas == del_modelo, nombre


# 11. Las tres con el motor, el charset y la collation de la 003.

def test_las_tablas_de_la_004_usan_el_motor_y_la_collation_de_la_003():
    sufijo = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    assert _sql(M004).count(sufijo) == 3


# 12. La 006 va con el deploy, ANTES de reiniciar el backend, como la 004: el
#     código de esta versión lee el período y los grupos de la Revisión.

def test_la_006_no_es_diferible_y_va_antes_del_reinicio():
    sql = _sql(M006)
    assert "-- NO DIFERIBLE" in sql
    assert "ANTES de reiniciar el backend" in sql


# 13. En ORDEN.txt, la 006 después de la 005 (el orden de una base nueva). La
#     E3b suma la 007 después.

def test_la_006_va_despues_de_la_005():
    entradas = _entradas_de_orden()
    m005 = "facturacion/005_borrar_pendientes_y_cruce.sql"
    m006 = "facturacion/006_revision_por_grupo.sql"
    assert entradas.index(m005) < entradas.index(m006)


# 14. La tabla nueva tiene las columnas del modelo, el motor y la collation de
#     la 003, y cae con su Revisión.

def test_la_006_crea_la_tabla_de_grupos_como_el_modelo():
    sql = _sql(M006)
    tablas = _tablas_creadas(sql)
    assert set(tablas) == {"facturacion_revision_grupo"}
    del_modelo = set(Base.metadata.tables["facturacion_revision_grupo"].columns.keys())
    assert tablas["facturacion_revision_grupo"] == del_modelo
    sentencia = next(s for s in _sentencias(sql) if "facturacion_revision_grupo (" in s)
    assert sentencia.endswith(
        "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci")
    assert ("FOREIGN KEY (revision_id) REFERENCES facturacion_revision (id) "
            "ON DELETE CASCADE") in sentencia


# 15. La 006 borra la tabla por tarea, llena el período de las Revisiones que
#     ya existen con su mes entero y lo deja obligatorio, y cambia el índice.
#     Lo que depende de lo que ya hay en la base va por PREPARE, para que se
#     pueda correr dos veces.

def test_lo_que_hace_la_006():
    sentencias = _sentencias(_sql(M006))
    assert "DROP TABLE IF EXISTS facturacion_revision_tarea" in sentencias
    assert ("UPDATE facturacion_revision SET desde = mes, hasta = LAST_DAY(mes) "
            "WHERE desde IS NULL OR hasta IS NULL") in sentencias
    assert ("ALTER TABLE facturacion_revision MODIFY COLUMN desde DATE NOT NULL, "
            "MODIFY COLUMN hasta DATE NOT NULL") in sentencias
    texto = " ".join(sentencias)
    assert ("ADD COLUMN desde DATE NULL AFTER mes, "
            "ADD COLUMN hasta DATE NULL AFTER desde") in texto
    assert ("ADD INDEX ix_facturacion_revision_cliente_mes_periodo "
            "(cliente_id, mes, desde, hasta)") in texto
    assert "DROP INDEX ix_facturacion_revision_cliente_mes'" in texto
    # El llenado va antes de dejarlo obligatorio, y la tabla nueva antes de
    # borrar la vieja no importa: no se copian datos entre ellas.
    llenar = next(i for i, s in enumerate(sentencias) if s.startswith("UPDATE"))
    obligar = next(i for i, s in enumerate(sentencias) if "MODIFY COLUMN desde" in s)
    assert llenar < obligar


# 16. El índice nuevo del modelo es el de la 006, y el viejo ya no está.

def test_el_indice_de_la_revision_es_el_del_periodo():
    indices = {i.name: [c.name for c in i.columns]
               for i in Base.metadata.tables["facturacion_revision"].indexes}
    assert indices == {
        "ix_facturacion_revision_cliente_mes_periodo": ["cliente_id", "mes", "desde", "hasta"],
    }


# 17. La 007 va con el deploy, ANTES de reiniciar el backend: el código de esta
#     versión lee el período del Comprobante. Su ALTER no es idempotente, y el
#     encabezado lo dice.

def test_la_007_no_es_diferible_va_antes_del_reinicio_y_avisa_que_no_es_idempotente():
    sql = _sql(M007)
    assert "-- NO DIFERIBLE" in sql
    assert "ANTES de reiniciar el backend" in sql
    assert "-- No es idempotente" in sql


# 18. En ORDEN.txt, la 007 después de la 006 y al final del archivo.

def test_la_007_va_despues_de_la_006_y_al_final():
    entradas = _entradas_de_orden()
    m006 = "facturacion/006_revision_por_grupo.sql"
    m007 = "facturacion/007_periodo_facturado.sql"
    assert entradas.index(m006) < entradas.index(m007)
    assert entradas[-1] == m007


# 19. La 007 suma las dos columnas, llena el período de los cargados a mano por
#     las quincenas de sus Líneas (las tres combinaciones) y, después, pasa la
#     fecha de esas Líneas al Desde. Nada más.

def test_lo_que_hace_la_007():
    sentencias = _sentencias(_sql(M007))
    assert len(sentencias) == 3
    sumar, periodo, lineas = sentencias
    assert sumar == ("ALTER TABLE facturacion_comprobante "
                     "ADD COLUMN periodo_desde DATE NULL AFTER fecha, "
                     "ADD COLUMN periodo_hasta DATE NULL AFTER periodo_desde")
    assert periodo.startswith("UPDATE facturacion_comprobante")
    # Sólo los cargados a mano que todavía no tienen período.
    assert periodo.endswith("WHERE c.es_historico = 0 AND c.periodo_desde IS NULL")
    # Las quincenas que tocan las Líneas, en un mismo mes (si no, no se llena).
    assert "MIN(DAY(fecha)) <= 15 AS hay_primera" in periodo
    assert "MAX(DAY(fecha)) >= 16 AS hay_segunda" in periodo
    assert "HAVING LAST_DAY(MIN(fecha)) = LAST_DAY(MAX(fecha))" in periodo
    # Sólo la 1.ª: del 1 al 15. Sólo la 2.ª: del 16 a fin de mes. Las dos: el
    # mes entero.
    assert ("c.periodo_desde = CASE WHEN l.hay_primera THEN l.mes "
            "ELSE l.mes + INTERVAL 15 DAY END") in periodo
    assert ("c.periodo_hasta = CASE WHEN l.hay_segunda THEN LAST_DAY(l.mes) "
            "ELSE l.mes + INTERVAL 14 DAY END") in periodo
    assert lineas == (
        "UPDATE facturacion_linea l "
        "JOIN facturacion_comprobante c ON c.id = l.comprobante_id "
        "SET l.fecha = c.periodo_desde "
        "WHERE c.es_historico = 0 AND c.periodo_desde IS NOT NULL "
        "AND l.fecha <> c.periodo_desde")


# 20. Las columnas nuevas son las del modelo: fecha, sin obligatoriedad (un
#     histórico no tiene período).

def test_el_modelo_tiene_el_periodo_de_la_007():
    columnas = Base.metadata.tables["facturacion_comprobante"].columns
    for nombre in ("periodo_desde", "periodo_hasta"):
        assert nombre in columnas
        assert columnas[nombre].nullable
        assert columnas[nombre].type.python_type.__name__ == "date"
