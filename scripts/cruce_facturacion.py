"""
Saca el Cruce de Facturación a dos CSV, para compararlo con Power BI (spec de
la E3a por grupo, decisión 9; antes, plan de la E3, decisión 7).

Es de sólo lectura y una capa fina sobre el módulo, sin SQL propio ni cuenta
propia: lee y cruza con lo mismo que el Resumen (cruce_del_periodo del
servicio), con su Umbral, su Mes de corte y sus Revisiones, así el CSV da lo
mismo que la pantalla. --desde y --hasta van en meses: el módulo recibe los
meses enteros, del 1 del primero al último día del último (como "Mes pasado"
o "Últimos 3 meses" en la pantalla). Se corre contra `testing`, que tiene los
históricos migrados.

    python scripts/cruce_facturacion.py --desde 2026-07 --hasta 2026-09
    python scripts/cruce_facturacion.py --desde 2026-07 --hasta 2026-09 --salida docs/modulos/facturacion/fuentes/cruce.csv

El principal es una fila por Cliente, mes, grupo y unidad: la línea del
Resumen, con su Campo, Facturado, Dif., Dif. % y Supera, y lo de su fila (el
período, el Estado del mes, si la diferencia está revisada y cuántas líneas
superan), en el orden del Resumen. Una cantidad que la pantalla muestra como
raya o sin valor va vacía.

El segundo, con "-tareas" al final del nombre, es una fila por Cliente, mes,
tarea y unidad, con el grupo, la Unidad sugerida, la medida "como Power BI"
(la que corresponde a la Unidad sugerida), la del módulo (la que corresponde
a la unidad de la fila), la cantidad facturada y el neto. Power BI mide cada
tarea por su Unidad sugerida y el módulo por la unidad de lo facturado: las
dos medidas lado a lado separan esa diferencia, que es a propósito, de los
errores. Las tareas de cada línea suman lo de esa línea del principal.

La cantidad y el neto son netos: las Notas de crédito restan. La cosecha, lo
No facturable y los históricos pendientes de facturar no entran, como en el
Resumen.

**La salida tiene nombres de clientes**: nunca se pega en PRs, chats ni en la
bitácora. Por eso los CSV sólo se escriben dentro de fuentes/, que está fuera
de git (ver fuentes/LEEME.md), y por consola salen sólo los conteos.
"""
import argparse
import csv
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.core.config import settings  # noqa: E402
from app.core.database import SessionExterna, SessionPropia  # noqa: E402
from app.modulos.facturacion import fechas  # noqa: E402
from app.modulos.facturacion.services.consulta_externa import (  # noqa: E402
    ConsultaExternaService,
)
from app.modulos.facturacion.services.cruce import (  # noqa: E402
    Medidas, cantidad_en_unidad, medidas_por_tarea,
)
from app.modulos.facturacion.services.resumen_service import (  # noqa: E402
    SIN_GRUPO, CruceDelPeriodo, ErrorResumen, ResumenService, fila_del_resumen,
)

FUENTES = RAIZ / "docs" / "modulos" / "facturacion" / "fuentes"

AVISO = ("La salida tiene nombres de clientes: nunca se pega en PRs, chats "
         "ni en la bitácora.")

ENCABEZADOS_GRUPOS = [
    "cliente_id", "cliente", "mes", "desde", "hasta", "estado",
    "diferencia_revisada", "lineas_superan", "grupo", "unidad", "campo",
    "facturado", "diferencia", "diferencia_pct", "supera", "fuera_del_filtro",
]
ENCABEZADOS_TAREAS = [
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


def ruta_de_tareas(salida: Path) -> Path:
    """El CSV por tarea, al lado del principal: cruce.csv da cruce-tareas.csv."""
    salida = Path(salida)
    return salida.with_name(salida.stem + "-tareas" + salida.suffix)


def _numero(valor: Decimal | None) -> str:
    """Una medida o una cantidad, con coma decimal y sin ceros de más; vacía
    si no hay (una fila sin unidad, una unidad sin medida del campo, o la raya
    de la pantalla)."""
    if valor is None:
        return ""
    texto = format(valor.normalize(), "f") if valor else "0"
    return texto.replace(".", ",")


def _pesos(valor: Decimal) -> str:
    """Con coma decimal y dos decimales, como lo abre el Excel de la oficina."""
    return f"{valor:.2f}".replace(".", ",")


def _si_no(valor: bool) -> str:
    return "sí" if valor else "no"


def filas_por_grupo(lectura: CruceDelPeriodo) -> list[list]:
    """Las filas del CSV principal: una por línea (grupo, unidad) de cada
    fila del Resumen, con lo de esa fila, en el orden del Resumen. Salen de
    fila_del_resumen, la misma que arma la pantalla: el CSV no hace cuentas.
    El Estado son las claves del Estado del mes, en orden de urgencia."""
    filas = []
    for cruce in lectura.cruces:
        fila = fila_del_resumen(cruce, lectura.nombres.get(cruce.cliente_id))
        for linea in fila["grupos"]:
            filas.append([
                fila["cliente_id"], fila["cliente_nombre"] or "",
                fila["mes"].strftime("%Y-%m"), fila["desde"].isoformat(),
                fila["hasta"].isoformat(), ", ".join(fila["estados"]),
                _si_no(fila["diferencia_revisada"]), fila["lineas_superan"],
                linea["grupo"], linea["unidad"] or "", _numero(linea["campo"]),
                _numero(linea["facturado"]), _numero(linea["diferencia"]),
                _numero(linea["diferencia_pct"]), _si_no(linea["supera"]),
                _si_no(linea["fuera_del_filtro"]),
            ])
    return filas


def filas_por_tarea(lectura: CruceDelPeriodo) -> list[list]:
    """Las filas del CSV por tarea: las tareas de cada línea (grupo, unidad)
    del Cruce, en el orden del principal, con la medida "como Power BI" al
    lado de la del módulo."""
    # Lo trabajado por (Cliente, mes) y tarea, para medir la Unidad sugerida.
    por_clave: dict[tuple, list[dict]] = defaultdict(list)
    for f in lectura.trabajado:
        por_clave[(f["cliente_id"], f["mes"])].append(f)
    sugeridas = {t["tarea_id"]: t["unidad_sugerida"] for t in lectura.tareas}

    filas = []
    for cruce in lectura.cruces:
        nombre = lectura.nombres.get(cruce.cliente_id) or ""
        medidas = medidas_por_tarea(por_clave.get((cruce.cliente_id, cruce.mes), []))
        for grupo in cruce.grupos:
            for f in grupo.tareas:
                sugerida = sugeridas.get(f.tarea_id)
                filas.append([
                    cruce.cliente_id, nombre, cruce.mes.strftime("%Y-%m"),
                    f.grupo_tarea or SIN_GRUPO, f.tarea_id, f.tarea_nombre or "",
                    f.unidad or "", sugerida or "",
                    _numero(cantidad_en_unidad(medidas.get(f.tarea_id, Medidas()),
                                               sugerida)),
                    _numero(f.campo), _numero(f.facturado), _pesos(f.importe),
                ])
    return filas


def escribir_csv(ruta: Path, encabezados: list[str], filas: list[list]) -> None:
    """CSV con `;` y coma decimal, en UTF-8 con BOM, para que Excel lo abra
    bien (como el informe del histórico)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo, delimiter=";")
        escritor.writerow(encabezados)
        escritor.writerows(filas)


# ─── Main ───────────────────────────────────────────────────────────────────

def _argumentos(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", required=True, metavar="AAAA-MM",
                    help="primer mes, incluido desde su día 1")
    ap.add_argument("--hasta", required=True, metavar="AAAA-MM",
                    help="último mes, incluido hasta su último día")
    ap.add_argument("--salida", type=Path,
                    help="el CSV por grupo, dentro de docs/modulos/facturacion/fuentes/ "
                         "(por defecto, cruce-<desde>-<hasta>.csv en esa carpeta); el "
                         "de tareas va al lado, con -tareas al final del nombre")
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
    fin = fechas.fin_de_mes(hasta)

    salida = Path(args.salida or FUENTES / f"cruce-{args.desde}-{args.hasta}.csv")
    salida_tareas = ruta_de_tareas(salida)
    if not (dentro_de_fuentes(salida) and dentro_de_fuentes(salida_tareas)):
        print("La salida tiene nombres de clientes: va dentro de %s, que está fuera "
              "de git. No se escribió nada." % FUENTES)
        return 1

    print(AVISO)
    print("Base propia: %s. Sólo lectura. Meses: %s a %s (del %s al %s).\n"
          % (settings.db_propia_name, args.desde, args.hasta, desde, fin))

    externa = None
    if consulta is None:
        externa = SessionExterna()
        consulta = ConsultaExternaService(externa)
    db = (abrir_sesion or SessionPropia)()
    try:
        # Un rango que el Resumen no acepta (más de MESES_MAXIMOS meses, o
        # después del mes en curso) se rechaza antes de leer el campo.
        lectura = ResumenService(db, consulta).cruce_del_periodo(
            desde.isoformat(), fin.isoformat())
        grupos = filas_por_grupo(lectura)
        tareas = filas_por_tarea(lectura)
    except ErrorResumen as error:
        print("%s No se escribió nada." % error.mensaje)
        return 1
    finally:
        db.rollback()
        db.close()
        if externa is not None:
            externa.close()

    escribir_csv(salida, ENCABEZADOS_GRUPOS, grupos)
    escribir_csv(salida_tareas, ENCABEZADOS_TAREAS, tareas)
    print("Filas del Resumen (Cliente y mes): %d." % len(lectura.cruces))
    print("Líneas (grupo y unidad): %d. CSV: %s" % (len(grupos), salida))
    print("Tareas (tarea y unidad): %d. CSV: %s" % (len(tareas), salida_tareas))
    print("\n" + AVISO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
