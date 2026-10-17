"""El modelo del Resumen (facturacion/004 y 006), sobre SQLite en memoria.

La configuración es una sola fila (id 1) con el Umbral y el Mes de corte. Una
Revisión de diferencia guarda, para un Cliente, un mes y su período (Desde y
Hasta), las (grupo, unidad) que superaban cuando se dejó; borrarla arrastra
sus grupos.

SQLite no hace cumplir las FK sin un PRAGMA: lo que se prueba del borrado es la
cascada de la relación, no la de la base.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.modulos.facturacion.models import Configuracion, RevisionDiferencia, RevisionGrupo


@pytest.fixture()
def fabrica():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


def revision(**campos):
    base = dict(
        cliente_id=12, mes=date(2026, 9, 1), desde=date(2026, 9, 1),
        hasta=date(2026, 9, 30), comentario="Diferencia explicada.",
        creada_en=datetime(2026, 10, 14, 12, 0),
    )
    return RevisionDiferencia(**{**base, **campos})


def test_una_revision_con_tres_grupos_se_lee_de_vuelta(fabrica):
    db = fabrica()
    r = revision(grupos=[
        RevisionGrupo(grupo="MANUALES", unidad="plantas"),
        # Una línea sin unidad también se puede revisar.
        RevisionGrupo(grupo="MANUALES", unidad=None),
        # Sin grupo va con el grupo nulo.
        RevisionGrupo(grupo=None, unidad="hectareas"),
    ])
    db.add(r)
    db.commit()
    id_ = r.id
    db.close()

    otra = fabrica()
    leida = otra.get(RevisionDiferencia, id_)
    assert (leida.cliente_id, leida.mes, leida.desde, leida.hasta, leida.comentario) == (
        12, date(2026, 9, 1), date(2026, 9, 1), date(2026, 9, 30), "Diferencia explicada.",
    )
    assert [(g.grupo, g.unidad) for g in leida.grupos] == [
        ("MANUALES", "plantas"), ("MANUALES", None), (None, "hectareas"),
    ]
    # Vigente: nadie la deshizo.
    assert leida.deshecha_en is None
    assert leida.deshecha_por is None
    otra.close()


def test_borrar_la_revision_borra_sus_grupos(fabrica):
    db = fabrica()
    r = revision(grupos=[RevisionGrupo(grupo="MANUALES", unidad="plantas"),
                         RevisionGrupo(grupo="SANIDAD", unidad="tancadas")])
    db.add(r)
    db.commit()

    db.delete(r)
    db.commit()

    assert db.query(RevisionDiferencia).count() == 0
    assert db.query(RevisionGrupo).count() == 0
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
