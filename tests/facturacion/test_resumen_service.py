"""El servicio del Resumen y la configuración (plan de la E3, paso A6), sobre
SQLite en memoria y con una consulta del campo falsa.

Lo que se cuida acá: el Umbral y el Mes de corte salen de la base o, sin
fila, de los valores iniciales; el rango se valida antes de leer el campo; lo
facturado se lee fresco de la base propia y entra en el Cruce como el motor
manda; un Cliente sin nada que cruzar no aparece; y las filas salen en el
orden del contrato (mes descendente, urgencia, Cliente).

Hoy es el 10 de noviembre de 2026: noviembre es el mes en curso y, con el
corte inicial en octubre, octubre se controla y septiembre queda Antes del
corte. Datos inventados.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.models import Usuario
from app.modulos.facturacion import config, fechas
from app.modulos.facturacion.models import (
    Adjunto, Comprobante, Configuracion, LineaComprobante, RevisionDiferencia,
    RevisionTarea,
)
from app.modulos.facturacion.services import consulta_externa, resumen_service
from app.modulos.facturacion.services.resumen_service import (
    ConfiguracionInvalida, MesInvalido, RangoInvalido, ResumenService,
)

D = Decimal

SEPTIEMBRE = date(2026, 9, 1)
OCTUBRE = date(2026, 10, 1)
NOVIEMBRE = date(2026, 11, 1)

LEIDO_TRABAJADO = datetime(2026, 11, 10, 14, 0)
LEIDO_TAREAS = datetime(2026, 11, 10, 13, 30)

PODA = 101          # horas de peón
RALEO = 103         # plantas
ATADO = 106         # facturable, sin Unidad sugerida
INTERNA = 107       # No facturable
CARGA_BINS = 108    # sugerida de cosecha

UNO, DOS, TRES, CUATRO, CINCO, NUEVE = 1, 2, 3, 4, 5, 9


class ConsultaFalsa:
    """El campo: clientes (el 3 de baja; el 9 no está), el maestro de tareas
    y lo trabajado por mes, con la hora de lectura. Anota cada lectura del
    Cruce y si la caché del Cruce seguía llena en ese momento."""

    CLIENTES = [
        {"id": UNO, "nombre": "CLIENTE UNO", "activo": True},
        {"id": DOS, "nombre": "CLIENTE DOS", "activo": True},
        {"id": TRES, "nombre": "CLIENTE TRES", "activo": False},
        {"id": CUATRO, "nombre": "CLIENTE CUATRO", "activo": True},
        {"id": CINCO, "nombre": "CLIENTE CINCO", "activo": True},
    ]
    TAREAS = [
        {"tarea_id": PODA, "nombre": "PODA", "grupo_tarea": "MANUALES",
         "unidad_sugerida": "horas_peon", "no_facturable": False},
        {"tarea_id": RALEO, "nombre": "RALEO", "grupo_tarea": "MANUALES",
         "unidad_sugerida": "plantas", "no_facturable": False},
        {"tarea_id": ATADO, "nombre": "ATADO", "grupo_tarea": "MANUALES",
         "unidad_sugerida": None, "no_facturable": False},
        {"tarea_id": INTERNA, "nombre": "LIMPIEZA GALPON", "grupo_tarea": "INTERNAS",
         "unidad_sugerida": None, "no_facturable": True},
        {"tarea_id": CARGA_BINS, "nombre": "CARGA DE BINS", "grupo_tarea": "COSECHA",
         "unidad_sugerida": "bins", "no_facturable": False},
    ]

    def __init__(self):
        self.trabajado = []
        self.lecturas = []

    def clientes(self, incluir_baja=False):
        return [c for c in self.CLIENTES if incluir_baja or c["activo"]]

    def trabajado_por_mes(self, desde, hasta):
        self.lecturas.append(("trabajado", desde, hasta,
                              any(c[0] == "trabajado" for c in consulta_externa._CACHE)))
        return {"leido_en": LEIDO_TRABAJADO, "filas": [
            f for f in self.trabajado
            if desde.replace(day=1) <= f["mes"] <= hasta.replace(day=1)]}

    def tareas_cruce(self):
        self.lecturas.append(("tareas_cruce",))
        return {"leido_en": LEIDO_TAREAS, "filas": list(self.TAREAS)}

    def trabajo(self, cliente_id, tarea_id, mes, *, jornal="0", unidades="0",
                partes=1):
        self.trabajado.append({
            "cliente_id": cliente_id, "tarea_id": tarea_id, "mes": mes,
            "horas_jornal": D(jornal), "horas_maquina": D("0"),
            "unidades": D(unidades), "tancadas": D("0"), "partes": partes})


@pytest.fixture(autouse=True)
def hoy_10_de_noviembre(monkeypatch):
    # Las 02:00 UTC del 10 son el 9 en UTC-3: el mes es el mismo.
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
    return ConsultaFalsa()


@pytest.fixture()
def servicio(db, consulta):
    return ResumenService(db, consulta)


@pytest.fixture()
def persona(db):
    p = Usuario(nombre="PERSONA DE PRUEBA", email="persona@prueba.test",
                password="x", rol="admin")
    db.add(p)
    db.commit()
    return p


_numeros = iter(range(1, 10_000))


def comprobante(db, cliente_id, lineas, *, tipo="factura", es_historico=False,
                pendiente_de_facturar=False, adjuntos=0, cliente_nombre=None):
    """Un Comprobante con sus Líneas, cada una (tarea_id, unidad, fecha,
    cantidad, importe), y `adjuntos` Adjuntos."""
    n = next(_numeros)
    c = Comprobante(
        tipo=tipo, cliente_id=cliente_id,
        cliente_nombre=cliente_nombre or f"COPIA {cliente_id}",
        empresa_emisora=None if es_historico else "EMPRESA UNO",
        numero=f"A {n:04d}", fecha=date(2026, 11, 2), es_historico=es_historico,
        pendiente_de_facturar=pendiente_de_facturar,
        clave_identidad=f"P|{n}",
        lineas=[
            LineaComprobante(
                orden=i, fecha=fecha, tarea_id=tarea_id, tarea_nombre=f"TAREA {tarea_id}",
                unidad=unidad, cantidad=D(cantidad), precio_unitario=D("1"),
                importe=D(importe))
            for i, (tarea_id, unidad, fecha, cantidad, importe) in enumerate(lineas, 1)
        ],
    )
    db.add(c)
    db.flush()
    for i in range(adjuntos):
        db.add(Adjunto(comprobante_id=c.id, nombre_original="factura.pdf",
                       nombre_en_disco=f"{n}-{i}.pdf", tipo_contenido="application/pdf",
                       tamano_bytes=10))
    db.commit()
    return c


def por_cliente(respuesta, mes):
    return {f["cliente_id"]: f for f in respuesta["filas"] if f["mes"] == mes}


# ─── Configuración ──────────────────────────────────────────────────────────

def test_los_valores_iniciales_viven_en_config():
    assert config.UMBRAL_INICIAL == D("5")
    assert config.MES_CORTE_INICIAL == date(2026, 10, 1)
    assert config.MESES_MAXIMOS == 12
    assert config.LARGO_COMENTARIO == 500


def test_sin_fila_da_los_valores_iniciales(servicio):
    assert servicio.configuracion() == {
        "umbral_pct": config.UMBRAL_INICIAL,
        "mes_corte": config.MES_CORTE_INICIAL,
        "actualizado_en": None,
        "actualizado_por_nombre": None,
    }


def test_despues_del_cambio_da_lo_guardado(db, consulta, servicio, persona, monkeypatch):
    monkeypatch.setattr(resumen_service, "ahora_utc", lambda: datetime(2026, 11, 10, 15, 0))

    guardado = servicio.cambiar_configuracion(
        umbral_pct="7.5", mes_corte="2026-08", usuario_id=persona.id)

    esperado = {
        "umbral_pct": D("7.5"),
        "mes_corte": date(2026, 8, 1),
        "actualizado_en": datetime(2026, 11, 10, 15, 0),
        "actualizado_por_nombre": "PERSONA DE PRUEBA",
    }
    assert guardado == esperado
    # Otra lectura, con otro servicio, ve lo mismo.
    assert ResumenService(db, consulta).configuracion() == esperado

    # Un segundo cambio pisa la misma fila: sigue habiendo una sola, la 1.
    servicio.cambiar_configuracion(umbral_pct=D("100"), mes_corte="2026-11",
                                   usuario_id=persona.id)
    filas = db.query(Configuracion).all()
    assert [(f.id, f.umbral_pct, f.mes_corte) for f in filas] == [
        (1, D("100"), NOVIEMBRE)]


def test_el_resumen_usa_la_configuracion_guardada(servicio, consulta, persona):
    servicio.cambiar_configuracion(umbral_pct="10", mes_corte="2026-09",
                                   usuario_id=persona.id)
    # Con el corte en septiembre, septiembre se controla: el trabajo sin
    # facturar queda Pendiente y no Antes del corte.
    consulta.trabajo(UNO, PODA, SEPTIEMBRE, jornal="10")

    respuesta = servicio.resumen("2026-09", "2026-09")

    assert (respuesta["umbral_pct"], respuesta["mes_corte"]) == (D("10"), SEPTIEMBRE)
    assert por_cliente(respuesta, SEPTIEMBRE)[UNO]["estados"] == ["pendiente_de_facturar"]


@pytest.mark.parametrize("umbral", ["0", "-1", "100.01", "5.125", "abc"])
def test_umbral_invalido(servicio, persona, umbral):
    with pytest.raises(ConfiguracionInvalida) as error:
        servicio.cambiar_configuracion(umbral_pct=umbral, mes_corte="2026-10",
                                       usuario_id=persona.id)
    assert error.value.campo == "umbral_pct"
    assert error.value.mensaje
    assert servicio.configuracion()["actualizado_en"] is None


@pytest.mark.parametrize("umbral", ["0.01", "100", "12.50"])
def test_umbral_en_el_borde_se_acepta(servicio, persona, umbral):
    guardado = servicio.cambiar_configuracion(
        umbral_pct=umbral, mes_corte="2026-10", usuario_id=persona.id)
    assert guardado["umbral_pct"] == D(umbral)


@pytest.mark.parametrize("mes_corte", ["2026-12", "2027-01", "2026-13", "2026-9", ""])
def test_mes_de_corte_invalido(servicio, persona, mes_corte):
    with pytest.raises(ConfiguracionInvalida) as error:
        servicio.cambiar_configuracion(umbral_pct="5", mes_corte=mes_corte,
                                       usuario_id=persona.id)
    assert error.value.campo == "mes_corte"
    assert servicio.configuracion()["actualizado_en"] is None


def test_el_mes_de_corte_puede_ser_el_mes_en_curso(servicio, persona):
    guardado = servicio.cambiar_configuracion(
        umbral_pct="5", mes_corte="2026-11", usuario_id=persona.id)
    assert guardado["mes_corte"] == NOVIEMBRE


# ─── Rango ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("desde, hasta, campo", [
    ("2025-10", "2026-10", "desde"),   # 13 meses
    ("2026-10", "2026-09", "hasta"),   # hasta antes de desde
    ("2026-10", "2026-12", "hasta"),   # pasa el mes en curso
    ("2026-12", "2026-12", "hasta"),
])
def test_rango_invalido(servicio, consulta, desde, hasta, campo):
    with pytest.raises(RangoInvalido) as error:
        servicio.resumen(desde, hasta)
    assert error.value.campo == campo
    assert error.value.mensaje
    # Se valida antes de leer el campo.
    assert consulta.lecturas == []


@pytest.mark.parametrize("desde, hasta, campo", [
    ("2026-13", "2026-11", "desde"),
    ("x", "2026-11", "desde"),
    ("2026-10", "2026-9", "hasta"),
])
def test_mes_invalido(servicio, consulta, desde, hasta, campo):
    with pytest.raises(MesInvalido) as error:
        servicio.resumen(desde, hasta)
    assert error.value.campo == campo
    assert consulta.lecturas == []


def test_doce_meses_hasta_el_en_curso_se_aceptan(servicio, consulta):
    respuesta = servicio.resumen("2025-12", "2026-11")
    assert respuesta["filas"] == []
    assert consulta.lecturas[0][:3] == ("trabajado", date(2025, 12, 1), NOVIEMBRE)


# ─── Filas ──────────────────────────────────────────────────────────────────

def test_la_respuesta_trae_la_configuracion_y_la_lectura_mas_vieja(servicio):
    respuesta = servicio.resumen("2026-10", "2026-10")
    assert respuesta["umbral_pct"] == config.UMBRAL_INICIAL
    assert respuesta["mes_corte"] == config.MES_CORTE_INICIAL
    assert respuesta["mes_en_curso"] == NOVIEMBRE
    # Dos lecturas del campo con hora distinta: vale la más vieja.
    assert respuesta["leido_en"] == LEIDO_TAREAS
    assert respuesta["tareas_sin_unidad"] == []


def test_pendiente_facturada_y_con_diferencia(db, servicio, consulta):
    for cliente in (UNO, DOS, CUATRO):
        consulta.trabajo(cliente, PODA, OCTUBRE, jornal="100", partes=4)
    comprobante(db, DOS, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)
    comprobante(db, CUATRO, [(PODA, "horas_peon", date(2026, 10, 16), "150", "7500")],
                adjuntos=1)

    filas = por_cliente(servicio.resumen("2026-10", "2026-10"), OCTUBRE)

    assert filas[UNO]["estados"] == ["pendiente_de_facturar"]
    assert filas[DOS]["estados"] == ["facturada"]
    assert filas[CUATRO]["estados"] == ["con_diferencia"]
    assert filas[DOS] == {
        "cliente_id": DOS, "cliente_nombre": "CLIENTE DOS", "mes": OCTUBRE,
        "horas_peon": D("100"), "horas_tractor": D("0"), "tancadas": D("0"),
        "plantas": D("0"), "hectareas": D("0"), "facturado_neto": D("5000"),
        "estados": ["facturada"], "diferencia_revisada": False,
        "comprobantes_sin_adjunto": [],
    }
    assert filas[UNO]["facturado_neto"] == D("0")


def test_una_nota_de_credito_resta_en_el_neto(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="80")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "20", "1000")],
                tipo="nota_credito", adjuntos=1)

    fila = por_cliente(servicio.resumen("2026-10", "2026-10"), OCTUBRE)[UNO]

    assert fila["facturado_neto"] == D("4000")
    assert fila["estados"] == ["facturada"]


def test_antes_del_corte_muestra_sus_numeros(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, SEPTIEMBRE, jornal="40")
    consulta.trabajo(UNO, RALEO, SEPTIEMBRE, unidades="300")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 9, 16), "10", "500")])

    fila = por_cliente(servicio.resumen("2026-09", "2026-09"), SEPTIEMBRE)[UNO]

    assert fila["estados"] == ["antes_del_corte"]
    assert (fila["horas_peon"], fila["plantas"]) == (D("40"), D("300"))
    assert fila["facturado_neto"] == D("500")
    assert fila["diferencia_revisada"] is False


def test_mes_en_curso(db, servicio, consulta):
    consulta.trabajo(UNO, RALEO, NOVIEMBRE, unidades="300")
    consulta.trabajo(DOS, RALEO, NOVIEMBRE, unidades="300")
    comprobante(db, DOS, [(RALEO, "plantas", date(2026, 11, 1), "300", "900")])

    filas = por_cliente(servicio.resumen("2026-11", "2026-11"), NOVIEMBRE)

    assert filas[UNO]["estados"] == ["mes_en_curso"]
    assert filas[UNO]["plantas"] == D("300")
    # El mes en curso no se controla, pero un Comprobante sin Adjunto se avisa.
    assert filas[DOS]["estados"] == ["falta_comprobante", "mes_en_curso"]


def test_falta_comprobante_en_uno_a_mano_y_no_en_un_historico(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    consulta.trabajo(DOS, PODA, OCTUBRE, jornal="100")
    a_mano = comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")])
    comprobante(db, DOS, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                es_historico=True)

    filas = por_cliente(servicio.resumen("2026-10", "2026-10"), OCTUBRE)

    assert filas[UNO]["estados"] == ["falta_comprobante"]
    assert filas[UNO]["comprobantes_sin_adjunto"] == [
        {"id": a_mano.id, "tipo": "factura", "numero": a_mano.numero}]
    assert filas[DOS]["estados"] == ["facturada"]
    assert filas[DOS]["comprobantes_sin_adjunto"] == []


def test_un_pendiente_de_facturar_no_factura(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                es_historico=True, pendiente_de_facturar=True)

    fila = por_cliente(servicio.resumen("2026-10", "2026-10"), OCTUBRE)[UNO]

    assert fila["estados"] == ["pendiente_de_facturar"]
    assert fila["facturado_neto"] == D("0")


def test_lo_facturado_fuera_del_rango_no_cuenta(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    # Del mismo Comprobante, la Línea de septiembre queda fuera del rango.
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 9, 16), "50", "2500"),
                          (PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)

    respuesta = servicio.resumen("2026-10", "2026-10")

    assert [f["mes"] for f in respuesta["filas"]] == [OCTUBRE]
    assert respuesta["filas"][0]["facturado_neto"] == D("5000")
    assert respuesta["filas"][0]["estados"] == ["facturada"]


def test_un_cliente_sin_trabajo_ni_comprobantes_no_aparece(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    # TRES sólo tiene un histórico pendiente de facturar, que no cuenta.
    comprobante(db, TRES, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                es_historico=True, pendiente_de_facturar=True)
    # CUATRO sólo tiene una Línea de cosecha, que no entra en el Cruce.
    comprobante(db, CUATRO, [(CARGA_BINS, "bins", date(2026, 10, 1), "30", "900")])
    # CINCO sólo trabajó en una tarea No facturable y facturó una Línea de ella.
    consulta.trabajo(CINCO, INTERNA, OCTUBRE, jornal="8")
    comprobante(db, CINCO, [(INTERNA, "horas_peon", date(2026, 10, 1), "8", "400")])
    # DOS no tiene nada.

    respuesta = servicio.resumen("2026-10", "2026-10")

    assert [f["cliente_id"] for f in respuesta["filas"]] == [UNO]


def test_un_cliente_con_comprobantes_y_sin_trabajo_aparece(db, servicio):
    comprobante(db, DOS, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)

    fila = por_cliente(servicio.resumen("2026-10", "2026-10"), OCTUBRE)[DOS]

    assert fila["facturado_neto"] == D("5000")
    assert fila["estados"] == ["con_diferencia"]


def test_el_nombre_sale_del_maestro_o_de_la_copia_del_comprobante(db, servicio, consulta):
    consulta.trabajo(TRES, PODA, OCTUBRE, jornal="10")   # de baja: está en el maestro
    comprobante(db, NUEVE, [(PODA, "horas_peon", date(2026, 10, 1), "10", "500")],
                adjuntos=1, cliente_nombre="CLIENTE NUEVE")

    filas = por_cliente(servicio.resumen("2026-10", "2026-10"), OCTUBRE)

    assert filas[TRES]["cliente_nombre"] == "CLIENTE TRES"
    assert filas[NUEVE]["cliente_nombre"] == "CLIENTE NUEVE"


# ─── Revisiones ─────────────────────────────────────────────────────────────

def revision(db, cliente_id, tareas, *, creada_en, deshecha=False):
    db.add(RevisionDiferencia(
        cliente_id=cliente_id, mes=OCTUBRE, comentario="Explicada.",
        creada_en=creada_en,
        deshecha_en=datetime(2026, 11, 9) if deshecha else None,
        tareas=[RevisionTarea(tarea_id=t, unidad=u) for t, u in tareas]))
    db.commit()


def test_la_revision_vigente_cubre_la_diferencia(db, servicio, consulta):
    for cliente in (UNO, DOS):
        consulta.trabajo(cliente, PODA, OCTUBRE, jornal="100")
        comprobante(db, cliente, [(PODA, "horas_peon", date(2026, 10, 1), "150", "7500")],
                    adjuntos=1)
    # UNO: la vigente es la vieja, que cubre; la nueva se deshizo.
    revision(db, UNO, [(PODA, "horas_peon")], creada_en=datetime(2026, 11, 1))
    revision(db, UNO, [], creada_en=datetime(2026, 11, 5), deshecha=True)
    # DOS: la vieja cubría, pero la vigente es la nueva, que no.
    revision(db, DOS, [(PODA, "horas_peon")], creada_en=datetime(2026, 11, 1))
    revision(db, DOS, [(RALEO, "plantas")], creada_en=datetime(2026, 11, 5))

    filas = por_cliente(servicio.resumen("2026-10", "2026-10"), OCTUBRE)

    assert (filas[UNO]["estados"], filas[UNO]["diferencia_revisada"]) == (
        ["facturada"], True)
    assert (filas[DOS]["estados"], filas[DOS]["diferencia_revisada"]) == (
        ["con_diferencia"], False)


# ─── Orden y aviso ──────────────────────────────────────────────────────────

def test_orden_mes_descendente_urgencia_y_cliente(db, servicio, consulta):
    # Noviembre: dos en curso, por nombre.
    consulta.trabajo(UNO, PODA, NOVIEMBRE, jornal="10")
    consulta.trabajo(CUATRO, PODA, NOVIEMBRE, jornal="10")
    # Octubre: UNO facturada, DOS pendiente, CUATRO con diferencia, CINCO
    # pendiente.
    for cliente in (UNO, DOS, CUATRO, CINCO):
        consulta.trabajo(cliente, PODA, OCTUBRE, jornal="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)
    comprobante(db, CUATRO, [(PODA, "horas_peon", date(2026, 10, 1), "200", "9000")],
                adjuntos=1)
    # Septiembre: antes del corte.
    consulta.trabajo(DOS, PODA, SEPTIEMBRE, jornal="10")

    respuesta = servicio.resumen("2026-09", "2026-11")

    assert [(f["mes"], f["cliente_nombre"], f["estados"][0]) for f in respuesta["filas"]] == [
        (NOVIEMBRE, "CLIENTE CUATRO", "mes_en_curso"),
        (NOVIEMBRE, "CLIENTE UNO", "mes_en_curso"),
        (OCTUBRE, "CLIENTE CINCO", "pendiente_de_facturar"),
        (OCTUBRE, "CLIENTE DOS", "pendiente_de_facturar"),
        (OCTUBRE, "CLIENTE CUATRO", "con_diferencia"),
        (OCTUBRE, "CLIENTE UNO", "facturada"),
        (SEPTIEMBRE, "CLIENTE DOS", "antes_del_corte"),
    ]


def test_tareas_sin_unidad_con_su_cantidad_de_clientes(servicio, consulta):
    consulta.trabajo(UNO, ATADO, OCTUBRE, jornal="5")
    consulta.trabajo(UNO, ATADO, SEPTIEMBRE, jornal="5")
    consulta.trabajo(DOS, ATADO, OCTUBRE, jornal="5")
    consulta.trabajo(DOS, PODA, OCTUBRE, jornal="5")

    respuesta = servicio.resumen("2026-09", "2026-10")

    assert respuesta["tareas_sin_unidad"] == [
        {"tarea_id": ATADO, "nombre": "ATADO", "clientes": 2}]
    # Una tarea sin unidad no suma en ninguna columna.
    fila = por_cliente(respuesta, OCTUBRE)[UNO]
    assert all(fila[u] == D("0") for u in
               ("horas_peon", "horas_tractor", "tancadas", "plantas", "hectareas"))


# ─── refrescar ──────────────────────────────────────────────────────────────

def test_refrescar_invalida_la_cache_del_cruce_antes_de_leer(servicio, consulta):
    consulta_externa._CACHE[("trabajado", OCTUBRE, NOVIEMBRE)] = (float("inf"), {})
    consulta_externa._CACHE[("clientes", True)] = (float("inf"), [])

    servicio.resumen("2026-10", "2026-10")
    assert consulta.lecturas[-2][3] is True   # sin refrescar, la caché sigue

    servicio.resumen("2026-10", "2026-10", refrescar=True)
    assert consulta.lecturas[-2][3] is False  # se vació antes de leer
    assert ("trabajado", OCTUBRE, NOVIEMBRE) not in consulta_externa._CACHE
    # Clientes, fincas y empresas no son del Cruce: quedan.
    assert ("clientes", True) in consulta_externa._CACHE
