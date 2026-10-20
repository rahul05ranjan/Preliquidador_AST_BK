# Facturación — pantallas

Brief de UX del módulo (sección 8.3 de `GUIA-MODULOS.md`), trabajado con `/impeccable shape` y
rediseñado sobre un mockup aprobado por el usuario. Dice qué se ve y qué se hace en cada
pantalla; el diseño visual se termina con `impeccable` al construir cada una. Los términos son
los de [`CONTEXT-facturacion.md`](CONTEXT-facturacion.md).

## Para quién y en qué modo

- **Contadoras**: operan. Personal administrativo, en PC de escritorio, que necesita señales
  claras.
- **Gerente**: sólo consulta.
- Es una herramienta de trabajo diario sobre planillas: densidad sí, con jerarquía legible.

## El resultado que importa

Que a fin de mes ningún Cliente quede sin facturar, que cada Diferencia se explique o se
corrija, y que cada Comprobante tenga su Adjunto. La prueba de que funciona: el Cruce da los
mismos números que el informe de Power BI que hoy hace ese control.

## Dirección

- **Extensión del mundo actual**, no un diseño nuevo: los tokens de `src/index.css`, el layout
  del núcleo y lo que el núcleo ya tiene (las clases globales de campos, chips y tablas, el
  overlay "Procesando..." y `CargandoContenido`). Las pantallas copian la forma de
  Preliquidación: barra superior, barra de filtros con período y seleccionables, tabla con la
  fila TOTAL fija y panel lateral a la derecha. Lo que hoy es de Preliquidación (barra de
  filtros, tablas, aviso de error, estado por pantalla) pide antes un PR del núcleo que lo suba
  a `src/core/`.
- La idea central es **de lo general al detalle, y de ahí a la carga**: Resumen → Detalle del
  Cliente y el mes → partes del campo de una tarea. Desde el Resumen, lo que falta facturar se
  carga con la Precarga, ya armada con lo trabajado.

## Pantallas

- **Resumen** (la que abre el módulo):
  - Arriba, tres cuadros con las Alertas de facturación (Pendiente de facturar, Con diferencia
    y Falta comprobante), cada uno con su cantidad. Tocar uno filtra la tabla por esa Alerta.
  - Barra de filtros: período por día, elegido en un calendario de rango (el primer clic marca
    Desde, el segundo Hasta y aplica), con los atajos al costado (Quincena pasada, Esta
    quincena, Mes pasado, Este mes, Últimos 3 meses y Este año): un clic en un atajo aplica su
    rango y cierra el panel, y para corregirlo se vuelve a abrir; y seleccionables de Mes, Cliente y Estado. Arranca en Mes pasado.
    No se eligen días posteriores al fin del mes en curso. Las filas siguen siendo por mes y Cliente:
    cada mes se mira con el período recortado a ese mes, y el Detalle recibe el mismo período.
  - Arriba a la derecha, "Datos del campo de las HH:MM · Volver a leer": la hora de la lectura
    más vieja del sistema de campo que usa la pantalla, y un link que la vuelve a leer.
  - Debajo de los cuadros y de la barra, sobre la tabla, un aviso cuando hay tareas facturables
    sin Unidad sugerida con trabajo en el período: cuántas son, un desplegable con cada tarea y
    en cuántos Clientes, y que se definen en la app de campo. No es una Alerta: no entra en los
    cuadros ni en el Estado del mes.
  - Tabla, un bloque por mes y Cliente: un encabezado con el Estado del mes y la acción (por
    ejemplo, "Con diferencia · N líneas superan", que cuenta las líneas: un grupo con dos
    Unidades que superan cuenta 2), y debajo una línea por grupo de tareas y Unidad de
    facturación, con Campo, Facturado, Dif. y Dif. %. Sólo cantidades, sin fila TOTAL. Lo
    facturado sin Cantidad del campo muestra Dif. % como raya "—".
  - Orden fijo, sin ordenar por columna: el mes más nuevo primero, después el Estado del mes
    más urgente y después el Cliente; dentro del bloque, por grupo ("Sin grupo" al final) y por
    Unidad.
  - Un grupo con una Línea cuyo período no entra entero en el período mirado muestra el
    Facturado como "fuera del filtro", en gris, sin Dif. ni Dif. %, y no avisa; tampoco se
    compara si además tiene otra Línea entera adentro. El bloque lleva arriba el aviso
    "1 factura no entra en este filtro", con qué días cubre y dónde termina el filtro (por
    ejemplo, "La Factura 0001-00001234 cubre del 1 al 15 de julio, y el filtro termina el 10.
    Para compararla, mirá la quincena entera."), y el botón "Ver del 1 al 15 de julio", que
    pasa el filtro a ese período. Con varios, el título dice "N facturas" y la lista nombra
    cada una; una Nota de crédito se nombra como tal. Si ningún grupo del bloque se puede
    comparar, el Estado es Sin comparar en este período.
  - El encabezado muestra todos los Estados del mes del bloque. Cada etiqueta es un link a
    donde se resuelve: Con diferencia al Detalle, Falta comprobante al Comprobante sin
    Adjunto.
  - El botón del encabezado lleva a la Alerta más urgente, en este orden: Pendiente de facturar
    (Cargar factura, abre la Precarga), Con diferencia (Ver diferencia), Falta comprobante
    (Adjuntar PDF). Sin Alertas, Ver detalle.
  - Un bloque Facturada con Revisión de diferencia lleva la nota "Diferencia revisada". Los
    meses Antes del corte van en gris: sus líneas se ven en gris, con Dif., sin aviso. Un bloque
    cuyo período todavía no terminó (Período en curso) se controla igual y lleva, al lado del
    Estado, la etiqueta tenue "En curso".
  - Un pie dice desde qué mes se controla, el Umbral de diferencia y que la cosecha no entra.
    Sólo el Admin ve "Cambiar", que abre en el mismo pie un formulario chico para el Umbral de
    diferencia y el Mes de corte.
- **Detalle** (el Cruce de un Cliente en un mes):
  - Barra superior con el Cliente, el mes, el Estado del mes y los Comprobantes del mes como
    links.
  - Mira el mismo período que el Resumen, recortado al mes.
  - Tabla con una fila por grupo de tareas y Unidad de facturación, todas cerradas: Unidad,
    Campo, Facturado, Diferencia y Dif. %. Los grupos que superan el Umbral de diferencia se
    marcan con una etiqueta, no sólo con color; las tareas no avisan. El triángulo de la fila
    abre sus tareas con la Cantidad del campo, y "Sin Unidad sugerida" junto a la tarea que no
    la tiene. Fila TOTAL en pesos, que suma sólo las Líneas que cuentan en el período.
  - El nombre de una tarea abre un modal con sus partes del campo: Fecha, Finca, Supervisor,
    Cantidad y el total. Se cierra con Cerrar, Escape o un click afuera, y el foco vuelve a la
    tarea. No se abre por finca. No hay panel lateral.
  - "Marcar revisada" abre un modal con los grupos que superan y un comentario obligatorio. La
    Revisión vale sólo para el período en que se deja. Una vez revisada, un aviso muestra
    quién, cuándo y el comentario, con "Deshacer". Deshacer no la borra: queda en el registro,
    con quién la deshizo, y vale la más reciente sin deshacer de ese período.
  - No se factura desde acá: si falta facturar algo, se vuelve al Resumen.
- **Precarga** (cargar o editar una factura o una nota de crédito):
  - Es parte de Comprobantes, no una pantalla aparte: la usa quien tiene Editar en
    Comprobantes. Un Comprobante nuevo se carga en `/facturacion/comprobantes/nuevo`, y uno ya
    cargado se edita en `/facturacion/comprobantes/:id/editar`.
  - Se abre desde una fila del Resumen ("Cargar factura", con el Cliente de la fila), con
    "Nueva factura" y "Nueva nota de crédito" en Comprobantes, o con "Editar" en la vista del
    Comprobante. El Resumen siempre arma una Factura: la Nota de crédito se carga sólo desde
    Comprobantes.
  - Abre con el Período propuesto: desde el Resumen, el período que se miraba, recortado al mes
    de la fila; con "Nueva factura", el mes anterior a hoy, entero (para una factura quincenal
    se toca un atajo); en una Nota de crédito, el de la Factura que corrige.
  - Datos de la factura: el Tipo (lo da desde dónde se abre y no se cambia, tampoco al
    editar), Cliente, en una Nota de crédito la Factura que corrige, Empresa emisora (la de la
    última Factura al Cliente), Número (punto de venta y número), la Fecha de carga (hoy, sin
    editar; al editar, "Fecha de carga · persona", que no cambia) y el Período facturado.
  - El Período facturado se elige en el mismo calendario de rango del Resumen, con cuatro
    atajos al costado (Quincena pasada, Esta quincena, Mes pasado y Este mes), y dice en qué mes
    cuenta la factura. Si cruza de un mes a otro, queda en rojo con "El período tiene que quedar
    dentro de un mismo mes" y no se puede guardar.
  - Si cambia el período o el Cliente con Líneas cargadas, un aviso ofrece "Recalcular líneas"
    o "Dejar como están", y hasta elegir no se puede guardar. Recalcular arma las Líneas como
    una Precarga nueva de ese período. Dejar no toca Cantidad, Precio ni Importe: sólo Campo
    pasa al período nuevo, y si hay tareas trabajadas en el período sin Línea, un aviso dice
    "N tareas trabajadas en el período no están en la factura", con "Agregarlas", que no pasa
    de 15 líneas.
  - Líneas: una por tarea trabajada en el período, con #, Tarea, Unidad (la Unidad propuesta),
    Campo (la Cantidad del campo en la unidad de la línea, con la marca "no coincide" si no
    coincide con la Cantidad; vacía en las unidades de cosecha), Cantidad, Precio unitario (el
    Precio sugerido; al pasar el mouse dice de qué factura sale, "Último precio: FC … del …"),
    Importe y quitar. Sin Precio sugerido, el casillero queda vacío y marcado en rojo. Se
    pueden agregar líneas hasta 15, con el contador "N de 15", y todo se puede cambiar. Con más
    de 15 tareas trabajadas, trae 15 y avisa cuántas quedaron afuera. Fila de Total neto.
  - Cambiar la Unidad de una línea pasa su Cantidad a lo trabajado en esa unidad y vuelve a
    sugerir el Precio; lo que se cambió a mano no se pisa, y sólo cambia Campo.
  - Panel derecho: el PDF (arrastrar o elegir), el control del neto del PDF contra lo que suman
    las líneas (opcional), y "Falta para guardar" con lo que falta. En el alta, el PDF es
    obligatorio. Al pie, Cancelar y Guardar. Al guardar, el alta, la subida del PDF (hasta
    10 MB), un aviso y la vista del Comprobante; si la subida falla, la vista dice "Se guardó,
    pero no el PDF: adjuntalo acá".
  - Al editar: abre con las Líneas guardadas, sin recalcular, y Campo muestra lo trabajado en
    el período guardado, como referencia. Las Líneas guardadas cuentan como cambiadas a mano:
    cambiarles la Unidad sólo cambia Campo. Cada Línea conserva su finca. No se cambia el
    Cliente de una Factura que tiene Notas de crédito. El panel muestra los Adjuntos, como en
    la vista, y el PDF no se pide; abajo, "Borrar comprobante". Un Comprobante histórico no se
    edita: no muestra "Editar", y su dirección de edición avisa que no se edita.
  - En una Nota de crédito: primero se elige el Cliente y después la Factura que corrige, de
    un desplegable con las Facturas de ese Cliente. El período se copia de esa Factura (de una
    histórica, la Quincena de su primera Línea, aunque haya cubierto el mes entero: hay que
    revisarlo) y sólo se cambia dentro de su mes; fuera de él queda en rojo y no se guarda. Las
    líneas arrancan vacías, con "Agregar línea" y el Precio sugerido. Una Nota de crédito no
    tiene Campo ni Recalcular, tampoco al editarla.
  - "Importar orden del portal" abre una ventana encima con los renglones de la Orden de
    facturación traducidos con las Equivalencias. Un renglón sin Equivalencia pide la tarea, con
    "Guardar para la próxima"; hasta completarlos no se puede usar la orden. Al usarla, las
    líneas se reemplazan por las de la orden y la columna Campo sigue mostrando lo trabajado.
- **Comprobante** (uno ya cargado, por ejemplo sin Adjunto):
  - Datos de la factura y sus líneas en sólo lectura, con el Período facturado (por ejemplo,
    "1 al 15 de octubre") y "Fecha de carga · persona". Un Comprobante histórico no tiene
    Período: cada línea muestra su fecha.
  - Arriba, "Ver lo trabajado", sólo con Ver en Resumen: lleva al Detalle del Cliente en el mes
    del Período facturado, mirando ese período; en un histórico, al mes de su primera Línea,
    entero. Y "Editar", sólo con Editar en Comprobantes y si no es histórico: abre la Precarga.
  - Panel lateral para adjuntar el PDF y ver los totales. Al adjuntarlo, el mes deja de tener
    Falta comprobante.
- **Comprobantes**: listado con la barra de filtros común (período y seleccionables de Cliente,
  Empresa emisora, Tipo, PDF y Origen, más la búsqueda por número), columnas Fecha de carga,
  Número, Cliente, Empresa emisora, Origen, Neto y PDF ("Sin PDF" a la vista), y la fila TOTAL
  con la cantidad de facturas y de notas de crédito. Arriba, "Nueva factura" y "Nueva nota de
  crédito", que abren la Precarga. La Nota de crédito se muestra con importe negativo; un
  Comprobante histórico, con su marca y en sólo lectura.
- **Equivalencias**: tabla con Cliente, Texto del cliente, Tarea nuestra, Unidad y Último uso,
  con filtros de Cliente y Tarea y la búsqueda por texto. "Agregar equivalencia" abre el alta en el panel lateral.
  También se crean al importar una orden. Un mismo texto de un Cliente apunta a una sola tarea.
- **Panel** (gerente, en el marco de Gerencial): lo facturado en el período, neto de notas de
  crédito, por mes, por Cliente y por grupo de tareas, con filtros de Cliente, Grupo y Empresa
  emisora. Sólo consulta.

## Estados y volúmenes

- Volúmenes: alrededor de 55 Clientes activos y unas 135 tareas, de las cuales unas 100 son
  facturables. Un Comprobante tiene de 1 a 15 Líneas en general; una importación de una Orden
  de facturación grande trae cientos de renglones.
- Resumen sin filas con los filtros: "Nada con estos filtros".
- Un Cliente sin trabajo y sin Comprobantes en el mes no aparece.
- Con los atajos, el aviso de facturas que no entran casi no aparece: cada factura cubre una
  quincena entera. Sale con un período elegido a mano que corta una quincena y, con el Período facturado,
  con una factura del mes completo mirada por quincena ("1 factura del mes completo no entra en
  esta quincena", con "Ver julio entero").
- Quincena pasada, Esta quincena y Este mes se controlan como cualquier período, aunque caigan
  en el mes en curso: Pendiente de facturar y "Cargar factura" aparecen sin esperar al mes
  siguiente. Esta quincena y Este mes son siempre un Período en curso y llevan "En curso"; en el
  Detalle, una línea avisa que el campo todavía puede sumar partes hasta el Hasta del período.
- Comprobante histórico: sin Empresa emisora ni Adjunto, con una marca y sin Falta
  comprobante.
- Tarea facturable sin Unidad sugerida: un solo aviso sobre la tabla del Resumen, no uno por
  fila. En el Detalle, la tarea dice "Sin Unidad sugerida"; en la Precarga, la Unidad queda
  vacía y marcada.
- La lectura del sistema de campo es lenta: indicador de carga. Toda escritura muestra el
  overlay.

## Límites

- Nada de cosecha.
- No se toca Preliquidación ni Liquidación Terceros.
- Ninguna dependencia nueva. Sin modo oscuro ni versión para celular.
- No se muestra el rol de la persona. Textos en español, sin emojis.

## Abierto

- Pegar varias filas desde Excel en la grilla de líneas: por ahora no; se agrega si las
  contadoras lo piden.
