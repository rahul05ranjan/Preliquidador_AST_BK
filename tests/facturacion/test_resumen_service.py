"""El servicio del Resumen y la configuración (plan de la E3, paso A6), sobre
SQLite en memoria y con una consulta del campo falsa.

Lo que se cuida acá: el Umbral y el Mes de corte salen de la base o, sin
fila, de los valores iniciales; el rango (por día, spec de la E3a por grupo,
decisión 6) se valida antes de leer el campo; lo
facturado se lee fresco de la base propia y entra en el Cruce como el motor
manda; cada fila trae sus líneas (grupo, unidad) y cuántas superan; una
Revisión cubre sólo su período exacto; un Cliente sin nada que cruzar no
aparece; y las filas salen en el orden del contrato (mes descendente,
urgencia, Cliente).

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
    RevisionGrupo,
)
from app.modulos.facturacion.services import consulta_externa, resumen_service
from app.modulos.facturacion.services.resumen_service import (
    ConfiguracionInvalida, FechaInvalida, RangoInvalido, ResumenService,
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
TAREA_VIEJA = 999   # no está en el maestro: Sin grupo

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


def linea(grupo, unidad, campo, facturado, *, supera=False):
    """Una línea (grupo, unidad) de una fila del Resumen, con la diferencia y
    su % calculados como el motor (None si no hay campo o es 0)."""
    campo = None if campo is None else D(campo)
    facturado = D(facturado)
    diferencia = None if campo is None else facturado - campo
    return {"grupo": grupo, "unidad": unidad, "campo": campo, "facturado": facturado,
            "diferencia": diferencia,
            "diferencia_pct": (None if not campo else
                               (diferencia * 100 / campo).quantize(D("0.01"))),
            "supera": supera, "fuera_del_filtro": False}


def fuera_del_filtro(grupo, unidad, campo, facturado):
    """Una línea que no se compara: sin diferencia, ni %, ni supera."""
    return {"grupo": grupo, "unidad": unidad, "campo": D(campo),
            "facturado": D(facturado), "diferencia": None, "diferencia_pct": None,
            "supera": False, "fuera_del_filtro": True}


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

    respuesta = servicio.resumen("2026-09-01", "2026-09-30")

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
    ("2025-10-31", "2026-10-01", "desde"),   # toca 13 meses
    ("2026-10-11", "2026-10-10", "hasta"),   # hasta antes de desde
    ("2026-10-01", "2026-12-01", "hasta"),   # pasa el mes en curso
    ("2026-12-01", "2026-12-31", "hasta"),
])
def test_rango_invalido(servicio, consulta, desde, hasta, campo):
    with pytest.raises(RangoInvalido) as error:
        servicio.resumen(desde, hasta)
    assert error.value.campo == campo
    assert error.value.mensaje
    # Se valida antes de leer el campo.
    assert consulta.lecturas == []


@pytest.mark.parametrize("desde, hasta, campo", [
    ("2026-10", "2026-11-30", "desde"),      # el mes solo, como antes
    ("x", "2026-11-30", "desde"),
    ("2026-10-01", "2026-09-31", "hasta"),   # un día que no existe
    ("2026-10-01", None, "hasta"),
])
def test_fecha_invalida(servicio, consulta, desde, hasta, campo):
    with pytest.raises(FechaInvalida) as error:
        servicio.resumen(desde, hasta)
    assert error.value.campo == campo
    assert error.value.mensaje == "La fecha va como AAAA-MM-DD, por ejemplo 2026-10-15."
    assert consulta.lecturas == []


def test_doce_meses_hasta_el_fin_del_mes_en_curso_se_aceptan(servicio, consulta):
    respuesta = servicio.resumen("2025-12-01", "2026-11-30")
    assert respuesta["filas"] == []
    assert consulta.lecturas[0][:3] == ("trabajado", date(2025, 12, 1), date(2026, 11, 30))


def test_el_campo_se_lee_con_los_dias_del_filtro(servicio, consulta):
    servicio.resumen("2026-09-16", "2026-10-15")
    assert consulta.lecturas[0][:3] == ("trabajado", date(2026, 9, 16), date(2026, 10, 15))


# ─── Filas ──────────────────────────────────────────────────────────────────

def test_la_respuesta_trae_la_configuracion_y_la_lectura_mas_vieja(servicio):
    respuesta = servicio.resumen("2026-10-01", "2026-10-31")
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

    filas = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)

    assert filas[UNO]["estados"] == ["pendiente_de_facturar"]
    assert filas[DOS]["estados"] == ["facturada"]
    assert filas[CUATRO]["estados"] == ["con_diferencia"]
    # Cada fila trae sus líneas (grupo, unidad), en cantidades y sin pesos.
    assert filas[DOS] == {
        "cliente_id": DOS, "cliente_nombre": "CLIENTE DOS", "mes": OCTUBRE,
        "desde": OCTUBRE, "hasta": date(2026, 10, 31), "en_curso": False,
        "grupos": [linea("MANUALES", "horas_peon", "100", "100")],
        "lineas_superan": 0,
        "estados": ["facturada"], "diferencia_revisada": False,
        "comprobantes_sin_adjunto": [],
        "comprobantes_fuera": [],
    }
    assert filas[UNO]["grupos"] == [
        linea("MANUALES", "horas_peon", "100", "0", supera=True)]
    assert filas[UNO]["lineas_superan"] == 1
    assert filas[CUATRO]["grupos"] == [
        linea("MANUALES", "horas_peon", "100", "150", supera=True)]
    assert filas[CUATRO]["grupos"][0]["diferencia_pct"] == D("50.00")


def test_una_nota_de_credito_resta_en_lo_facturado(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="80")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "20", "1000")],
                tipo="nota_credito", adjuntos=1)

    fila = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)[UNO]

    # 100 - 20 = 80 horas facturadas, lo trabajado.
    assert fila["grupos"] == [linea("MANUALES", "horas_peon", "80", "80")]
    assert fila["estados"] == ["facturada"]


def test_antes_del_corte_muestra_sus_numeros(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, SEPTIEMBRE, jornal="40")
    consulta.trabajo(UNO, RALEO, SEPTIEMBRE, unidades="300")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 9, 16), "10", "500")])

    fila = por_cliente(servicio.resumen("2026-09-01", "2026-09-30"), SEPTIEMBRE)[UNO]

    assert fila["estados"] == ["antes_del_corte"]
    # Con sus números y la diferencia, pero sin aviso: no se controla.
    assert fila["grupos"] == [linea("MANUALES", "horas_peon", "40", "10"),
                              linea("MANUALES", "plantas", "300", "0")]
    assert fila["lineas_superan"] == 0
    assert fila["diferencia_revisada"] is False


def test_el_mes_en_curso_se_controla_igual_y_avisa_que_esta_en_curso(db, servicio, consulta):
    consulta.trabajo(UNO, RALEO, NOVIEMBRE, unidades="300")
    consulta.trabajo(DOS, RALEO, NOVIEMBRE, unidades="300")
    comprobante(db, DOS, [(RALEO, "plantas", date(2026, 11, 1), "300", "900")])

    filas = por_cliente(servicio.resumen("2026-11-01", "2026-11-30"), NOVIEMBRE)

    # Hoy es el 10 de noviembre: el período no terminó y se controla igual.
    assert filas[UNO]["estados"] == ["pendiente_de_facturar"]
    assert filas[UNO]["grupos"] == [linea("MANUALES", "plantas", "300", "0", supera=True)]
    assert filas[UNO]["lineas_superan"] == 1
    assert filas[DOS]["estados"] == ["falta_comprobante"]
    assert filas[UNO]["en_curso"] is filas[DOS]["en_curso"] is True


def test_un_periodo_del_mes_en_curso_que_ya_termino_no_esta_en_curso(db, servicio, consulta):
    consulta.trabajo(UNO, RALEO, NOVIEMBRE, unidades="300")

    # Hoy es el 9 en UTC-3 (ver hoy_10_de_noviembre): hasta el 8 ya terminó, y
    # hasta el 9, hoy, todavía no.
    fila = por_cliente(servicio.resumen("2026-11-01", "2026-11-08"), NOVIEMBRE)[UNO]
    assert (fila["estados"], fila["en_curso"]) == (["pendiente_de_facturar"], False)
    fila = por_cliente(servicio.resumen("2026-11-01", "2026-11-09"), NOVIEMBRE)[UNO]
    assert fila["en_curso"] is True


def test_falta_comprobante_en_uno_a_mano_y_no_en_un_historico(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    consulta.trabajo(DOS, PODA, OCTUBRE, jornal="100")
    a_mano = comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")])
    comprobante(db, DOS, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                es_historico=True)

    filas = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)

    assert filas[UNO]["estados"] == ["falta_comprobante"]
    assert filas[UNO]["comprobantes_sin_adjunto"] == [
        {"id": a_mano.id, "tipo": "factura", "numero": a_mano.numero}]
    assert filas[DOS]["estados"] == ["facturada"]
    assert filas[DOS]["comprobantes_sin_adjunto"] == []


def test_un_pendiente_de_facturar_no_factura(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                es_historico=True, pendiente_de_facturar=True)

    fila = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)[UNO]

    assert fila["estados"] == ["pendiente_de_facturar"]
    assert fila["grupos"] == [linea("MANUALES", "horas_peon", "100", "0", supera=True)]


def test_lo_facturado_fuera_del_rango_no_cuenta(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    # Del mismo Comprobante, la Línea de septiembre queda fuera del rango.
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 9, 16), "50", "2500"),
                          (PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)

    respuesta = servicio.resumen("2026-10-01", "2026-10-31")

    assert [f["mes"] for f in respuesta["filas"]] == [OCTUBRE]
    assert respuesta["filas"][0]["grupos"] == [linea("MANUALES", "horas_peon", "100", "100")]
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

    respuesta = servicio.resumen("2026-10-01", "2026-10-31")

    assert [f["cliente_id"] for f in respuesta["filas"]] == [UNO]


def test_un_cliente_con_comprobantes_y_sin_trabajo_aparece(db, servicio):
    comprobante(db, DOS, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)

    fila = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)[DOS]

    # Facturado sin campo: supera, con el % en raya.
    assert fila["grupos"] == [linea("MANUALES", "horas_peon", "0", "100", supera=True)]
    assert fila["grupos"][0]["diferencia_pct"] is None
    assert fila["estados"] == ["con_diferencia"]


def test_el_nombre_sale_del_maestro_o_de_la_copia_del_comprobante(db, servicio, consulta):
    consulta.trabajo(TRES, PODA, OCTUBRE, jornal="10")   # de baja: está en el maestro
    comprobante(db, NUEVE, [(PODA, "horas_peon", date(2026, 10, 1), "10", "500")],
                adjuntos=1, cliente_nombre="CLIENTE NUEVE")

    filas = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)

    assert filas[TRES]["cliente_nombre"] == "CLIENTE TRES"
    assert filas[NUEVE]["cliente_nombre"] == "CLIENTE NUEVE"


# ─── Líneas por grupo ───────────────────────────────────────────────────────

def test_las_lineas_van_por_grupo_y_unidad_y_se_cuentan_las_que_superan(db, servicio,
                                                                        consulta):
    # MANUALES en horas de peón: PODA facturada de más. MANUALES en plantas:
    # RALEO sin facturar. Sin grupo: una tarea que no está en el maestro,
    # facturada sin campo. Las tres superan.
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    consulta.trabajo(UNO, RALEO, OCTUBRE, unidades="300")
    # No facturable: no da línea.
    consulta.trabajo(UNO, INTERNA, OCTUBRE, jornal="8")
    comprobante(db, UNO, [(TAREA_VIEJA, "horas_peon", date(2026, 10, 1), "5", "250"),
                          (PODA, "horas_peon", date(2026, 10, 1), "150", "7500")],
                adjuntos=1)

    fila = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)[UNO]

    # Por grupo, con Sin grupo al final, y por unidad.
    assert fila["grupos"] == [
        linea("MANUALES", "horas_peon", "100", "150", supera=True),
        linea("MANUALES", "plantas", "300", "0", supera=True),
        linea("Sin grupo", "horas_peon", "0", "5", supera=True),
    ]
    # Cuenta líneas, no grupos: MANUALES supera en dos unidades y cuenta 2.
    assert fila["lineas_superan"] == 3
    assert fila["estados"] == ["con_diferencia"]


def test_las_tareas_de_un_grupo_se_compensan(db, servicio, consulta):
    # PODA facturada de menos y ATADO (sin Unidad sugerida, facturado en horas
    # de peón) de más: por tarea las dos superarían; el grupo cierra.
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    consulta.trabajo(UNO, ATADO, OCTUBRE, jornal="50")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "50", "2500"),
                          (ATADO, "horas_peon", date(2026, 10, 1), "100", "5000")],
                adjuntos=1)

    fila = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)[UNO]

    assert fila["grupos"] == [linea("MANUALES", "horas_peon", "150", "150")]
    assert (fila["lineas_superan"], fila["estados"]) == (0, ["facturada"])


# ─── El filtro por día (decisiones 6 a 8) ───────────────────────────────────

def test_del_1_al_10_lo_que_cae_en_parte_no_cuenta_y_la_fila_avisa(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    factura = comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000")],
                          adjuntos=1)

    fila = por_cliente(servicio.resumen("2026-10-01", "2026-10-10"), OCTUBRE)[UNO]

    assert (fila["desde"], fila["hasta"]) == (OCTUBRE, date(2026, 10, 10))
    assert fila["grupos"] == [fuera_del_filtro("MANUALES", "horas_peon", "100", "0")]
    assert fila["lineas_superan"] == 0
    assert fila["estados"] == ["sin_comparar"]
    assert fila["comprobantes_fuera"] == [
        {"id": factura.id, "tipo": "factura", "numero": factura.numero,
         "desde": OCTUBRE, "hasta": date(2026, 10, 15)}]


def test_con_la_quincena_entera_la_misma_factura_se_compara(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "100", "5000"),
                          (PODA, "horas_peon", date(2026, 10, 16), "40", "2000")],
                adjuntos=1)

    fila = por_cliente(servicio.resumen("2026-10-01", "2026-10-15"), OCTUBRE)[UNO]

    # La Línea del 16 cae entera afuera: no cuenta y no avisa.
    assert fila["grupos"] == [linea("MANUALES", "horas_peon", "100", "100")]
    assert (fila["estados"], fila["comprobantes_fuera"]) == (["facturada"], [])


def test_un_filtro_de_dos_meses_se_recorta_a_cada_uno(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, SEPTIEMBRE, jornal="10")
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="10")

    respuesta = servicio.resumen("2026-09-20", "2026-10-15")

    cortes = {f["mes"]: (f["desde"], f["hasta"]) for f in respuesta["filas"]}
    assert cortes == {SEPTIEMBRE: (date(2026, 9, 20), date(2026, 9, 30)),
                      OCTUBRE: (OCTUBRE, date(2026, 10, 15))}


# ─── Revisiones ─────────────────────────────────────────────────────────────

def revision(db, cliente_id, grupos, *, creada_en, deshecha=False,
             desde=OCTUBRE, hasta=date(2026, 10, 31)):
    """Una Revisión de octubre; sin desde ni hasta, del mes entero."""
    db.add(RevisionDiferencia(
        cliente_id=cliente_id, mes=OCTUBRE, desde=desde, hasta=hasta,
        comentario="Explicada.", creada_en=creada_en,
        deshecha_en=datetime(2026, 11, 9) if deshecha else None,
        grupos=[RevisionGrupo(grupo=g, unidad=u) for g, u in grupos]))
    db.commit()


def test_la_revision_vigente_cubre_la_diferencia(db, servicio, consulta):
    for cliente in (UNO, DOS):
        consulta.trabajo(cliente, PODA, OCTUBRE, jornal="100")
        comprobante(db, cliente, [(PODA, "horas_peon", date(2026, 10, 1), "150", "7500")],
                    adjuntos=1)
    # UNO: la vigente es la vieja, que cubre; la nueva se deshizo.
    revision(db, UNO, [("MANUALES", "horas_peon")], creada_en=datetime(2026, 11, 1))
    revision(db, UNO, [], creada_en=datetime(2026, 11, 5), deshecha=True)
    # DOS: la vieja cubría, pero la vigente es la nueva, que no.
    revision(db, DOS, [("MANUALES", "horas_peon")], creada_en=datetime(2026, 11, 1))
    revision(db, DOS, [("MANUALES", "plantas")], creada_en=datetime(2026, 11, 5))

    filas = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)

    assert (filas[UNO]["estados"], filas[UNO]["diferencia_revisada"]) == (
        ["facturada"], True)
    assert (filas[DOS]["estados"], filas[DOS]["diferencia_revisada"]) == (
        ["con_diferencia"], False)


def test_una_revision_cubre_solo_su_periodo_exacto(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "150", "7500")],
                adjuntos=1)
    # La de la 1.ª quincena es la más reciente y cubre el grupo, pero no es
    # del mes entero: el Resumen, que mira el mes entero, no la toma.
    revision(db, UNO, [("MANUALES", "horas_peon")], creada_en=datetime(2026, 11, 5),
             hasta=date(2026, 10, 15))

    fila = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)[UNO]
    assert (fila["estados"], fila["diferencia_revisada"]) == (["con_diferencia"], False)

    # Una anterior del mes entero sí cubre, aunque la de la quincena sea más
    # nueva: cada período tiene su vigente.
    revision(db, UNO, [("MANUALES", "horas_peon")], creada_en=datetime(2026, 11, 1))

    fila = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)[UNO]
    assert (fila["estados"], fila["diferencia_revisada"]) == (["facturada"], True)


def test_la_revision_de_la_quincena_cubre_al_mirar_esa_quincena(db, servicio, consulta):
    consulta.trabajo(UNO, PODA, OCTUBRE, jornal="100")
    comprobante(db, UNO, [(PODA, "horas_peon", date(2026, 10, 1), "150", "7500")],
                adjuntos=1)
    revision(db, UNO, [("MANUALES", "horas_peon")], creada_en=datetime(2026, 11, 5),
             hasta=date(2026, 10, 15))

    quincena = por_cliente(servicio.resumen("2026-10-01", "2026-10-15"), OCTUBRE)[UNO]
    assert (quincena["estados"], quincena["diferencia_revisada"]) == (["facturada"], True)
    # Con un filtro de dos meses, octubre se recorta a la misma quincena.
    dos_meses = por_cliente(servicio.resumen("2026-09-16", "2026-10-15"), OCTUBRE)[UNO]
    assert dos_meses["diferencia_revisada"] is True
    # Y el mes entero no lo cubre.
    mes = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)[UNO]
    assert (mes["estados"], mes["diferencia_revisada"]) == (["con_diferencia"], False)


def test_sin_grupo_se_revisa_con_el_grupo_nulo(db, servicio, consulta):
    comprobante(db, UNO, [(TAREA_VIEJA, "horas_peon", date(2026, 10, 1), "5", "250")],
                adjuntos=1)
    revision(db, UNO, [(None, "horas_peon")], creada_en=datetime(2026, 11, 1))

    fila = por_cliente(servicio.resumen("2026-10-01", "2026-10-31"), OCTUBRE)[UNO]

    assert (fila["estados"], fila["diferencia_revisada"]) == (["facturada"], True)
    assert fila["grupos"][0]["grupo"] == "Sin grupo"


# ─── Orden y aviso ──────────────────────────────────────────────────────────

def test_orden_mes_descendente_urgencia_y_cliente(db, servicio, consulta):
    # Noviembre, en curso: dos pendientes, por nombre.
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

    respuesta = servicio.resumen("2026-09-01", "2026-11-30")

    assert [(f["mes"], f["cliente_nombre"], f["estados"][0]) for f in respuesta["filas"]] == [
        (NOVIEMBRE, "CLIENTE CUATRO", "pendiente_de_facturar"),
        (NOVIEMBRE, "CLIENTE UNO", "pendiente_de_facturar"),
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

    respuesta = servicio.resumen("2026-09-01", "2026-10-31")

    assert respuesta["tareas_sin_unidad"] == [
        {"tarea_id": ATADO, "nombre": "ATADO", "clientes": 2}]
    # Una tarea sin unidad da una línea sin unidad y sin campo, que supera
    # porque tuvo partes.
    fila = por_cliente(respuesta, OCTUBRE)[UNO]
    assert fila["grupos"] == [linea("MANUALES", None, None, "0", supera=True)]


# ─── refrescar ──────────────────────────────────────────────────────────────

def test_refrescar_invalida_la_cache_del_cruce_antes_de_leer(servicio, consulta):
    consulta_externa._CACHE[("trabajado", OCTUBRE, NOVIEMBRE)] = (float("inf"), {})
    consulta_externa._CACHE[("clientes", True)] = (float("inf"), [])

    servicio.resumen("2026-10-01", "2026-10-31")
    assert consulta.lecturas[-2][3] is True   # sin refrescar, la caché sigue

    servicio.resumen("2026-10-01", "2026-10-31", refrescar=True)
    assert consulta.lecturas[-2][3] is False  # se vació antes de leer
    assert ("trabajado", OCTUBRE, NOVIEMBRE) not in consulta_externa._CACHE
    # Clientes, fincas y empresas no son del Cruce: quedan.
    assert ("clientes", True) in consulta_externa._CACHE
