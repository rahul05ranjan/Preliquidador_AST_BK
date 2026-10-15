"""
Saca el Cruce de Facturación a un CSV, para compararlo con Power BI (plan de
la E3, decisión 7: la aceptación).

Es de sólo lectura y una capa fina sobre el módulo, sin SQL propio: lo
trabajado sale de trabajado_por_mes del campo, lo facturado del lector del
servicio del Resumen (leer_lineas) y el Cruce del motor (cruce.py), así el CSV
da lo mismo que la pantalla. Se corre contra `testing`, que tiene los
históricos migrados.

    python scripts/cruce_facturacion.py --desde 2026-06 --hasta 2026-09
    python scripts/cruce_facturacion.py --desde 2026-06 --hasta 2026-09 --salida docs/modulos/facturacion/fuentes/cruce.csv

Una fila por Cliente, mes, tarea y unidad, con el grupo, la Unidad sugerida,
la medida "como Power BI" (la que corresponde a la Unidad sugerida), la del
módulo (la que corresponde a la unidad de la fila), la cantidad facturada y
el neto. Power BI mide cada tarea por su Unidad sugerida y el módulo por la
unidad de lo facturado: las dos medidas lado a lado separan esa diferencia,
que es a propósito, de los errores. La cantidad y el neto son netos: las
Notas de crédito restan. La cosecha, lo No facturable y los históricos
pendientes de facturar no entran, como en el Resumen.

**La salida tiene nombres de clientes**: nunca se pega en PRs, chats ni en la
bitácora. Por eso el CSV sólo se escribe dentro de fuentes/, que está fuera
de git (ver fuentes/LEEME.md), y por consola salen sólo los conteos.
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.core.config import settings  # noqa: E402
from app.core.database import SessionExterna, SessionPropia  # noqa: E402
from app.modulos.facturacion import fechas  # noqa: E402
from app.modulos.facturacion.config import UMBRAL_INICIAL  # noqa: E402
from app.modulos.facturacion.services.consulta_externa import (  # noqa: E402
    ConsultaExternaService,
)
from app.modulos.facturacion.services.cruce import (  # noqa: E402
    Medidas, cantidad_en_unidad, cruzar, medidas_por_tarea,
)
from app.modulos.facturacion.services.resumen_service import (  # noqa: E402
    SIN_GRUPO, ResumenService, leer_lineas, se_muestra,
)

FUENTES = RAIZ / "docs" / "modulos" / "facturacion" / "fuentes"

AVISO = ("La salida tiene nombres de clientes: nunca se pega en PRs, chats "
         "ni en la bitácora.")

ENCABEZADOS = [
    "cliente_id", "cliente", "mes", "grupo", "tarea_id", "tarea", "unidad",
    "unidad_sugerida", "medida_como_power_bi", "medida_del_modulo",
    "cantidad_facturada", "neto",
]


# ─── La salida ──────────────────────────────────────────────────────────────

def dentro_de_fuentes(ruta: Path) -> bool:
    """Si la ruta es un archivo dentro de fuentes/ (o de una subcarpeta),
    resuelta: un `..` que sale de la carpeta no pasa."""
    carpeta = Path(FUENTES).resolve()
    destino = Path(ruta).resolve()
    return destino != carpeta and destino.is_relative_to(carpeta)


def _numero(valor: Decimal | None) -> str:
    """Una medida o una cantidad, con coma decimal y sin ceros de más; vacía
    si no hay (una fila sin unidad, o una unidad sin medida del campo)."""
    if valor is None:
        return ""
    texto = format(valor.normalize(), "f") if valor else "0"
    return texto.replace(".", ",")


def _pesos(valor: Decimal) -> str:
    """Con coma decimal y dos decimales, como lo abre el Excel de la oficina."""
    return f"{valor:.2f}".replace(".", ",")


def filas_del_cruce(trabajado: list[dict], lineas, tareas: list[dict],
                    nombres: dict, desde: date, hasta: date) -> list[list]:
    """Las filas del CSV, por mes, Cliente y el orden del motor.

    El Umbral y el Mes de corte sólo deciden si una fila supera y el Estado
    del mes, que el CSV no lleva: se pasa el corte en `desde` y el mes en
    curso después de `hasta`, así todos los meses pasan por el motor igual."""
    cruces = [c for c in cruzar(trabajado, lineas, tareas, umbral_pct=UMBRAL_INICIAL,
                                mes_corte=desde, mes_en_curso=fechas.mes_siguiente(hasta))
              if se_muestra(c)]

    # Lo trabajado por (Cliente, mes) y tarea, para medir la Unidad sugerida.
    por_clave: dict[tuple, list[dict]] = defaultdict(list)
    for f in trabajado:
        por_clave[(f["cliente_id"], f["mes"])].append(f)
    sugeridas = {t["tarea_id"]: t["unidad_sugerida"] for t in tareas}

    cruces.sort(key=lambda c: (c.mes, nombres.get(c.cliente_id) or "", c.cliente_id))
    filas = []
    for cruce in cruces:
        medidas = medidas_por_tarea(por_clave.get((cruce.cliente_id, cruce.mes), []))
        for f in cruce.filas:
            sugerida = sugeridas.get(f.tarea_id)
            filas.append([
                cruce.cliente_id, nombres.get(cruce.cliente_id) or "",
                cruce.mes.strftime("%Y-%m"), f.grupo_tarea or SIN_GRUPO,
                f.tarea_id, f.tarea_nombre or "", f.unidad or "", sugerida or "",
                _numero(cantidad_en_unidad(medidas.get(f.tarea_id, Medidas()), sugerida)),
                _numero(f.campo), _numero(f.facturado), _pesos(f.importe),
            ])
    return filas


def escribir_csv(ruta: Path, filas: list[list]) -> None:
    """CSV con `;` y coma decimal, en UTF-8 con BOM, para que Excel lo abra
    bien (como el informe del histórico)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo, delimiter=";")
        escritor.writerow(ENCABEZADOS)
        escritor.writerows(filas)


# ─── Main ───────────────────────────────────────────────────────────────────

def _argumentos(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", required=True, metavar="AAAA-MM",
                    help="primer mes, incluido")
    ap.add_argument("--hasta", required=True, metavar="AAAA-MM",
                    help="último mes, incluido")
    ap.add_argument("--salida", type=Path,
                    help="el CSV, dentro de docs/modulos/facturacion/fuentes/ (por "
                         "defecto, cruce-<desde>-<hasta>.csv en esa carpeta)")
    return ap.parse_args(argv)


def main(argv=None, *, abrir_sesion=None, consulta=None) -> int:
    """Lo que toca afuera se puede inyectar, para probarlo sin bases: la
    sesión propia y la consulta del campo. Sin consulta, abre la sesión del
    campo y la cierra al final."""
    args = _argumentos(argv)
    try:
        desde = fechas.leer_mes(args.desde)
        hasta = fechas.leer_mes(args.hasta)
    except ValueError as error:
        print(error)
        return 1
    if hasta < desde:
        print("--hasta no puede ser anterior a --desde. No se escribió nada.")
        return 1

    salida = args.salida or FUENTES / f"cruce-{args.desde}-{args.hasta}.csv"
    if not dentro_de_fuentes(salida):
        print("La salida tiene nombres de clientes: va dentro de %s, que está fuera "
              "de git. No se escribió nada." % FUENTES)
        return 1

    print(AVISO)
    print("Base propia: %s. Sólo lectura. Meses: %s a %s.\n"
          % (settings.db_propia_name, args.desde, args.hasta))

    externa = None
    if consulta is None:
        externa = SessionExterna()
        consulta = ConsultaExternaService(externa)
    db = (abrir_sesion or SessionPropia)()
    try:
        trabajado = consulta.trabajado_por_mes(desde, hasta)["filas"]
        tareas = consulta.tareas_cruce()["filas"]
        lineas = leer_lineas(db, desde, hasta)
        clientes = {f["cliente_id"] for f in trabajado} | {l.cliente_id for l in lineas}
        nombres = ResumenService(db, consulta).nombres_de_clientes(clientes)
        filas = filas_del_cruce(trabajado, lineas, tareas, nombres, desde, hasta)
    finally:
        db.rollback()
        db.close()
        if externa is not None:
            externa.close()

    escribir_csv(Path(salida), filas)
    print("Filas: %d (Cliente, mes, tarea y unidad)." % len(filas))
    print("CSV: %s" % salida)
    print("\n" + AVISO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
