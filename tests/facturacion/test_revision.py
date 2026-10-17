"""La Revisión de diferencia (plan de la E3, paso A9, y el contrato de las rutas
15 y 16), sobre SQLite en memoria y con la consulta del campo falsa del
Detalle.

Lo que se cuida acá: el comentario es obligatorio y de hasta 500 caracteres,
medidos después de recortar los espacios de los bordes; sólo se revisa un mes
Con diferencia (cualquier otro estado da 409 `no_revisable`, con un mensaje
según el estado); la Revisión guarda quién, cuándo, su período (el filtro
recortado al mes; sin Desde ni Hasta, el mes entero) y las (grupo, unidad)
que superaban,
calculadas con los mismos datos que vio el Detalle; con ella el mes queda
Facturada y revisada, hasta que supere un grupo nuevo; y deshacerla deja el
registro sellado y el mes otra vez Con diferencia.

Hoy es el 10 de noviembre de 2026: noviembre es el mes en curso y, con el
corte inicial en octubre, octubre se controla y septiembre queda Antes del
corte. Datos inventados.
"""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.models import Usuario
from app.modulos.facturacion import fechas
from app.modulos.facturacion.models import RevisionDiferencia
from app.modulos.facturacion.services import consulta_externa, resumen_service
from app.modulos.facturacion.services.resumen_service import (
    ClienteNoEncontrado, FechaInvalida, MesInvalido, NoRevisable, RangoInvalido,
    ResumenService, RevisionInvalida, SinRevision,
)
from tests.facturacion import test_detalle as detalle_a8

OCTUBRE = detalle_a8.OCTUBRE

PODA = detalle_a8.PODA              # horas de peón
RALEO = detalle_a8.RALEO            # plantas
ATADO = detalle_a8.ATADO            # sin Unidad sugerida
UNO, DOS, CUATRO, CINCO = (detalle_a8.UNO, detalle_a8.DOS, detalle_a8.CUATRO,
                           detalle_a8.CINCO)
SIN_NADA = detalle_a8.SIN_NADA      # ni en el maestro ni con Comprobantes

DEJADA = datetime(2026, 11, 10, 15, 0)
DESHECHA = datetime(2026, 11, 10, 16, 45)

comprobante = detalle_a8.comprobante


@pytest.fixture(autouse=True)
def hoy_10_de_noviembre(monkeypatch):
    monkeypatch.setattr(fechas, "_ahora",
                        lambda: datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc))


@pytest.fixture(autouse=True)
def cache_limpia():
    consulta_externa.invalidar_cache()
    yield
    consulta_externa.invalidar_cache()


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)()
    yield sesion
    sesion.close()
    engine.dispose()


@pytest.fixture()
def consulta():
    return detalle_a8.ConsultaFalsa()


@pytest.fixture()
def servicio(db, consulta):
    return ResumenService(db, consulta)


def _persona(db, nombre, email):
    p = Usuario(nombre=nombre, email=email, password="x", rol="usuario")
    db.add(p)
    db.commit()
    return p


@pytest.fixture()
def persona(db):
    return _persona(db, "PERSONA DE PRUEBA", "persona@prueba.test")


@pytest.fixture()
def otra_persona(db):
    return _persona(db, "OTRA PERSONA", "otra@prueba.test")


@pytest.fixture()
def reloj(monkeypatch):
    """Reemplaza ahora_utc del servicio: devuelve la hora que se le fije."""
    hora = {"ahora": DEJADA}
    monkeypatch.setattr(resumen_service, "ahora_utc", lambda: hora["ahora"])
    return hora


def con_diferencia(db, consulta, cliente_id=UNO):
    """Octubre Con diferencia: PODA trabajó 100 horas y se facturaron 150
    (supera); RALEO, 300 plantas facturadas justas (no supera). Con PDF, así
    no falta comprobante."""
    consulta.parte(cliente_id, PODA, date(2026, 10, 3), jornal="100")
    consulta.parte(cliente_id, RALEO, date(2026, 10, 5), unidades="300")
    comprobante(db, cliente_id, [(PODA, "horas_peon", date(2026, 10, 1), "150", "7500"),
                                 (RALEO, "plantas", date(2026, 10, 1), "300", "900")],
                adjuntos=1)


def revisiones(db):
    return list(db.scalars(select(RevisionDiferencia).order_by(RevisionDiferencia.id)))


def grupos_de(revision):
    return {(g.grupo, g.unidad) for g in revision.grupos}


# ─── Comentario ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("comentario", ["", "   ", "\n\t ", None])
def test_el_comentario_es_obligatorio(db, servicio, consulta, persona, reloj, comentario):
    con_diferencia(db, consulta)

    with pytest.raises(RevisionInvalida) as error:
        servicio.revisar(UNO, "2026-10", comentario, persona.id)

    assert error.value.campo == "comentario"
    assert error.value.mensaje
    assert revisiones(db) == []


def test_el_comentario_de_mas_de_500_da_error(db, servicio, consulta, persona, reloj):
    con_diferencia(db, consulta)

    with pytest.raises(RevisionInvalida) as error:
        servicio.revisar(UNO, "2026-10", "x" * 501, persona.id)

    assert error.value.campo == "comentario"
    assert "500" in error.value.mensaje
    assert revisiones(db) == []


def test_el_largo_se_mide_despues_de_recortar_los_bordes(db, servicio, consulta, persona,
                                                         reloj):
    con_diferencia(db, consulta)

    servicio.revisar(UNO, "2026-10", "  " + "x" * 500 + " \n", persona.id)

    [guardada] = revisiones(db)
    # Se guarda recortado: 500 justos, lo que entra en la columna.
    assert guardada.comentario == "x" * 500


# ─── Estados que no se revisan ──────────────────────────────────────────────

def _pendiente(db, consulta, cliente_id=UNO):
    consulta.parte(cliente_id, PODA, date(2026, 10, 3), jornal="100")


def _antes_del_corte(db, consulta, cliente_id=UNO):
    consulta.parte(cliente_id, PODA, date(2026, 9, 3), jornal="100")
    comprobante(db, cliente_id, [(PODA, "horas_peon", date(2026, 9, 1), "150", "7500")],
                adjuntos=1)


def _facturada(db, consulta, cliente_id=UNO):
    consulta.parte(cliente_id, PODA, date(2026, 10, 3), jornal="100")
    comprobante(db, cliente_id, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)


@pytest.mark.parametrize("preparar, mes, estado", [
    (_pendiente, "2026-10", "pendiente_de_facturar"),
    (_antes_del_corte, "2026-09", "antes_del_corte"),
    (_facturada, "2026-10", "facturada"),
])
def test_solo_se_revisa_un_mes_con_diferencia(db, servicio, consulta, persona, reloj,
                                              preparar, mes, estado):
    preparar(db, consulta)
    assert estado in servicio.detalle(UNO, mes)["estados"]

    with pytest.raises(NoRevisable) as error:
        servicio.revisar(UNO, mes, "Explicada.", persona.id)

    assert error.value.mensaje
    assert revisiones(db) == []


def test_el_mensaje_de_no_revisable_depende_del_estado(db, servicio, consulta, persona,
                                                       reloj):
    mensajes = {}
    casos = [(_pendiente, UNO, "2026-10"), (_antes_del_corte, DOS, "2026-09"),
             (_facturada, CINCO, "2026-10")]
    for preparar, cliente_id, mes in casos:
        preparar(db, consulta, cliente_id)
        with pytest.raises(NoRevisable) as error:
            servicio.revisar(cliente_id, mes, "Explicada.", persona.id)
        mensajes[preparar.__name__] = error.value.mensaje

    # Tres estados, tres mensajes distintos.
    assert len(set(mensajes.values())) == 3, mensajes


def test_un_periodo_en_curso_con_diferencia_se_revisa(db, servicio, consulta, persona,
                                                      reloj):
    """Hoy es el 10 de noviembre: la 1.ª quincena de noviembre no terminó y
    se controla igual, así que también se revisa (plan del 2026-10-17)."""
    consulta.parte(UNO, PODA, date(2026, 11, 3), jornal="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 11, 1), "150", "7500")],
                adjuntos=1)
    periodo = {"desde": "2026-11-01", "hasta": "2026-11-15"}
    antes = servicio.detalle(UNO, "2026-11", **periodo)
    assert (antes["estados"], antes["en_curso"]) == (["con_diferencia"], True)

    despues = servicio.revisar(UNO, "2026-11", "Explicada.", persona.id, **periodo)

    assert (despues["estados"], despues["diferencia_revisada"]) == (["facturada"], True)
    [guardada] = revisiones(db)
    assert (guardada.desde, guardada.hasta) == (date(2026, 11, 1), date(2026, 11, 15))


def test_sin_nada_que_supere_el_409_habla_de_grupos(db, servicio, consulta, persona,
                                                   reloj):
    """La diferencia se mide por grupo de tareas y unidad (decisión 1 de la
    spec de la E3a por grupo): el mensaje no nombra tareas."""
    _facturada(db, consulta)

    with pytest.raises(NoRevisable) as error:
        servicio.revisar(UNO, "2026-10", "Explicada.", persona.id)

    assert "grupo" in error.value.mensaje
    assert "tarea" not in error.value.mensaje.lower()


def test_un_mes_ya_revisado_no_se_vuelve_a_revisar(db, servicio, consulta, persona, reloj):
    con_diferencia(db, consulta)
    servicio.revisar(UNO, "2026-10", "Explicada.", persona.id)

    with pytest.raises(NoRevisable) as error:
        servicio.revisar(UNO, "2026-10", "Otra vez.", persona.id)

    assert error.value.mensaje
    assert len(revisiones(db)) == 1


# ─── Qué guarda ─────────────────────────────────────────────────────────────

def test_guarda_quien_cuando_el_mes_entero_y_los_grupos_que_superaban(
        db, servicio, consulta, persona, reloj):
    con_diferencia(db, consulta)
    # ATADO no tiene unidad: trabajada y sin facturar, su línea de MANUALES
    # sin unidad supera.
    consulta.parte(UNO, ATADO, date(2026, 10, 4), jornal="6")
    # Otro Cliente con diferencia en el mismo mes: no entra.
    con_diferencia(db, consulta, cliente_id=DOS)

    servicio.revisar(UNO, "2026-10", "  Acordado con el Cliente.  ", persona.id)

    [guardada] = revisiones(db)
    assert guardada.cliente_id == UNO
    assert guardada.mes == OCTUBRE
    # El período: el mes entero, del 1 al último día.
    assert (guardada.desde, guardada.hasta) == (OCTUBRE, date(2026, 10, 31))
    assert guardada.comentario == "Acordado con el Cliente."
    assert guardada.creada_en == DEJADA
    assert guardada.creada_por == persona.id
    assert (guardada.deshecha_en, guardada.deshecha_por) == (None, None)
    # Las líneas que superaban; la de plantas (RALEO), que no, no.
    assert grupos_de(guardada) == {("MANUALES", "horas_peon"), ("MANUALES", None)}
    # En el orden de las líneas: por unidad, la que no tiene al final.
    assert [(g.grupo, g.unidad) for g in guardada.grupos] == [
        ("MANUALES", "horas_peon"), ("MANUALES", None)]


def test_lee_los_partes_del_mes_sin_vaciar_la_cache(db, servicio, consulta, persona, reloj,
                                                    monkeypatch):
    con_diferencia(db, consulta)

    def no_vaciar():
        raise AssertionError("La Revisión no vuelve a leer el campo.")
    monkeypatch.setattr(resumen_service, "invalidar_cache_cruce", no_vaciar)

    servicio.revisar(UNO, "2026-10", "Explicada.", persona.id)

    assert ("partes", UNO, OCTUBRE, date(2026, 10, 31)) in consulta.lecturas


# ─── El efecto de una Revisión ──────────────────────────────────────────────

def test_devuelve_el_detalle_facturada_y_revisada(db, servicio, consulta, persona, reloj):
    con_diferencia(db, consulta)

    detalle = servicio.revisar(UNO, "2026-10", "Explicada.", persona.id)

    [guardada] = revisiones(db)
    assert detalle["cliente_id"] == UNO
    assert detalle["mes"] == OCTUBRE
    assert (detalle["estados"], detalle["diferencia_revisada"]) == (["facturada"], True)
    assert detalle["se_puede_revisar"] is False
    assert detalle["revision"]["id"] == guardada.id
    assert detalle["revision"]["creada_por_nombre"] == "PERSONA DE PRUEBA"
    assert detalle["revision"]["grupos"] == [{"grupo": "MANUALES", "unidad": "horas_peon"}]
    # El período que muestra el aviso: el mes entero, del 1 al último día.
    assert (detalle["revision"]["desde"], detalle["revision"]["hasta"]) == (
        OCTUBRE, date(2026, 10, 31))
    # Y el Resumen dice lo mismo.
    [fila] = servicio.resumen("2026-10-01", "2026-10-31")["filas"]
    assert (fila["estados"], fila["diferencia_revisada"]) == (["facturada"], True)


def test_un_grupo_nuevo_que_supera_pide_otra_revision(db, servicio, consulta, persona,
                                                      otra_persona, reloj):
    con_diferencia(db, consulta)
    primera = servicio.revisar(UNO, "2026-10", "Explicada.", persona.id)["revision"]

    # Llega otro parte de RALEO: 400 plantas trabajadas y 300 facturadas.
    consulta.parte(UNO, RALEO, date(2026, 10, 20), unidades="100")
    detalle = servicio.detalle(UNO, "2026-10")
    assert (detalle["estados"], detalle["diferencia_revisada"]) == (["con_diferencia"], False)
    assert detalle["se_puede_revisar"] is True

    reloj["ahora"] = DESHECHA
    detalle = servicio.revisar(UNO, "2026-10", "También RALEO.", otra_persona.id)

    vieja, nueva = revisiones(db)
    assert vieja.id == primera["id"]
    assert grupos_de(nueva) == {("MANUALES", "horas_peon"), ("MANUALES", "plantas")}
    assert (nueva.creada_por, nueva.creada_en) == (otra_persona.id, DESHECHA)
    # La nueva es la vigente, y cubre las dos.
    assert detalle["revision"]["id"] == nueva.id
    assert detalle["revision"]["comentario"] == "También RALEO."
    assert (detalle["estados"], detalle["diferencia_revisada"]) == (["facturada"], True)


def test_si_no_supera_ninguna_queda_facturada_sin_nota(db, servicio, consulta, persona,
                                                       reloj):
    con_diferencia(db, consulta)
    servicio.revisar(UNO, "2026-10", "Explicada.", persona.id)

    # Una Nota de crédito corrige PODA: 150 - 50 = 100, lo trabajado.
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "50", "2500")],
                tipo="nota_credito", adjuntos=1)
    detalle = servicio.detalle(UNO, "2026-10")

    assert (detalle["estados"], detalle["diferencia_revisada"]) == (["facturada"], False)
    assert detalle["se_puede_revisar"] is False
    # La Revisión queda en el registro.
    [guardada] = revisiones(db)
    assert guardada.deshecha_en is None


# ─── Deshacer ───────────────────────────────────────────────────────────────

def test_deshacer_sella_el_registro_y_el_mes_vuelve_a_con_diferencia(
        db, servicio, consulta, persona, otra_persona, reloj):
    con_diferencia(db, consulta)
    servicio.revisar(UNO, "2026-10", "Explicada.", persona.id)

    reloj["ahora"] = DESHECHA
    detalle = servicio.deshacer_revision(UNO, "2026-10", otra_persona.id)

    # No se borra: queda con quién y cuándo la deshizo, y con sus grupos.
    [guardada] = revisiones(db)
    assert (guardada.deshecha_en, guardada.deshecha_por) == (DESHECHA, otra_persona.id)
    assert (guardada.creada_en, guardada.creada_por) == (DEJADA, persona.id)
    assert guardada.comentario == "Explicada."
    assert grupos_de(guardada) == {("MANUALES", "horas_peon")}
    # Devuelve el Detalle, otra vez Con diferencia y sin Revisión vigente.
    assert (detalle["estados"], detalle["diferencia_revisada"]) == (["con_diferencia"], False)
    assert detalle["se_puede_revisar"] is True
    assert detalle["revision"] is None


def test_deshacer_sin_revision_vigente_da_409(db, servicio, consulta, persona, reloj):
    con_diferencia(db, consulta)

    with pytest.raises(SinRevision) as error:
        servicio.deshacer_revision(UNO, "2026-10", persona.id)

    assert error.value.mensaje


def test_deshacer_dos_veces_da_409(db, servicio, consulta, persona, reloj):
    con_diferencia(db, consulta)
    servicio.revisar(UNO, "2026-10", "Explicada.", persona.id)
    servicio.deshacer_revision(UNO, "2026-10", persona.id)

    reloj["ahora"] = DESHECHA
    with pytest.raises(SinRevision):
        servicio.deshacer_revision(UNO, "2026-10", persona.id)

    # El sello de la primera vez no cambia.
    [guardada] = revisiones(db)
    assert guardada.deshecha_en == DEJADA


def test_deshacer_no_toca_una_revision_de_otro_periodo(db, servicio, consulta, persona,
                                                       reloj):
    con_diferencia(db, consulta)
    # Una Revisión de la 1.ª quincena: sin Desde ni Hasta se deshace sólo la
    # del mes entero.
    db.add(RevisionDiferencia(cliente_id=UNO, mes=OCTUBRE, desde=OCTUBRE,
                              hasta=date(2026, 10, 15), comentario="Quincena.",
                              creada_en=DEJADA))
    db.commit()

    with pytest.raises(SinRevision):
        servicio.deshacer_revision(UNO, "2026-10", persona.id)

    [guardada] = revisiones(db)
    assert guardada.deshecha_en is None


def test_con_la_quincena_se_guarda_y_se_deshace_la_de_ese_periodo(
        db, servicio, consulta, persona, otra_persona, reloj):
    con_diferencia(db, consulta)
    quincena = {"desde": "2026-10-01", "hasta": "2026-10-15"}

    detalle = servicio.revisar(UNO, "2026-10", "Explicada.", persona.id, **quincena)

    [guardada] = revisiones(db)
    assert (guardada.desde, guardada.hasta) == (OCTUBRE, date(2026, 10, 15))
    assert (detalle["desde"], detalle["hasta"]) == (OCTUBRE, date(2026, 10, 15))
    assert (detalle["estados"], detalle["diferencia_revisada"]) == (["facturada"], True)
    # La de la 1.ª quincena no cubre el mes entero.
    [mes] = servicio.resumen("2026-10-01", "2026-10-31")["filas"]
    assert (mes["estados"], mes["diferencia_revisada"]) == (["con_diferencia"], False)
    [primera] = servicio.resumen("2026-10-01", "2026-10-15")["filas"]
    assert (primera["estados"], primera["diferencia_revisada"]) == (["facturada"], True)
    # Sin Desde ni Hasta no se deshace: es de otro período.
    with pytest.raises(SinRevision):
        servicio.deshacer_revision(UNO, "2026-10", otra_persona.id)

    reloj["ahora"] = DESHECHA
    detalle = servicio.deshacer_revision(UNO, "2026-10", otra_persona.id, **quincena)

    db.refresh(guardada)
    assert (guardada.deshecha_en, guardada.deshecha_por) == (DESHECHA, otra_persona.id)
    assert detalle["estados"] == ["con_diferencia"]


def test_sin_comparar_no_se_revisa(db, servicio, consulta, persona, reloj):
    # Del 1 al 10, las dos Líneas (del 1 al 15) caen en parte: nada se compara.
    con_diferencia(db, consulta)

    with pytest.raises(NoRevisable) as error:
        servicio.revisar(UNO, "2026-10", "Explicada.", persona.id,
                         desde="2026-10-01", hasta="2026-10-10")

    assert "período" in error.value.mensaje
    assert revisiones(db) == []


@pytest.mark.parametrize("desde, hasta, error", [
    ("2026-10-11", "2026-10-10", RangoInvalido),
    ("2026-11-01", None, RangoInvalido),
    ("2026-10", None, FechaInvalida),
])
def test_un_periodo_que_no_sirve_no_lee_ni_guarda(servicio, consulta, persona, reloj,
                                                  desde, hasta, error):
    with pytest.raises(error):
        servicio.revisar(UNO, "2026-10", "Explicada.", persona.id, desde=desde, hasta=hasta)
    with pytest.raises(error):
        servicio.deshacer_revision(UNO, "2026-10", persona.id, desde=desde, hasta=hasta)
    assert consulta.lecturas == []


def test_deshacer_otro_mes_no_toca_la_revision(db, servicio, consulta, persona, reloj):
    con_diferencia(db, consulta)
    servicio.revisar(UNO, "2026-10", "Explicada.", persona.id)

    with pytest.raises(SinRevision):
        servicio.deshacer_revision(UNO, "2026-09", persona.id)
    with pytest.raises(SinRevision):
        servicio.deshacer_revision(DOS, "2026-10", persona.id)

    [guardada] = revisiones(db)
    assert guardada.deshecha_en is None


# ─── 404 y mes inválido ─────────────────────────────────────────────────────

def test_un_cliente_que_no_existe_da_404(db, servicio, consulta, persona, reloj):
    consulta.parte(SIN_NADA, PODA, date(2026, 10, 3), jornal="100")

    with pytest.raises(ClienteNoEncontrado):
        servicio.revisar(SIN_NADA, "2026-10", "Explicada.", persona.id)
    with pytest.raises(ClienteNoEncontrado):
        servicio.deshacer_revision(SIN_NADA, "2026-10", persona.id)

    assert revisiones(db) == []


@pytest.mark.parametrize("mes", ["2026-13", "2026-9", "x"])
def test_mes_invalido(servicio, consulta, persona, reloj, mes):
    with pytest.raises(MesInvalido) as error:
        servicio.revisar(UNO, mes, "Explicada.", persona.id)
    assert error.value.campo == "mes"
    with pytest.raises(MesInvalido):
        servicio.deshacer_revision(UNO, mes, persona.id)
    assert consulta.lecturas == []
