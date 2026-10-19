# Spec — Facturación E3b: la Precarga y el Período facturado

Rama `feature/facturacion-e3b` en los dos repos. Spec aprobada por el usuario el 2026-10-19, escrita por la
sesión que entrevistó, sin planificador: cada ticket lo planifica su ejecutor. Reemplaza las §3.6
(BK-E3b) y §3.7 (FT-E3b) del plan `2026-10-14-facturacion-e3.md`, con las marcas de la spec
`2026-10-17-facturacion-e3a-por-grupo.md`; lo que esas secciones dicen y esta spec no contradice sigue
en pie (ver "Siguen del plan de la E3", al final de la §4). El boceto aprobado en la entrevista tiene
6 escenas: la Precarga nueva, el cambio de unidad, Recalcular o Dejar con el aviso de las tareas que
faltan, la edición, la Nota de crédito y el calendario en rojo.

## 1. Problema

Hoy un Comprobante se carga a mano, Línea por Línea, con una fecha en la cabecera y otra en cada
Línea. Esa fecha mezcla dos cosas: cuándo se cargó y qué período se factura. Por eso el cruce adivina
el período por la quincena de la fecha, y una factura del mes entero cargada a mano cuenta como si
fuera de la 1.ª quincena. Además, la contadora vuelve a tipear lo que el campo ya sabe: qué tareas se
trabajaron, cuánto, en qué unidad y a qué precio se facturó la última vez.

## 2. Solución

El Comprobante guarda su **Período facturado** (Desde y Hasta, dentro de un mismo mes), elegido con el
mismo calendario del Resumen; la fecha de cabecera pasa a ser la **Fecha de carga**, siempre hoy. El
cruce cuenta cada Línea con el período de su Comprobante. La **Precarga** arma la Factura con lo
trabajado en el período: una Línea por tarea, con la unidad propuesta, la Cantidad del campo, el
Precio sugerido y la Empresa de la última Factura. La contadora la corrige, adjunta el PDF y guarda.
La misma pantalla edita un Comprobante y carga una Nota de crédito.

## 3. Historias de usuario

1. Como contadora, quiero elegir el período que factura con el mismo calendario del Resumen, para que
   una factura del mes entero cuente como del mes entero.
2. Como contadora, quiero abrir la Precarga desde una fila del Resumen y encontrar la factura ya
   armada con lo trabajado, para sólo revisarla, adjuntar el PDF y guardar.
3. Como contadora, quiero que cada Línea traiga la unidad y el precio con los que le facturé a ese
   Cliente la última vez, para no buscarlos en la factura anterior.
4. Como contadora, quiero cambiar la unidad de una Línea y que la Cantidad pase a lo trabajado en esa
   unidad, para facturarle a un Cliente la poda techo en horas de máquina.
5. Como contadora, quiero que al cambiar el período o el Cliente se me pregunte si recalcular, para no
   perder lo que corregí a mano.
6. Como contadora, quiero editar un Comprobante en la misma pantalla en que lo cargué, viendo contra
   qué trabajado lo comparo, para corregir un error sin borrarlo.
7. Como contadora, quiero cargar una Nota de crédito eligiendo la Factura que corrige, para que herede
   su período.

## 4. Decisiones cerradas

1. **El cruce cuenta cada Línea con el Período facturado de su Comprobante.** Una factura del mes
   entero no entra en una quincena: sale el aviso que ya existe ("1 factura del mes completo no entra
   en esta quincena", con "Ver julio entero"). Un Comprobante sin período (los históricos) sigue con la
   quincena de la fecha de cada Línea (decisión 8 de la E3a). En los cargados desde la E3b,
   `facturacion_linea.fecha` se guarda igual a `periodo_desde`, como dato interno: la consulta por mes
   y el índice no cambian. `LineaFacturada` suma el período del Comprobante, y su `periodo` lo devuelve
   si no es nulo; si es nulo, usa `periodo_de_linea(fecha)`. Porqué: el período lo decide quien carga,
   no la fecha. Descartado: dos columnas de período en la Línea.
2. **La Nota de crédito** se carga sólo desde "Nueva nota de crédito" en Comprobantes; el Resumen
   siempre arma Factura. Primero se elige el Cliente y después la Factura que corrige, de un desplegable
   con las Facturas de ese Cliente. El período se copia de esa Factura y se puede cambiar dentro del
   mismo mes; si la Factura es histórica (sin período), se propone la quincena de su primera Línea. La
   grilla arranca vacía, con "Agregar línea" y el Precio sugerido común, sin columna Campo ni
   Recalcular. El PDF es obligatorio en el alta. Queda para más adelante: "Copiar las líneas de la
   Factura".
3. **La edición abre la misma Precarga** con las Líneas guardadas, sin recalcular. Campo muestra lo
   trabajado en el período guardado, como referencia, con la marca "no coincide"; en una Nota de crédito
   no hay Campo. Si cambia el período o el Cliente, aparece Recalcular o Dejar (decisión 4); sigue la
   regla de la E2: no se cambia el Cliente de una Factura con Notas. **El tipo queda fijo**: un PUT que
   lo cambia da 422 (hoy la E2 lo permite si no hay Notas; si se cargó mal, se borra y se carga de
   nuevo). La Fecha de carga no cambia y se muestra "Fecha de carga · persona". El PDF no es
   obligatorio: se ven los Adjuntos de la E2 y sigue "Borrar comprobante". Un histórico no se edita (ya
   existe `HistoricoNoEditable`). Se conserva la finca que tenían las Líneas. Las Líneas guardadas
   cuentan como tocadas a mano (Cantidad y Precio): cambiarles la unidad no las pisa, sólo cambia Campo
   (decisión 7). Porqué: lo guardado salió del PDF y no se recalcula sin que la contadora lo pida
   (decidido por el usuario, 2026-10-19).
4. **"Dejar como están"** deja las Líneas intactas (Cantidad, Precio e importe). Sólo cambia Campo, que
   pasa al período nuevo con la marca de lo que no coincide. Si hay tareas trabajadas en el período sin
   Línea, aparece "N tareas trabajadas en el período no están en la factura", con el botón
   "Agregarlas", que respeta el tope de 15 líneas. "Recalcular" vuelve a armar las Líneas como una
   Precarga nueva.
5. **La `facturacion/007`** suma `periodo_desde` y `periodo_hasta` al Comprobante y completa los
   cargados a mano (`es_historico = 0 AND periodo_desde IS NULL`) con el período de las quincenas de
   sus Líneas: todas en la 1.ª, del 1 al 15; todas en la 2.ª, del 16 a fin de mes; en las dos, el mes
   entero. Después, la `fecha` de esas Líneas pasa a `periodo_desde`. El pre-check frena si un
   Comprobante tiene Líneas en dos meses, y se consulta al usuario. Descartado: dejarlos sin período.
6. **El calendario es el del Resumen**, con 4 atajos: Quincena pasada, Esta quincena, Mes pasado y
   Este mes (sin Últimos 3 meses ni Este año). Un rango que cruza de mes se puede marcar, pero queda en
   rojo con "El período tiene que quedar dentro de un mismo mes" y no se guarda. El período propuesto:
   desde el Resumen, el filtro recortado al mes de la fila; desde "Nueva factura", el mes anterior a hoy,
   entero; en una Nota de crédito, el de la Factura que corrige.
7. **Cambiar la unidad de una Línea** pasa la Cantidad a lo trabajado en esa unidad en el período,
   según `MEDIDA_DE_UNIDAD`; el Precio se vuelve a sugerir para esa unidad y el importe se recalcula.
   Lo tocado a mano (Cantidad o Precio) no se pisa: sólo cambia Campo, con la marca. En las unidades sin
   medida (las de cosecha: `bins`, `bins_c`, `bins_m` y `viajes`) la Cantidad queda vacía. Por eso la
   ruta de la Precarga devuelve, por tarea, todas las medidas y los precios por (tarea, unidad).
   Porqué: algunos Clientes, por arreglos internos, facturan una tarea en otra unidad (la poda techo,
   que va en plantas, para un Cliente va en horas de máquina), y así el cruce queda bien.
8. **La unidad propuesta** de cada Línea es la de la última Factura a ese Cliente por esa tarea, sin
   contar las Notas de crédito; si no hay, la Unidad sugerida. El cruce de una tarea sin nada facturado
   sigue con la Unidad sugerida. Va al glosario. Descartado: una tabla de unidad por Cliente en
   Mantenimiento.

**Siguen del plan de la E3** (§3.6 y §3.7), confirmados en la entrevista:
- La Fecha de carga es `hoy()`; la API no recibe `fecha`, ni en la cabecera ni en las Líneas.
- El Precio sugerido y la Empresa emisora salen de la última Factura del Cliente (por tarea y unidad,
  el precio), sin contar las Notas. El `title` del precio dice "Último precio: FC … del …".
- Hasta 15 Líneas, con el contador "N de 15". Sin finca en la Precarga.
- El panel del PDF (`PanelPdf`): el PDF, el control del neto y "Falta para guardar".
- Al guardar: el alta con overlay, después `subirAdjunto` (tope de 10 MB), un toast y el paso a la
  vista. Si la subida falla: "Se guardó, pero no el PDF: adjuntalo acá".
- La vista del Comprobante muestra el Período ("1 al 15 de octubre"), "Fecha de carga · persona",
  "Ver lo trabajado" (sólo con Ver en `resumen`) y "Editar" (sólo con Editar y si no es histórico).
- El listado rotula la fecha "Fecha de carga".
- Los 422: "Falta el período facturado." (campo `periodo_desde`), "El período tiene que quedar dentro
  de un mismo mes." (campo `periodo_hasta`) y `periodo_invalido` (Hasta antes de Desde).

## 5. Riesgo

**Migraciones**
- `migrations/facturacion/007_periodo_facturado.sql` (la última del módulo es la 006):
  - `ALTER TABLE facturacion_comprobante` suma `periodo_desde` y `periodo_hasta`, `DATE NULL`. El ALTER
    **no es idempotente**: el encabezado lo dice y el pre-check confirma que las columnas no existen.
  - Pre-check: cuántos cargados a mano sin período hay y cuáles tienen Líneas en dos meses. Si hay
    alguno en dos meses, **se frena y se consulta**. En producción no se esperan cargados a mano.
  - UPDATE del período por las quincenas de las Líneas (decisión 5) y, después, UPDATE de la `fecha`
    de esas Líneas a `periodo_desde`. La `fecha` de cabecera de los cargados a mano queda como estaba
    y desde ahí se lee como Fecha de carga.
  - Respaldo antes de correrla: las filas de los cargados a mano en `facturacion_comprobante` y
    `facturacion_linea` (la `fecha` original de las Líneas se pierde con el UPDATE).
  - Vuelta atrás comentada y sin `;` (precedente de la 002): devolver la `fecha` de las Líneas desde el
    respaldo y borrar las dos columnas.
  - "NO DIFERIBLE": va **antes de reiniciar** el backend, porque el código nuevo lee las columnas; el
    código anterior no las nota.
  - Un renglón al final de `migrations/ORDEN.txt`, después de la 006, y otro en el `LEEME.md` del
    módulo.
- **En `testing`**: pre-check, respaldo, la 007 con OK; después, confirmar las dos columnas y que los
  cargados a mano tienen período y la `fecha` de sus Líneas es `periodo_desde`.

**Contrato entre repos**
- `POST` y `PUT /comprobantes`: la entrada pierde `fecha` (cabecera y Líneas) y suma `periodo_desde` y
  `periodo_hasta`; el servicio pone la Fecha de carga en hoy en el alta y no la toca al editar. El PUT da
  422 si cambia el tipo (cambio en `editar` de `comprobantes_service.py`, que hoy compara
  `cliente_id` y `tipo` juntos).
- `ComprobanteFila` y `ComprobanteDetalle` suman `periodo_desde`, `periodo_hasta` y
  `creado_por_nombre`; el `mes` del listado sale del período, y si no hay (histórico), de la primera
  Línea, como hoy.
- **Nace la ruta 18**: `GET /api/facturacion/precarga` (Cliente, Desde y Hasta), con `comprobantes` y
  nivel Editar. Devuelve una Línea propuesta por tarea trabajada (unidad propuesta, todas sus medidas
  en el período), los precios por (tarea, unidad) con su comprobante de origen y la Empresa sugerida.
  Archivos de arranque: `services/precarga_service.py` nuevo, sobre `precios.py`, `cruce.py`
  (`MEDIDA_DE_UNIDAD`) y la consulta al campo de `resumen_service.py`.
- `GET /resumen` y el Detalle no cambian de forma: cambia qué Líneas cuentan (decisión 1).
- Deploy: PRs hermanos, en la misma ventana; se mergea primero el backend. El front anterior manda
  `fecha` y no manda período: con el backend nuevo, su alta da 422. Facturación está escondida (nadie
  tiene su rol), así que no hace falta compatibilidad.

**Permisos**: nace una ruta, así que `ESPERADO` de `tests/facturacion/test_mapa_permisos.py` pasa de
17 a **18** (y el nombre del test que cuenta las rutas). Ninguna pantalla nace: la Precarga es parte de
`comprobantes`. En el front, `/comprobantes/:id/editar` nombra la pantalla `comprobantes`.

**Datos**: en `testing` los cargados a mano de prueba cambian la `fecha` de sus Líneas (quedan
respaldados). En producción no se esperan cargados a mano; el pre-check lo confirma.

**Zonas sensibles**: `migrations/` y `models.py` → **dos rondas** de revisión.

## 6. Decisiones de testeo

- Costuras que ya existen: el motor del cruce (funciones puras), el servicio del Resumen y el de
  Comprobantes con la consulta al campo falsa, la API con su cliente de test, la migración leyendo el
  `.sql` y la lógica del front en `.js` con `node --test`. Nace una costura: `precarga_service.py`,
  con la consulta al campo falsa, como el Resumen. En el front, la lógica de la Precarga va en
  `precarga.js` (puro), no en el componente.
- Casos que tienen que tener test:
  - una Factura del 1 al 31 no cuenta con Quincena pasada y cuenta con Mes pasado; un histórico sin
    período sigue contando por la quincena de cada Línea (guardián);
  - el alta guarda la Fecha de carga en hoy y la `fecha` de las Líneas en `periodo_desde`; la edición
    no cambia la Fecha de carga;
  - los tres 422 del período, y el 422 al cambiar el tipo;
  - la unidad propuesta sale de la última Factura del Cliente por esa tarea, salta las Notas y, si no
    hay, usa la Unidad sugerida;
  - cambiar la unidad trae la medida y el precio nuevos; con la Cantidad tocada a mano, sólo cambia
    Campo; en `bins`, la Cantidad queda vacía;
  - "Dejar como están" no toca las Líneas y cuenta las tareas que faltan; "Agregarlas" no pasa de 15;
  - la 007 en `ORDEN.txt` después de la 006, con la vuelta atrás sin `;`, y el UPDATE de las tres
    combinaciones de quincenas;
  - `ESPERADO` con 18 rutas.
- La suite puede quedar roja entre tickets: cada ticket termina en verde con los tests de lo que tocó.

## 7. Casos borde que vas a ver en pantalla

1. **Una factura del mes entero mirada por quincena** no se compara: el Resumen muestra el aviso y
   "Ver julio entero". Es lo esperado; antes contaba como 1.ª quincena y daba diferencias falsas.
2. **Desde "Nueva factura" el período propuesto es el mes anterior entero**: si la factura es
   quincenal, hay que tocar un atajo.
3. **Una tarea que el Cliente factura en otra unidad** aparece la primera vez con la Unidad sugerida;
   desde la segunda Factura, con la unidad de la última.
4. **Campo en una Línea de cosecha** (`bins`, `viajes`) queda vacío: no hay medida para comparar.
5. **Una Nota de crédito de una Factura histórica** propone la quincena de su primera Línea, aunque la
   Factura haya cubierto el mes entero: revisar el período antes de guardar.
6. **Más de 15 tareas trabajadas** en el período: la Precarga trae 15 y avisa cuántas quedaron afuera;
   "Agregarlas" tampoco pasa de 15.
7. **Un Comprobante cargado a mano antes de la E3b** aparece, después de la 007, con un período
   deducido de sus Líneas y su vieja fecha como Fecha de carga.

## 8. Fuera de alcance

- "Copiar las líneas de la Factura" en la Nota de crédito.
- Una tabla de unidad por Cliente (descartada); cambiar cómo mide el cruce una tarea sin facturado.
- Editar un histórico; cambiar el tipo de un Comprobante.
- Los minors de "A futuro" del calendario y de la E3a, y los formatos de exportación por Cliente.
- Commits, DDL y deploy, con OK.

## 9. Preguntas abiertas

Ninguna. La única que quedó la cerró el usuario al aprobar la spec (2026-10-19), como se recomendaba:
el período de una Nota de crédito puede cambiar sólo dentro del mes de la Factura que corrige, no a
cualquier mes, porque una Nota corrige lo facturado en ese mes.

---

## Tickets

Orden: `1 → 2 → 3 → 4 → 5 → 5b`, y `6` en paralelo con todos.

### Ticket 1 — El Período facturado en el Comprobante
Qué se construye: el Comprobante guarda su Período facturado y la fecha de cabecera pasa a ser la Fecha
de carga (hoy). El formulario actual de carga a mano cambia las fechas por el calendario del Resumen con
4 atajos y el rojo si cruza de mes. El cruce cuenta cada Línea con el período de su Comprobante. La vista
muestra el Período y "Fecha de carga · persona"; el listado rotula "Fecha de carga" y saca el mes del
período.
Repos: los dos
Toca: el modelo y la migración 007, el servicio y la API de Comprobantes, el motor del cruce y la lectura
de Líneas del Resumen, el formulario, la vista y el listado de Comprobantes, el calendario
Depende de: ninguno
En paralelo con: Ticket 6
Decisiones que aplica: 1, 5, 6 (salvo el período propuesto desde el Resumen y la Nota de crédito)
Criterios de aceptación:
- [ ] Una Factura del 1 al 31 no cuenta con Quincena pasada y cuenta con Mes pasado; un histórico
      cuenta igual que antes (test guardián).
- [ ] El alta guarda la Fecha de carga en hoy y las Líneas con `fecha = periodo_desde`; la API ya no
      recibe `fecha`.
- [ ] Los tres 422 del período llegan al formulario en su campo; un rango que cruza de mes queda en rojo
      y no deja guardar.
- [ ] La vista dice "1 al 15 de octubre" y "Fecha de carga · persona"; el listado dice "Fecha de carga".
- [ ] La 007 aplicada en `testing` con pre-check, respaldo y OK.
- [ ] Interfaz con `impeccable`.
PR: hermanos de la E3b (BK y FT)

### Ticket 2 — La Precarga de una Factura nueva
Qué se construye: la ruta 18 y la página Precarga, que reemplaza al formulario para una Factura nueva.
Arma una Línea por tarea trabajada en el período, con la unidad propuesta, la Cantidad del campo, el
Precio sugerido con su `title` y la Empresa de la última Factura; la columna Campo con la marca "no
coincide"; el contador "N de 15"; el panel del PDF con "Falta para guardar"; el guardado con la subida
del PDF. Se entra desde una fila del Resumen (con el período recortado al mes) y desde "Nueva factura"
(con el mes anterior entero).
Repos: los dos
Toca: el servicio y la API de la Precarga (nuevos), la tabla de permisos de los tests, la lógica de la
Precarga del front, la página Precarga y su panel del PDF, las rutas del módulo, el Resumen (la entrada)
Depende de: Ticket 1
En paralelo con: Ticket 6
Decisiones que aplica: 6 (el período propuesto), 8, y "Siguen del plan de la E3"
Criterios de aceptación:
- [ ] `ESPERADO` tiene 18 rutas y la Precarga pide `comprobantes` con Editar.
- [ ] La unidad propuesta sale de la última Factura del Cliente por esa tarea, salta las Notas y, si no
      hay, usa la Unidad sugerida.
- [ ] Con más de 15 tareas trae 15 y avisa cuántas quedaron afuera.
- [ ] Sin PDF no se guarda; si la subida falla, queda el aviso "Se guardó, pero no el PDF: adjuntalo
      acá" en la vista.
- [ ] Desde una fila del Resumen con Quincena pasada abre con esa quincena; desde "Nueva factura", con el
      mes anterior entero.
- [ ] Interfaz con `impeccable`, igual al boceto aprobado.
PR: hermanos de la E3b

### Ticket 3 — Cambiar la unidad, el período o el Cliente con la Precarga abierta
Qué se construye: al cambiar la unidad de una Línea, la Cantidad pasa a la medida de esa unidad y el
Precio se vuelve a sugerir, sin pisar lo tocado a mano. Al cambiar el período o el Cliente, el aviso
Recalcular o Dejar; con Dejar, Campo pasa al período nuevo y aparece "N tareas trabajadas en el período
no están en la factura" con "Agregarlas".
Repos: front
Toca: la lógica de la Precarga del front, la página Precarga
Depende de: Ticket 2
En paralelo con: Ticket 6
Decisiones que aplica: 4, 7
Criterios de aceptación:
- [ ] Pasar una Línea de Plantas a Horas de tractor trae las horas de máquina y el precio de esa unidad;
      con la Cantidad tocada a mano, sólo cambia Campo.
- [ ] En `bins`, la Cantidad queda vacía.
- [ ] "Dejar como están" no toca Cantidad, Precio ni importe; "Agregarlas" no pasa de 15.
- [ ] "Recalcular" deja la grilla igual que una Precarga nueva de ese período.
- [ ] Interfaz con `impeccable`, igual al boceto aprobado.
PR: el del front de la E3b

### Ticket 4 — Editar un Comprobante en la Precarga
Qué se construye: `/comprobantes/:id/editar` abre la Precarga con las Líneas guardadas, sin recalcular;
Campo del período guardado con la marca; Recalcular o Dejar al cambiar el período o el Cliente (con la
regla de la Factura con Notas); los Adjuntos de la E2 y "Borrar comprobante". El tipo queda fijo (422 si
cambia), la Fecha de carga no cambia y la finca se conserva. Un histórico no muestra "Editar".
Repos: los dos (el back, sólo el 422 del tipo)
Toca: el servicio de Comprobantes (la edición), la página Precarga, las rutas del módulo, la vista del
Comprobante
Depende de: Ticket 3
En paralelo con: Ticket 6
Decisiones que aplica: 3
Criterios de aceptación:
- [ ] Un PUT que cambia el tipo da 422; uno que cambia el Cliente de una Factura con Notas sigue dando
      el error de la E2.
- [ ] Editar y guardar sin cambios deja la Fecha de carga, la finca y las Líneas iguales.
- [ ] Guardar sin PDF nuevo funciona; los Adjuntos se suben y se quitan como en la E2.
- [ ] Un histórico no muestra "Editar" y su URL de edición avisa que no se edita.
- [ ] Interfaz con `impeccable`, igual al boceto aprobado.
PR: hermanos de la E3b

### Ticket 5 — La Nota de crédito en la Precarga
Qué se construye: "Nueva nota de crédito" en Comprobantes abre la Precarga en modo Nota: el Cliente,
después la Factura que corrige (desplegable con las Facturas de ese Cliente), el período copiado de ella
(o la quincena de su primera Línea si es histórica), editable dentro del mes de la Factura; la grilla
vacía con "Agregar línea" y el Precio sugerido común, sin Campo ni Recalcular; el PDF obligatorio en el
alta. Editar una Nota abre sin Campo. Sale el puente `NuevoComprobante()` de las rutas. Además, la
vista del Comprobante suma "Ver lo trabajado" (§4, "Siguen del plan de la E3"): lleva al Detalle del
Cliente y el mes del Período, filtrado por el Período (un histórico, sin Período: el mes de su primera
Línea, sin filtro), y se muestra sólo con Ver en `resumen` (sumado a este ticket por el usuario,
2026-10-19).
Repos: front (el back ya valida la Factura corregida)
Toca: la lógica de la Precarga del front, la página Precarga, el listado de Comprobantes (el botón),
la vista del Comprobante ("Ver lo trabajado"), las rutas del módulo
Depende de: Ticket 4
En paralelo con: Ticket 6
Decisiones que aplica: 2, 6 (el período de la Nota)
Criterios de aceptación:
- [ ] El desplegable muestra sólo Facturas del Cliente elegido; al elegir una, el período se copia.
- [ ] Un período fuera del mes de la Factura queda en rojo y no se guarda.
- [ ] Sin PDF, el alta no se guarda; editar una Nota no muestra Campo ni Recalcular.
- [ ] "Ver lo trabajado" aparece en la vista sólo con Ver en `resumen` y lleva al Detalle del
      Cliente y el mes del Comprobante.
- [ ] Interfaz con `impeccable`, igual al boceto aprobado.
PR: el del front de la E3b

### Ticket 5b — El back controla el mes de la Nota de crédito
Qué se construye: el alta y la edición de una Nota de crédito dan 422 `comprobante_invalido` en
`periodo_desde` si el Período facturado no queda en el mes de la Factura que corrige. El mes de la
Factura es el de su Período o, si no tiene (un histórico), el de su primera Línea, como el `mes` del
listado; una Factura sin Período ni Líneas no tiene mes y no se controla. Hasta el Ticket 5 la regla
vivía sólo en el front (sumado por el usuario, 2026-10-19).
Repos: back
Toca: el servicio de Comprobantes (la validación de la Factura corregida)
Depende de: Ticket 5
En paralelo con: Ticket 6
Decisiones que aplica: 6 (el período de la Nota) y §9
Criterios de aceptación:
- [ ] Una Nota con período de otro mes que su Factura da 422 en `periodo_desde`, en el alta y en la
      edición; con el mismo mes se guarda.
- [ ] Contra una Factura histórica sin Período cuenta el mes de su primera Línea.
- [ ] El mensaje dice el mes de la Factura, para que el front lo muestre en el campo.
PR: el del backend de la E3b

### Ticket 6 — Los docs de la E3b
Qué se construye: el glosario de Facturación ajusta el Período propuesto (decisión 6), suma la unidad
propuesta (decisión 8), la Nota de crédito desde Comprobantes y el tipo fijo al editar; `pantallas.md`
suma la Precarga; las §3.6 y §3.7 del plan de la E3 quedan marcadas como reemplazadas por esta spec.
Repos: back
Toca: los docs de Facturación y el plan de la E3
Depende de: ninguno (las decisiones están cerradas)
En paralelo con: Tickets 1, 2, 3, 4 y 5
Decisiones que aplica: 2, 3, 6, 8
Criterios de aceptación:
- [ ] El glosario nombra la unidad propuesta y el Período propuesto según desde dónde se abre.
- [ ] El plan de la E3 remite a esta spec en las §3.6 y §3.7.
PR: el del backend de la E3b
