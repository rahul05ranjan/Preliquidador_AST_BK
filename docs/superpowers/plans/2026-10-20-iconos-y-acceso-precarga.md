# Íconos de Resumen y Comprobantes, y acceso a la Precarga desde el Detalle

Carril corto, sólo front, sin API ni DDL.

- **Qué se pide.** Comprobantes deja el ícono de Conceptos y pasa a un recibo; Resumen pasa a
  una planilla de control (un portapapeles con tilde). La tarjeta del módulo en Inicio queda
  como está. En el Detalle de una fila del Resumen con Pendiente de facturar, un botón
  "Cargar factura" en la cabecera abre la Precarga con el Cliente y el período del Detalle;
  sólo con Editar en `comprobantes`, como la acción de la fila.
- **Archivos.** `src/core/ui/iconos.jsx` (núcleo: los dos íconos nuevos),
  `src/modulos/facturacion/rutas.jsx` (los íconos de las dos rutas y su comentario),
  `src/modulos/facturacion/pages/Detalle.jsx` (el botón) y `src/modulos/facturacion/estados.js`
  (exportar `rutaDeCargarFactura`, que hoy arma esa misma ruta para la fila). Son 4 archivos:
  el cuarto es un `export`, para no repetir el armado de la ruta.
- **Test rojo primero.** En `estados.test.js`: `rutaDeCargarFactura` con el período parcial
  del Detalle da `/facturacion/comprobantes/nuevo?cliente=…&desde=…&hasta=…`, y sin `desde` ni
  `hasta` usa el mes entero. Hoy falla porque la función no está exportada.
- **Botón.** Si convive con "Marcar revisada", "Cargar factura" queda primario y "Marcar
  revisada" pasa a secundario (como en la fila del Resumen, donde la acción del estado es la
  primaria).
- **Verificación.** Suite del front, lint y build; `revision-codigo` (un agente, dos ejes) y el
  `verificador-review`; `/impeccable critique` y `audit` sobre el Detalle y el menú; smoke contra
  `testing` con el usuario de prueba: los dos íconos en el menú, el botón en un Detalle con
  Pendiente de facturar que abre la Precarga con Cliente y período cargados, y el Detalle de una
  fila Facturada sin el botón.

## Desvíos al ejecutar

- **En vez de exportar `rutaDeCargarFactura`**, `estados.js` suma
  `rutaDeCargarDesdeElDetalle(detalle, puedeEditarComprobantes)`: decide si el Detalle está
  Pendiente de facturar y delega en `destinoDeEtiqueta`, así el permiso y el armado de la ruta
  quedan en un solo lugar, el mismo que usa la fila. El test rojo se armó sobre esa función
  (falló por el export faltante): con Pendiente y Editar da la ruta de la Precarga con el
  período del Detalle; sin Pendiente o sin Editar, null.
- **Un quinto archivo, `Detalle.module.css`**, con `.enlaceBoton`: el botón es un `Link` (navega,
  se puede abrir en otra pestaña) y salía subrayado y sin foco visible propio.
- **Tras la crítica, con el usuario:**
  - El ícono `planilla` pasa a un clip más grande, al estilo de los demás íconos: el primero
    parecía una batería.
  - Si conviven los dos botones, "Marcar revisada" va primero y "Cargar factura", la primaria,
    al final.
  - **Un sexto archivo, `Precarga.jsx`**: al guardar o borrar un Comprobante también invalida
    el Resumen (y sus Detalles, que cuelgan de esa clave). Sin eso, al volver de la Precarga
    el Detalle seguía mostrando Pendiente de facturar hasta recargar.
