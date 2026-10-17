# Spec — Facturación E3a: el cruce por grupo de tareas y el filtro por día

Rama `feature/facturacion-e3` en los dos repos. Spec aprobada por el usuario el 2026-10-17, escrita por la
sesión que entrevistó, sin planificador: cada ticket lo planifica su ejecutor. Reemplaza lo que el plan
`2026-10-14-facturacion-e3.md` dice del cruce por tarea, el filtro por meses, la Revisión por tarea y el
script del cruce; el resto de ese plan sigue en pie.

## 1. Problema

El Resumen y el Detalle de la E3a comparan lo trabajado contra lo facturado **por tarea** y **por mes
entero**. Pero las contadoras facturan por grupo de tareas: comparar por tarea da "Con diferencia" en
meses que están bien facturados. Además, sólo se puede mirar de a meses, y la mayoría de la
facturación es quincenal (del 1 al 15 y del 16 a fin de mes): no se puede controlar una quincena.

## 2. Solución

La diferencia se mide por **grupo de tareas y unidad**, con el Umbral de siempre. El Resumen y el
Detalle se filtran **por día** (Desde y Hasta, con atajos). Una Línea facturada cuenta sólo si su período
entero cae adentro del filtro; si cae en parte, no cuenta y la fila lo avisa, con un botón para mirar
ese período. La Revisión guarda los grupos que superaban y el período en que se revisó. El
Detalle pierde el panel lateral: las tareas se abren dentro del grupo, y los partes y la Revisión, en
modales.

## 3. Historias de usuario

1. Como contadora, quiero ver en el Resumen una línea por unidad de cada Cliente, con Campo,
   Facturado, Dif. y Dif. %, para saber de un vistazo qué grupos no cierran.
2. Como contadora, quiero filtrar por días (Quincena pasada, Mes pasado, Otro período…), para
   controlar lo que facturé en una quincena.
3. Como contadora, quiero que una factura que no entra entera en el filtro no se compare a medias y me
   lo avise, para no perseguir diferencias que no existen.
4. Como contadora, quiero abrir un grupo en el Detalle y ver sus tareas con la cantidad del campo, y
   abrir los partes de una tarea, para encontrar de dónde sale una diferencia.
5. Como contadora, quiero dejar revisada una diferencia de una quincena o de un mes, con un comentario,
   para que ese período no me siga avisando lo que ya expliqué.
6. Como dueño, quiero comparar el cruce nuevo contra Power BI con el script, para confiar en los
   números antes de dárselo a las contadoras.

## 4. Decisiones cerradas

1. **Diferencia y "Con diferencia" van por (grupo de tareas, unidad)**, con el Umbral del 5 % por
   grupo. Las tareas no avisan. Un grupo con dos unidades da dos filas. Facturado sin campo muestra
   Dif. % como raya "—". "Sin Unidad sugerida" se muestra junto a la tarea. Porqué: las contadoras
   facturan por grupo; por tarea daba diferencias falsas. Revierte lo del BK #100 ("Con diferencia se
   mide por tarea"): el porqué de volver al grupo va en el cuerpo del PR del backend, que es lo que
   archiva la bitácora.
2. **Resumen**: un encabezado por mes y Cliente con el Estado y la acción ("Con diferencia · N líneas
   superan", donde N cuenta las líneas (grupo, unidad): un grupo con dos unidades que superan cuenta
   2), y debajo una línea por unidad (Campo, Facturado, Dif., Dif. %). Sólo cantidades, sin TOTAL.
   Orden fijo, sin ordenar por columna: el mes más nuevo primero, después el Estado más urgente y
   después el Cliente; dentro de cada bloque, por grupo ("Sin grupo" al final) y por unidad. Los meses
   que van en gris (Antes del corte y Mes en curso) muestran sus líneas en gris, con Dif., sin aviso.
   Los cuadros de Alertas, Mes en curso y Antes del corte no cambian. Sale del boceto ya aprobado: el
   Ticket 1 no lleva boceto nuevo.
3. **Detalle**: una fila por (grupo, unidad), todas cerradas. El triángulo abre sus tareas con la
   cantidad del campo. El nombre de la tarea abre un modal con sus partes (fecha, finca, supervisor,
   cantidad y total); se cierra con Cerrar, Escape o un click afuera, y el foco vuelve a la tarea. El
   panel lateral de 360 px se va.
4. **El TOTAL del Detalle sigue en pesos**, y suma sólo los comprobantes que cuentan en el filtro,
   y dentro de ellos sólo las Líneas que cuentan. Los grupos que no se comparan (fuera del filtro,
   los mixtos incluidos) quedan afuera del TOTAL por los dos lados, lo trabajado y lo facturado
   (decidido con el usuario en la revisión, 2026-10-17, Paso R1).
5. **La Revisión guarda los (grupo, unidad) que superaban y su período** (Desde y Hasta: el filtro
   recortado al mes de la fila; con Mes pasado, el mes entero). Cubre sólo ese período exacto: la de la
   1.ª quincena no cubre el mes entero ni al revés. Si después supera otro grupo en ese período, vuelve
   a Con diferencia. Se deja y se deshace desde el Detalle, **en un modal** con los grupos que superan y
   el comentario, con boceto aprobado antes de construirlo. Hace falta una migración nueva (ver Riesgo).
6. **Filtro por día** con Desde y Hasta. Atajos: Quincena pasada, Esta quincena, Mes pasado, Este mes,
   Últimos 3 meses, Este año y Otro período. Arranca en Mes pasado. Las filas siguen siendo por mes y
   Cliente; el Estado se calcula sobre el filtro recortado a cada mes; el Detalle recibe el mismo rango.
   El campo trae los partes cuya fecha cae en el filtro.
7. **Regla simple: una Línea cuenta sólo si su período entero cae adentro del filtro.** El período es
   de cada Línea (decisión 8), no del comprobante entero. Si cae en parte, esa Línea no cuenta, y:
   - el grupo donde está muestra el Facturado como "fuera del filtro" en gris, sin Dif. ni Dif. %, y
     no avisa. Vale también para un grupo que además tiene otra Línea entera adentro: ese grupo no se
     compara (grupo mixto);
   - la fila lleva arriba el aviso, con el texto del boceto aprobado: "1 factura no entra en este
     filtro" / "La Factura 0001-00001234 cubre del 1 al 15 de julio, y el filtro termina el 10. Para
     compararla, mirá la quincena entera." y el botón "Ver del 1 al 15 de julio", que cambia el filtro
     a ese período. Con varios, el título dice "N facturas" y la lista nombra cada una; una Nota de
     crédito se nombra como tal. El aviso nombra el período de las Líneas que caen en parte;
   - si ningún grupo de la fila se puede comparar, el Estado es **"Sin comparar en este período"**
     (término nuevo del Estado del mes), y no Pendiente de facturar ni Con diferencia. Falta
     comprobante sigue apareciendo al lado si corresponde (decisión del usuario, 2026-10-17).

   Porqué: la facturación es casi toda quincenal y los filtros también, así que con los atajos el caso
   casi no aparece; repartir media factura inventaba diferencias. Descartado: el reparto proporcional
   al campo o a los días (la "opción A" que se había elegido antes).
8. **Período de una Línea ya cargada**, por su fecha: el 1 cubre del 1 al 15 y el 16 cubre del 16 a fin
   de mes. El usuario confirmó que todo el histórico es así. Otra fecha (de una carga a mano) se toma
   igual: del 1 al 15 es la 1.ª quincena y del 16 en adelante, la 2.ª. Cada Línea cuenta con su propio
   período: un comprobante histórico con Líneas del 1 y del 16 se compara quincena por quincena, Línea
   por Línea (decisión del usuario, 2026-10-17; descartado: tomar el mes entero como período del
   comprobante). Una factura del mes entero se reconoce recién con el Período facturado de la E3b;
   el aviso ya sirve para ella sin cambios ("1 factura del mes completo no entra en esta quincena", con
   "Ver julio entero"), pero en la E3a no se construye ese caso aparte.
9. **El script del cruce** (el que genera el CSV para comparar contra Power BI) se rehace por (grupo,
   unidad) y usa el cálculo del módulo, no una cuenta propia.
10. **Docs a reescribir**: el glosario de Facturación (Cruce, Diferencia, Revisión de diferencia con su
    período, el término nuevo "Sin comparar en este período" en el Estado del mes, y el "se mira por mes
    completo" que hoy dice lo contrario del filtro por día), `pantallas.md` y la §3.4 de
    `plan-facturacion.md`.
11. **E3b**: sólo se marca lo que queda desactualizado, no se replanea.

## 5. Riesgo

**Migraciones**
- `migrations/facturacion/006_revision_por_grupo.sql` (la última del módulo es la 005):
  - crea `facturacion_revision_grupo` (revisión con borrado en cascada, grupo y unidad) y borra
    `facturacion_revision_tarea`;
  - suma a la Revisión su período (Desde y Hasta) y cambia el índice (no único) de (Cliente, mes) por
    uno de (Cliente, mes, Desde, Hasta); las Revisiones que ya existan quedan con el mes entero. Se
    siguen guardando todas, con quién revisó y quién deshizo: la que vale es la más reciente no
    deshecha de ese período exacto (decisión del usuario, 2026-10-17);
  - "NO DIFERIBLE": va **antes de reiniciar** el backend, como la 004; idempotente; vuelta atrás
    comentada y sin `;`, siguiendo el precedente de la `002_borrar_unidad_por_tarea.sql`;
  - un renglón al final de `migrations/ORDEN.txt` y en el `LEEME.md` del módulo.
- **Orden en producción** (ninguna de las tres está allá): 004 y 006 antes del reinicio, 005 después.
  `ORDEN.txt` queda 004, 005, 006, que es el orden para una base nueva: el encabezado de la 006 y el
  paso de deploy del plan de la E3 lo dicen explícito. Que la 004 cree la tabla por tarea y la 006 la
  borre en el mismo deploy no hace daño.
- **En `testing`** (con la 004 y la 005 ya aplicadas): antes de la 006, contar las filas de las dos
  tablas de Revisión y respaldarlas; la 006 con OK; después, confirmar que la tabla nueva existe, la
  vieja no y la Revisión tiene su período. Desde ahí, el código anterior de la E3a falla al leer
  Revisiones.
- **La E3b** tenía reservada la 006 para el Período facturado: pasa a ser la **007**.

**Contrato entre repos**
- `GET /resumen`: `desde` y `hasta` pasan de AAAA-MM a **AAAA-MM-DD**. Errores nuevos de formato y de
  rango (hasta antes de desde, más de 12 meses tocados, después del mes en curso). Cada fila trae las
  unidades por grupo en lugar de las medidas por tarea, los grupos "fuera del filtro" y los
  comprobantes que no entran, con su período.
- `GET /resumen/{cliente_id}/{mes}` (Detalle): suma `desde` y `hasta` opcionales (sin ellos, el mes
  entero); devuelve grupos con sus tareas y sus partes del rango.
- `POST` y `DELETE /resumen/{cliente_id}/{mes}/revision`: el path no cambia; suman `desde` y `hasta`
  opcionales (sin ellos, el mes entero); guardan y muestran grupos.
- Deploy: PRs hermanos de la E3a, en la misma ventana; se mergea primero el backend. La E3a no está en
  producción, así que no hace falta compatibilidad con el contrato anterior.

**Permisos**: ninguna pantalla nace ni se va y los paths no cambian, así que `ESPERADO` de
`test_mapa_permisos.py` **no cambia**.

**Datos**: en `testing` se pierden las Revisiones de prueba guardadas por tarea (quedan respaldadas).
En producción no hay ninguna.

**Zonas sensibles**: `migrations/` y `models.py` → **dos rondas** de revisión.

## 6. Decisiones de testeo

- Costuras que ya existen: el motor del cruce (funciones puras, sin base), el servicio del Resumen con
  la consulta al campo falsa, la API con su cliente de test, la migración leyendo el `.sql` y la lógica
  del front en `.js` con `node --test`. No se suman costuras nuevas.
- Casos que tienen que tener test:
  - con el mes entero, el cruce da lo mismo que hoy, agrupado (guardián del cambio);
  - un grupo con dos unidades da dos filas; facturado sin campo supera y muestra la raya;
  - una Línea del 1 entra con la 1.ª quincena y con el mes, y no entra con un filtro del 1 al 10;
  - el grupo mixto no se compara y no avisa;
  - una fila con todo afuera dice "Sin comparar en este período", no Pendiente de facturar;
  - una Nota de crédito que cae en parte afuera tampoco cuenta;
  - un comprobante con Líneas del 1 y del 16, con Quincena pasada, cuenta sólo la Línea de esa quincena;
  - una Revisión cubre sólo su período exacto y sólo si todo lo que supera está guardado;
  - la 006 en `ORDEN.txt` después de la 005, con la vuelta atrás sin `;`.
- La suite va a quedar roja entre tickets: cada ticket termina en verde con los tests de lo que tocó.

## 7. Casos borde que vas a ver en pantalla

1. **Con los atajos, el aviso casi no aparece**: cada factura cubre una quincena entera, así que con
   Quincena pasada o meses enteros queda entera adentro o entera afuera. Sale con un Otro período que
   corte una quincena (del 1 al 10, por ejemplo) y, desde la E3b, con una factura mensual mirada por
   quincena.
2. **Desde el día 16, "Quincena pasada" cae en Mes en curso**, que sólo controla Falta comprobante:
   esa quincena no muestra diferencias aunque estén. Esta quincena y Este mes caen siempre ahí.
3. **Una factura mensual cargada a mano antes de la E3b** con fecha del 1 cuenta como 1.ª quincena:
   en Quincena pasada da Con diferencia falso. Mes pasado, el atajo con el que arranca, no tiene el
   problema. El histórico no tiene facturas así.
4. **Una pulverización facturada por hectárea** no tiene campo: da Con diferencia siempre, con Dif. %
   en raya.
5. **Una Revisión de la 1.ª quincena no cubre el mes entero**: al mirar Mes pasado, el mes puede volver
   a decir Con diferencia y hay que revisarlo otra vez en ese período.
6. Un grupo que se renombra en el maestro del campo deja de estar cubierto por su Revisión: vuelve a
   Con diferencia (falla del lado seguro).

## 8. Fuera de alcance

- La E3b (Precarga y Período facturado) más allá de marcar lo desactualizado.
- Cambiar cómo se mide la pulverización; un precio por grupo; el reparto proporcional (descartado).
- Un modal común en el núcleo del front (se copia el patrón de Preliquidación; subirlo va a "A futuro").
- Los cuadros de Alertas, Mes en curso y Antes del corte, y el pie de configuración.
- La comparación contra Power BI, que la hace el usuario. Commits, DDL y deploy, con OK.

## 9. Preguntas abiertas

Ninguna. Las cuatro se cerraron con el usuario el 2026-10-17: la Revisión va en un modal; una Revisión
cubre sólo el período en que se dejó; el reparto se reemplaza por la regla simple de la decisión 7 (así
caen las preguntas del nivel del reparto y de los pesos del TOTAL), con el boceto del aviso aprobado; y
el grupo mixto no se compara.

---

## Tickets

Orden: `1 → 2 → 3 → 4 → 5a`, y `5b` en paralelo con todos.

### Ticket 1 — El Resumen por grupo y unidad (mes entero)
Qué se construye: el cruce compara por (grupo, unidad); el Resumen muestra el encabezado por mes y
Cliente con su Estado y una línea por unidad. La Revisión pasa a guardar grupos y período (migración
006), porque el Estado depende de ella; hasta el Ticket 4 el período es siempre el mes entero. El filtro
sigue en meses hasta el Ticket 4.
Repos: los dos
Toca: el motor del cruce, el servicio y la API del Resumen, el modelo de la Revisión, la migración 006,
la pantalla del Resumen
Depende de: ninguno
En paralelo con: Ticket 5b
Decisiones que aplica: 1, 2, 5 (sólo lo de guardar)
Criterios de aceptación:
- [ ] Con el mes entero, el cruce da lo de hoy agrupado (test guardián).
- [ ] Un grupo con dos unidades da dos líneas; facturado sin campo muestra la raya.
- [ ] El encabezado dice "Con diferencia · N líneas superan" y el botón va al Detalle.
- [ ] El orden es el fijo de la decisión 2.
- [ ] La 006 aplicada en `testing` con respaldo y OK; una Revisión guardada por la API cubre el mes.
- [ ] Mientras no esté el Ticket 2, el Detalle de la pantalla queda roto en el worktree (no se prueba).
PR: hermanos de la E3a (BK y FT)

### Ticket 2 — El Detalle por grupo con el modal de partes
Qué se construye: el Detalle muestra una fila por (grupo, unidad), cerradas; el triángulo abre sus
tareas con la cantidad del campo y "Sin Unidad sugerida" al lado; el nombre de la tarea abre el modal de
partes. Se va el panel lateral. El TOTAL sigue en pesos.
Repos: los dos
Toca: la API del Detalle, la pantalla del Detalle
Depende de: Ticket 1
En paralelo con: Ticket 5b
Decisiones que aplica: 1, 3, 4
Criterios de aceptación:
- [ ] Todas las filas arrancan cerradas y se abren con el teclado.
- [ ] El modal cierra con Cerrar, Escape y click afuera, y devuelve el foco a la tarea.
- [ ] A 1366 de ancho no hay scroll horizontal.
- [ ] Interfaz con `impeccable`.
PR: hermanos de la E3a

### Ticket 3 — La Revisión por grupo desde el Detalle
Qué se construye: dejar y deshacer una Revisión desde el Detalle, en un modal, con los grupos que
superan y el comentario. El 409 sin nada que supere habla de grupos.
Repos: los dos (el back casi sin cambios)
Toca: la API de la Revisión, la pantalla del Detalle
Depende de: Ticket 2
En paralelo con: Ticket 5b
Decisiones que aplica: 5
Criterios de aceptación:
- [ ] El usuario aprueba el boceto del modal antes de construirlo.
- [ ] Revisar deja el mes en Revisada; si después supera otro grupo, vuelve a Con diferencia.
- [ ] Deshacer la devuelve a Con diferencia, y el foco vuelve al botón.
PR: hermanos de la E3a

### Ticket 4 — El filtro por día y el aviso de lo que no entra
Qué se construye: Desde y Hasta con los atajos, arrancando en Mes pasado; el contrato pasa a fechas; el
Estado se calcula sobre el filtro recortado a cada mes; el Detalle y la Revisión reciben el rango; una
Línea que cae en parte afuera no cuenta, su grupo dice "fuera del filtro" y la fila lleva el aviso del
boceto con su botón; "Sin comparar en este período" cuando no queda nada para comparar.
Repos: los dos
Toca: el motor del cruce, el servicio y la API del Resumen, la API del Detalle y de la Revisión, el
filtro y las pantallas del Resumen y del Detalle
Depende de: Ticket 3
En paralelo con: Ticket 5b
Decisiones que aplica: 5 (el período), 6, 7, 8
Criterios de aceptación:
- [ ] Mes pasado da lo mismo que el Ticket 1.
- [ ] Un Otro período del 1 al 10 muestra el aviso con el texto del boceto, y su botón pasa el filtro
      al 1 al 15.
- [ ] El grupo mixto dice "fuera del filtro"; una fila con todo afuera dice "Sin comparar en este
      período".
- [ ] Una Revisión dejada en la 1.ª quincena no cubre el mes entero.
- [ ] Interfaz con `impeccable`.
- [ ] Tomar el tiempo de Este año contra `testing`; si tarda, frenar y avisar.
PR: hermanos de la E3a

### Ticket 5a — El script del cruce por grupo
Qué se construye: el script que genera el CSV para Power BI sale por (grupo, unidad) usando el cálculo
del módulo.
Repos: back
Toca: el script del cruce
Depende de: Ticket 4
En paralelo con: Ticket 5b
Decisiones que aplica: 9
Criterios de aceptación:
- [ ] El CSV de julio a septiembre en `testing` sale por grupo y da lo mismo que la pantalla.
PR: el del backend de la E3a

### Ticket 5b — Los docs y las marcas en la E3b
Qué se construye: se reescriben el glosario, `pantallas.md` y la §3.4 del plan; en el plan de la E3b se
marca lo desactualizado (la 006 pasa a 007, el período de las Líneas, el orden del deploy, el aviso de la
factura mensual).
Repos: back
Toca: los docs de Facturación y el plan de la E3b
Depende de: ninguno (las decisiones están cerradas)
En paralelo con: Tickets 1, 2, 3, 4 y 5a
Decisiones que aplica: 10, 11
Criterios de aceptación:
- [ ] El glosario ya no dice "se mira por mes completo" y suma "Sin comparar en este período".
- [ ] El plan de la E3b dice 007 y el paso de deploy dice 004 y 006 antes del reinicio, 005 después.
PR: el del backend de la E3a

## Pasos de la revisión de código

### Paso R1 — El TOTAL del Detalle deja afuera los grupos que no se comparan
Hallazgo (urgent, revisión del 2026-10-17): `_total` en `app/modulos/facturacion/services/resumen_service.py`
suma lo trabajado de todas las filas y lo facturado de todas las Líneas que cuentan, aunque el grupo esté
fuera del filtro. El grupo dice "fuera del filtro", sin diferencia, pero el TOTAL sí la muestra, inventada.
Escenarios de falla:
- Filtro del 1 al 10, una Factura de Poda del 1 al 15 y Precio sugerido para Poda: el grupo dice fuera del
  filtro, pero el TOTAL valoriza los partes de Poda contra $0 facturado.
- Grupo mixto, filtro del 1 al 20: una Línea de Poda del 1 al 15 (cuenta) y otra del 16 al 31 (no cuenta).
  El TOTAL compara lo trabajado del 1 al 20 contra lo facturado del 1 al 15.
Decisión del usuario: opción "los dos lados" (decisión 4, ampliada). Los (tarea, unidad) de todo grupo con
`fuera_del_filtro` quedan afuera de `campo_pesos`, de `facturado_pesos` y de `tareas_sin_precio`; el
resto del TOTAL no cambia. Descartado: sacar sólo lo trabajado, porque deja una diferencia falsa al revés.
Arreglo mínimo: en `_total`, juntar las claves (tarea_id, unidad) de las tareas de los grupos con
`fuera_del_filtro` y excluirlas de los tres cálculos (para lo facturado, sumar las `cruce.lineas` con
`signo * importe` cuyas claves no estén ahí, en vez de `cruce.facturado_neto`).
Toca: `resumen_service.py` y `tests/facturacion/test_detalle.py`.
Criterios de aceptación:
- [ ] Un test rojo y después verde con el grupo fuera del filtro y Precio sugerido: `campo_pesos` 0 y
      `tareas_sin_precio` sin esa tarea.
- [ ] Un test rojo y después verde con el grupo mixto: ni lo trabajado ni la Línea que cuenta suman en el
      TOTAL; un grupo comparable al lado sí suma por los dos lados.
- [ ] Los tests de facturación pasan.

## Pasos del smoke

### Paso R2 — La tabla del Resumen no entra a 1366 px
Hallazgo (smoke del 2026-10-17, contra `testing`): a 1366 × 768 la tabla del Resumen mide unos 1135 px
contra 1074 del contenedor y aparece el scroll horizontal; "Cargar factura" queda cortado al borde y el badge
"Pendiente de facturar" se parte en tres líneas. Causa: el Grupo de tareas hereda `white-space: nowrap` de
las celdas y es la columna más ancha (unos 257 px).
Decisión del usuario: se arregla antes de los PRs. Desde y Hasta apilados en el selector quedan como minor.
Arreglo mínimo: en `src/modulos/facturacion/pages/Resumen.module.css`, que el Grupo de tareas se pueda partir
(con un ancho mínimo, como el Cliente) y que el Estado y la Acción no se partan. Con eso no alcanzó (1099 px
contra 1074): la Unidad también se parte ("Horas de tractor"), y el badge del Estado tiene un ancho máximo
(el de "Pendiente de facturar") sólo por debajo de 1500 px, para que a 1920 vaya en una línea. Paso visual con `impeccable`
(`impeccable context` y `reference/craft-floor.md`), sin test, verificado en el navegador.
Toca: `Resumen.module.css` (y `Resumen.jsx` sólo si hace falta una clase).
Criterios de aceptación:
- [x] A 1366 × 768, en el Resumen, el `scrollWidth` de la tabla no supera su `clientWidth`, también con la
      fila del aviso de lo que no entra.
- [x] "Cargar factura" se ve entero y el badge del Estado no se parte en tres líneas.
- [x] A 1920 px la tabla se ve igual que antes.
Verificado (Mes pasado, Este año y del 1 al 10 de julio con el aviso, con el menú lateral expandido):
1074 = 1074 a 1366 px, el badge en dos líneas como mucho; a 1920, en una.

### Paso R3 — El foco cae en el BODY
Hallazgo (smoke del 2026-10-17): dos casos dejan el foco en el BODY, y el próximo Tab arranca desde el
principio de la página.
- En el Resumen, el botón del aviso de lo que no entra cambia el período: la tabla se desmonta mientras carga,
  y el botón con el foco desaparece con ella.
- Un click en el fondo de un modal lo cierra; el cleanup de `Modal.jsx` devuelve el foco al botón que lo abrió,
  pero después la acción por defecto del mousedown lo manda al BODY.
Decisión del usuario: se arregla antes de los PRs. El texto "que cubría ." con una Revisión vieja sin grupos
(sólo pasa en `testing`) queda como minor.
Arreglo mínimo:
- En `Resumen.jsx`, el h1 con `tabIndex={-1}` y un ref, como en el Detalle (`tituloRef`); `verPeriodo` le
  pasa el foco después de cambiar el período.
- En `Modal.jsx`, el `onMouseDown` del overlay llama a `e.preventDefault()` antes de `onCerrar()`, para que el
  foco que devuelve el cleanup no se pierda.
Los tests del front no tienen DOM: paso sin test, verificado en el navegador.
Toca: `src/modulos/facturacion/pages/Resumen.jsx` y `src/modulos/facturacion/components/Modal.jsx`.
Criterios de aceptación:
- [x] Después de "Ver ese período" en el aviso, `document.activeElement` es el h1 del Resumen y el Tab
      siguiente sigue el orden de la página (primero "Volver a leer" y las Alertas, como al cargarla).
- [x] Después de un click en el fondo del modal de Revisión, el modal se cierra y el foco queda en el botón
      que lo abrió; lo mismo con el modal de partes.
- [x] El click dentro del modal, en una zona sin controles, no lo cierra.
- [x] `npm test` y el build pasan.
