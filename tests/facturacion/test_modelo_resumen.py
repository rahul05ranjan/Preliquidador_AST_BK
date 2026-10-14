"""El modelo del Resumen (facturacion/004), sobre SQLite en memoria.

La configuración es una sola fila (id 1) con el Umbral y el Mes de corte. Una
Revisión de diferencia guarda, para un Cliente y un mes, las (tarea, unidad)
que superaban cuando se dejó; borrarla arrastra sus tareas.

SQLite no hace cumplir las FK sin un PRAGMA: lo que se prueba del borrado es la
cascada de la relación, no la de la base.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.modulos.facturacion.models import Configuracion, RevisionDiferencia, RevisionTarea


@pytest.fixture()
def fabrica():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


def revision(**campos):
    base = dict(
        cliente_id=12, mes=date(2026, 9, 1), comentario="Diferencia explicada.",
        creada_en=datetime(2026, 10, 14, 12, 0),
    )
    return RevisionDiferencia(**{**base, **campos})


def test_una_revision_con_dos_tareas_se_lee_de_vuelta(fabrica):
    db = fabrica()
    r = revision(tareas=[
        RevisionTarea(tarea_id=7, unidad="plantas"),
        # Una tarea sin unidad también se puede revisar.
        RevisionTarea(tarea_id=8, unidad=None),
    ])
    db.add(r)
    db.commit()
    id_ = r.id
    db.close()

    otra = fabrica()
    leida = otra.get(RevisionDiferencia, id_)
    assert (leida.cliente_id, leida.mes, leida.comentario) == (
        12, date(2026, 9, 1), "Diferencia explicada.",
    )
    assert sorted((t.tarea_id, t.unidad) for t in leida.tareas) == [
        (7, "plantas"), (8, None),
    ]
    # Vigente: nadie la deshizo.
    assert leida.deshecha_en is None
    assert leida.deshecha_por is None
    otra.close()


def test_borrar_la_revision_borra_sus_tareas(fabrica):
    db = fabrica()
    r = revision(tareas=[RevisionTarea(tarea_id=7, unidad="plantas"),
                         RevisionTarea(tarea_id=8, unidad="hectareas")])
    db.add(r)
    db.commit()

    db.delete(r)
    db.commit()

    assert db.query(RevisionDiferencia).count() == 0
    assert db.query(RevisionTarea).count() == 0
    db.close()


def test_la_configuracion_con_id_1_persiste(fabrica):
    db = fabrica()
    db.add(Configuracion(
        id=1, umbral_pct=Decimal("7.50"), mes_corte=date(2026, 8, 1),
    ))
    db.commit()
    db.close()

    otra = fabrica()
    leida = otra.get(Configuracion, 1)
    assert leida.umbral_pct == Decimal("7.50")
    assert leida.mes_corte == date(2026, 8, 1)
    # El alta sella cuándo; quién queda en NULL si no se pasa.
    assert leida.actualizado_en is not None
    assert leida.actualizado_por is None
    otra.close()
