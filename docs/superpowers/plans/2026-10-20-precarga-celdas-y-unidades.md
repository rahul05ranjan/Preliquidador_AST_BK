# Precarga: celdas alineadas y unidades abreviadas en Campo (carril corto)

**Pedido.** En la grilla de Líneas de la Precarga (Facturación), cuando hay un Precio sugerido
la celda de Precio unitario queda más arriba que el resto de la fila. Y la columna Campo pasa a
unidades abreviadas: Horas de peón HsH, Horas de tractor HsM, Plantas Pl, Hectáreas Ha y
Tancadas Tanc (elegidas por el usuario el 2026-10-20). Sólo front, sin API.

**Archivos.** `src/modulos/facturacion/precarga.js` (`UNIDAD_DE_CAMPO`, y `campoDeLinea` suma el
nombre completo para el `title`), `components/GrillaLineas.jsx` y `GrillaLineas.module.css` (las
celdas de la fila editable alineadas arriba, con el texto de Campo, Importe y el número de fila
a la altura del texto de los inputs; la etiqueta "sugerido" o "a mano" cuelga debajo sin mover
nada).

**Test rojo primero.** En `precarga.test.js`, los casos de `campoDeLinea` esperan `'HsM'` en vez
de `'h máquina'` y el nombre completo de la unidad.

**Verificación.** `npm test`, `npm run build` y lint de los archivos tocados; en el navegador
contra `testing`, una Precarga con un Precio sugerido y una Cantidad a mano, con la fila
alineada, y las abreviaturas con su `title`. Revisión: una ronda de `revision-codigo` e
`impeccable critique/audit` sobre la grilla.

**Paso R1 (high de la revisión).** El `vertical-align: top` y el `padding-top` del número de
fila también pegaban en la grilla de sólo lectura (`Lectura` usa la misma clase de fila): al
abrir un Comprobante guardado, el número quedaba unos 2 px más abajo que el texto y una tarea de
varios renglones subía el resto de las celdas. Arreglo: la tabla editable lleva la clase
`editable` y las dos reglas nuevas se limitan a ella; la de sólo lectura queda centrada como
antes. Es CSS, sin test: se verifica en el navegador en las dos grillas.
