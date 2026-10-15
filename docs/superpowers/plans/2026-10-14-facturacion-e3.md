# Plan: Facturación, etapa 3 (Resumen, Detalle y Precarga)

Fecha: 2026-10-14. Worktrees: backend y front en la rama `feature/facturacion-e3`. La etapa se parte en E3a y E3b (ver 3.3).

## Aprobación

2026-10-14: el usuario aprobó el plan "como recomendás". Las preguntas abiertas de la sección 5
quedan cerradas con lo que el plan asume en cada una, y las premisas de arriba se resuelven como
propone el plan (corte en octubre de 2026 y lo mueve el Admin; los meses Antes del corte se ven y
suman en el TOTAL; PDF obligatorio en el alta de la Precarga; la Nota de crédito resta cantidad;
los meses para comparar con Power BI los elige el usuario en F5, o los tres últimos cerrados con
históricos). Los bocetos de F0 siguen necesitando el OK del usuario antes de los pasos visuales.

### Ajustes de ejecución (2026-10-14, con OK del usuario, para ir más rápido)

- **Back y front en paralelo.** Un `ejecutor` sigue los pasos A del backend y otro los FA del
  front, cada uno en su worktree. Cada carril sigue de a un par por vez.
- **Tests sólo del paso.** Cada par corre únicamente la verificación que nombra su paso, no el
  módulo entero ni `tests/core` de más. La suite completa corre una vez en A13 y en FA7.
- **Nombre de las tareas de una Revisión** (`revision.tareas[].tarea_nombre`, ruta 14): no se
  guarda en la base. Sale del maestro del campo y, si la tarea no está ahí, de las Líneas del
  mes (la misma regla del Detalle). La 004 no cambia. Lo aplican A8 y A9.
- **A4b. Par: igualar la consulta del campo a la de Power BI** (el usuario pasó la consulta que usa
  Power BI, 2026-10-14). Coinciden las tres planillas, `estado <> 9`, el tractor 1 de
  pulverización (la nodriza no se factura) y las medidas de maquinaria y tareas manuales. Única
  diferencia: en pulverización Power BI toma `unidades = 0`; la nuestra leía `pdpulve.unidades`.
  Se pasa a `0 AS unidades`. Confirmado con el usuario: el mes sale de la fecha de la tarea
  (`fecha`, no `date_time`), y `tareas.unidad` no se usa para facturar (sigue la Unidad sugerida
  del BK #94). Riesgo para F5: un valor con coma decimal en el campo, Power BI puede leerlo y el
  REGEXP lo cuenta 0.
- **A7b. Par: precio 0 es "sin precio"** (decisión del usuario, 2026-10-14). Si la última
  Factura del Cliente para la (tarea, unidad) tiene precio unitario 0 o menos, no hay Precio
  sugerido: `precios_sugeridos` no devuelve esa clave (no se busca una Factura anterior). En el
  Detalle la tarea cuenta en `tareas_sin_precio`; en la Precarga el precio queda vacío. Porqué:
  un precio 0 suele ser un error de carga.
- **A8b. Par: precio medio 0 es "sin precio"** (decisión del usuario, 2026-10-15, la misma regla
  del A7b). En el Detalle, si el precio medio de las Facturas del mes para una (tarea, unidad) da 0
  o menos, esa fila no tiene precio: no cae al Precio sugerido y la tarea cuenta en
  `tareas_sin_precio`. Archivos: `resumen_service.py` y `tests/facturacion/test_detalle.py`. Va
  después del A9, que toca el mismo servicio. Un mes futuro en el Detalle sigue como Mes en curso,
  sin 422 (decisión del usuario, 2026-10-15).
- **A10b. Par: el Resumen trae el último cambio de la configuración** (decisión del usuario,
  2026-10-15, por el FRENADO del FA5). El boceto aprobado muestra en el pie "Último cambio: quién,
  cuándo", y la ruta 13 no lo traía. El schema `Resumen` suma `actualizado_en: datetime | None` y
  `actualizado_por_nombre: str | None`, opcionales, que salen de `ResumenService.configuracion()`
  (`None` si nadie la cambió). Archivos: `schemas.py`, `api/resumen.py` (o el servicio, si el
  Resumen se arma ahí) y `tests/facturacion/test_api_resumen.py`. El front ya los lee: no cambia.
- **Comentario de la Revisión** (A9): se recortan los espacios de los bordes antes de medir el
  largo, igual que el front (FA4).

## Antes de empezar: premisas que no se cumplen

1. **Con el Mes de corte en octubre de 2026, hoy no hay nada para cargar desde el Resumen.**
   - Septiembre queda Antes del corte y octubre es Mes en curso. Hasta el 1 de noviembre no aparece ningún Pendiente de facturar ni Con diferencia, y tampoco el botón "Cargar factura".
   - La segunda condición de aceptación ("una factura del mes pasado se carga desde el Resumen") sólo se cumple si el Admin mueve el corte hacia atrás. En `testing` se mueve para los smokes (F4 y F11). En producción decide el usuario (pregunta 1).
   - La comparación con Power BI no depende del corte: las filas Antes del corte muestran sus números, y además la comparación va por script.
2. **"El Cruce da lo mismo que Power BI" no puede ser literal.**
   - Power BI mide cada tarea por su Unidad sugerida. El módulo la mide por la unidad de lo facturado (plan §3.3).
   - Una tarea facturada en otra unidad da a propósito otra Cantidad del campo.
   - El script de aceptación saca las dos medidas lado a lado, para separar esas diferencias de los errores (decisión 7).
3. **Los mockups aprobados no cubren todo lo que la etapa tiene que mostrar.**
   - Faltan cinco cosas:
     - el aviso de tarea sin Unidad sugerida;
     - dónde cambia el Admin el Umbral y el Mes de corte;
     - la hora de lectura del campo, con "Volver a leer";
     - la Nota de crédito en la Precarga: no tiene "Factura que corrige", que la E2 exige;
     - la Precarga en modo edición.
   - Por la regla del usuario (interfaz nueva: mockup y opinión antes de construir), van a un boceto con OK antes de los pasos visuales (F0).
4. **El mockup de la Precarga exige el PDF para guardar**: su "Falta para guardar" incluye "El PDF.".
   - La E2 deja guardar sin PDF, y la API no cambia.
   - Guardar y adjuntar siguen siendo dos llamadas. Si la segunda falla, el Comprobante queda guardado sin PDF y el mes lo marca Falta comprobante (riesgo 9, pregunta 5).
5. **"Antes del corte, sin sumas" (D6) choca con el mockup**, que muestra los números de esas filas y los suma en el TOTAL (pregunta 2).
6. **El cuadro "Falta comprobante" del mockup cuenta facturas en el texto y filas en el código.** El plan cuenta filas (mes y Cliente), como los otros dos cuadros, porque el plan §3.4 dice que se cuentan "cada Alerta por separado".

## 1. Qué se pide

Construir la etapa 3 de Facturación:
- **El Resumen**: una fila por mes y Cliente, con lo trabajado, lo facturado y el Estado del mes.
- **El Detalle**: el Cruce de una fila, tarea por tarea, hasta los partes del campo. Incluye la Revisión de diferencia.
- **El Umbral y el Mes de corte**, que cambia sólo el Admin.
- **El aviso de tareas facturables sin Unidad sugerida.**
- **La Precarga**: arma la factura con lo trabajado, el Período facturado, la Fecha de carga y el Precio sugerido.

Se da por buena cuando se cumplen dos condiciones:
- el Cruce coincide con Power BI en los meses cerrados, salvo lo explicado en la §4;
- una factura del mes pasado se carga desde el Resumen.

## 2. Qué encontré en el código

### 2.1 Lo que ya existe y sirve

**Backend**

- **`app/modulos/facturacion/permisos.py`**
  - Declara cinco pantallas: `pendientes`, `cruce`, `comprobantes`, `equivalencias` y `panel`.
  - Sólo `comprobantes` tiene rutas: 12, fijadas en `tests/facturacion/test_mapa_permisos.py:35-53` y `:88-89`.
  - `requiere_admin()` (`app/core/permisos.py:77-89`) vale como requisito de ruta: `_normalizar` de ese test acepta `"admin"`.
- **`models.py`**
  - `Comprobante.fecha` es Date y nullable.
  - `LineaComprobante.fecha` es NOT NULL ("el 1 o el 16") y tiene el índice `ix_facturacion_linea_tarea_fecha`.
  - Los importes se guardan positivos; el signo sale del tipo.
- **`services/comprobantes_service.py`**
  - El alta exige la fecha de cabecera (`:450-451`).
  - Cada Línea guarda su fecha (`:575`) y exige cantidad > 0 (`:555-556`).
  - El `mes` del listado sale de la primera Línea (`_fila`, `:400-420`).
- **`services/consulta_externa.py` (Facturación)**
  - Tiene caché de 10 minutos (`_cacheado`, `:98-117`, que no guarda errores) para clientes, fincas y empresas.
  - `obtener_tareas` no tiene caché, y la usa la validación del alta.
  - `_reloj()` es monotónico: sirve para vencer la caché, no para mostrar una hora.
- **`services/historico.py`**
  - `SIN_NUMERO_FACTURADO_HASTA` está en `:240`.
  - La firma de la Línea incluye su fecha.
  - `conciliar` (`:976-984`) agrega lo facturado en Python por mes, de forma portable entre SQLite y MySQL.
- **Partes del campo.** `QUERY_PRINCIPAL` de Preliquidación (`app/modulos/preliquidacion/services/consulta_externa.py:18-205`) tiene las tres planillas que lee Power BI y la cosecha:

  | Rama | Líneas |
  |---|---|
  | Pulverización, tractor 1 | `:21-54` |
  | Pulverización, tractor 2 | `:58-90` |
  | Maquinaria | `:94-129` |
  | Tareas manuales | `:133-164` |
  | Cosecha | `:167-205` |

  - Terceros valida los varchar con REGEXP antes de convertir (`app/modulos/terceros/services/consulta_externa.py:299-301` y `:347-348`).
  - En pulverizadas, `unidades` viene vacía (`:303-305`).
- **Para "quién":** `Usuario.nombre` (`app/core/models.py:39`).
- **`scripts/refrescar_testing.py:52-63`**
  - No copia las tablas de Facturación, pero sí copia `rol_permiso`.
  - `tests/core/test_refrescar_testing.py` sólo controla que su lista exista en el modelo: no hay que tocarlo.

**Front**

- **`rutas.jsx`**
  - Tiene tres rutas de la pantalla `comprobantes`.
  - La regla de orden está en `:25-26`: la primera entrada del menú es donde aterriza la Tarjeta.
- **`listado.js`:** `textoMes` (`:55-60`) y `delMesMasNuevo` (`:25`, no exportada).
- **Fecha por Línea**
  - `GrillaLineas.jsx` tiene Fecha y Finca por Línea.
  - `formulario.js` y `lineas.js` exigen la fecha (`formulario.js:183`, `lineas.js:64-65`) y la mandan (`formulario.js:231` y `:237`).
- **`pages/Comprobante.jsx`**
  - Tiene `Vista` (`:140-174`) y `Formulario` (`:211`).
  - Quien puede Editar abre directamente el formulario.
- **Núcleo**
  - `FiltrosBar`: sus opciones en cascada sólo comparan valores escalares (`src/core/ui/opcionesCascada.js`).
  - `EncabezadoOrdenable` (`src/core/ui/TablaOrdenable.jsx:7`), para tablas con fila de totales.
  - `ordenarFilas` (`src/core/ui/ordenarFilas.js:9`).
  - `CargandoContenido`, `CargandoOverlay` (`src/core/ui/CargandoOverlay.jsx`), `useEstadoPantalla`, `puedeVer` y `puedeEditar`.
  - `esAdmin` es local, en `src/core/permisos.js:7`.
- **Tests:** `npm test` sólo toma `src/modulos/facturacion/*.test.js` (`package.json:11`). La lógica nueva va en la raíz del módulo.

### 2.2 Lo que hay que crear

**Backend**
- `fechas.py`
- `services/cruce.py`, puro
- `services/precios.py`
- `services/resumen_service.py`
- `services/precarga_service.py`
- `api/resumen.py`
- Tres modelos: configuración, Revisión y sus tareas.
- Migraciones `004`, `005` y `006`.
- `scripts/cruce_facturacion.py`

**Front**
- Lógica en la raíz del módulo: `periodo.js`, `estados.js`, `resumen.js`, `detalle.js` y `precarga.js`.
- Servicio: `services/resumen.js`.
- Páginas: `Resumen.jsx`, `Detalle.jsx` y `Precarga.jsx`.
- Componentes chicos.

### 2.3 Convenciones que el cambio respeta

- **ADR-0013.** El SQL del campo se copia de Preliquidación, no se importa. El núcleo no cambia, así que no hay PR del núcleo.
- **GUIA-MODULOS.**
  - Una pantalla nueva no entra en los roles que ya existen (`:372`).
  - Una pantalla retirada no se reutiliza, y sus permisos se borran con una migración después del deploy (`:374`).
  - Reglas 9 a 12: migración, `ORDEN.txt`, idempotencia o aviso, primero `testing`.
  - Regla 15: `detail` como `{tipo, mensaje}`.
  - Regla 16: schemas.
  - Regla 21: overlay, carga y toast.
- **Migraciones.** Con el formato de `facturacion/002` y `003`, y la vuelta atrás comentada sin `;` (`tests/facturacion/test_migracion.py:50-56`).
- **Tests.**
  - De API: con `app.dependency_overrides` y `_persona` (`tests/facturacion/test_api_comprobantes.py:177-193`).
  - De modelo: SQLite en memoria (`tests/facturacion/test_modelo_comprobantes.py:25-37`).
  - Del campo: `SesionFalsa` (`tests/terceros/test_consulta_externa.py:25-49`).
  - Datos ficticios siempre: nunca nombres reales.
- **Front.** CSS Modules con los tokens de `src/index.css`, sin dependencias nuevas, React Query y los servicios en `services/`. Textos en español, sin emojis.

## 3. Pasos

### 3.1 Decisiones

**Decisión 1. Claves de pantalla**

Recomendación:
- `PANTALLAS` queda así, en este orden:
  - `resumen`, Resumen, editable: Editar es dejar o deshacer una Revisión;
  - `comprobantes`;
  - `equivalencias`;
  - `panel`, sólo Ver.
- `pendientes` y `cruce` se retiran como se retiró `unidad`: salen de `PANTALLAS` y del glosario, y su clave no se reutiliza nunca.
- Sus permisos guardados se borran con `facturacion/005`, después del reinicio, igual que la `002`.
- No se copian a `resumen`, porque GUIA-MODULOS:372 lo prohíbe. El admin suma Resumen al rol de las contadoras al asignarlo (aviso en F7).
- Dependencias nuevas en `permisos.py`:
  - `ver_resumen`;
  - `editar_resumen`;
  - `editar_configuracion = requiere_admin()`, definida una sola vez, como `DEP_ADMIN` en `app/core/administracion.py:30`.

Porqué: Resumen reemplaza a las dos (plan §3.7). Si una clave retirada se reutilizara, un rol con permisos viejos ganaría la pantalla nueva.

Descartado:
- Reutilizar `pendientes`: rompe GUIA-MODULOS:374.
- Dejar las claves sin rutas: el editor de roles mostraría pantallas que no existen.
- Copiar los permisos en la migración: contradice `:372`.

**Decisión 2. Período facturado**

Recomendación:
- **Columnas nuevas.** `facturacion_comprobante.periodo_desde` y `periodo_hasta`, DATE NULL, con la `facturacion/006`.
- **`facturacion_linea.fecha` se queda**, NOT NULL y con su índice, y pasa a ser la fecha en la que cuenta la Línea:
  - en un Comprobante cargado a mano, el servicio la iguala a `periodo_desde`;
  - en un histórico, sigue siendo la fecha a facturar de la planilla.
- **`Comprobante.fecha` pasa a ser la Fecha de carga.**
  - En el alta la pone `hoy()`; en la edición no cambia.
  - La entrada de la API deja de traerla, y las Líneas también.
- **Los ya cargados a mano.** La 006 les pone como período el mes de su primera Línea, del día 1 al último.
  - Antes, un pre-check confirma que ninguno tenga Líneas en dos meses.
  - En producción se espera que no haya ninguno: la Factura de prueba se borró el 2026-10-13.
- **Los históricos quedan sin Período (NULL).**
  - Cada Línea cuenta en el mes de su fecha, como en la planilla y en Power BI. Un histórico con Líneas en varios meses cuenta cada una en su mes.
  - No cambian `historico.py` (`_firma_de_linea`, `_cambio`, `aplicar`, `conciliar`) ni `--reemplazar-cambiados`.

Porqué: el Cruce, el listado y la conciliación siguen leyendo una sola columna, sin ramas por tipo. El cambio de esquema es aditivo, y la vuelta atrás es borrar dos columnas.

Descartado:
- **Borrar la fecha de la Línea.** Los históricos con varios meses no tendrían dónde contar, y cambiarían `conciliar` y la firma.
- **Fecha nullable más COALESCE.** Pide otro ALTER sobre datos y crea dos caminos en cada consulta.
- **Usar `creado_en` como Fecha de carga.** Está en UTC y tiene hora; además, en los históricos es la fecha de la migración.

**Decisión 3. Una tarea facturada en dos unidades en el mismo mes**

Recomendación:
- **En el Detalle**, una fila por (tarea, unidad), cada una contra la Cantidad del campo de su unidad, con la marca "en 2 unidades". Cada fila se mide contra el Umbral por separado.
- **En el Resumen**, la tarea suma en la columna de cada unidad.
- **Plantas y hectáreas** leen la misma medida: lo esperable es que alguna supere. El mes queda Con diferencia y se resuelve con una Revisión, que guarda (tarea, unidad).

Porqué: no esconde nada ni inventa un reparto.

Descartado:
- Una sola fila con la unidad de mayor importe: esconde la otra.
- Prorratear: adivina.

**Decisión 4. Umbral y Mes de corte**

Recomendación:
- **Dónde se guardan.** Tabla `facturacion_configuracion` de una sola fila (id 1), con `umbral_pct` DECIMAL(5,2), `mes_corte` DATE (día 1), `actualizado_en` y `actualizado_por`.
  - Nace vacía en la 004.
  - Sin fila, el servicio usa los valores iniciales de `config.py`: 5 % y octubre de 2026.
  - El primer cambio crea la fila.
- **Dónde se cambian.** En el pie del Resumen, donde `pantallas.md:52` ya pone el mes de corte, el Umbral y que la cosecha no entra.
  - Sólo el Admin ve "Cambiar". El front lo decide con `usuario?.rol === 'admin'`, como el núcleo.
  - "Cambiar" abre un formulario chico en el mismo pie.
- **API.** `PUT /api/facturacion/configuracion` con `requiere_admin()`, y el backend manda. No hay GET aparte: el Resumen y el Detalle traen los dos valores.
- **Validaciones** (si fallan, 422 `configuracion_invalida` con `campo`):
  - Umbral mayor que 0 y hasta 100, con dos decimales como máximo;
  - Mes de corte no posterior al mes en curso.

Descartado:
- Variables de entorno: las cambia quien deploya, no el Admin.
- Una tabla clave-valor: no tiene tipos.
- Una pantalla o clave nueva.
- La Administración del núcleo: el núcleo no conoce módulos.
- Una semilla en la migración: habría dos lugares con los valores iniciales.
- Exportar `esAdmin` del núcleo: abre un PR del núcleo por una línea.

**Decisión 5. Aviso de tarea sin Unidad sugerida**

Recomendación:
- **Dónde va.** Un banner warn sobre la tabla del Resumen, debajo de los cuadros y de la barra.
- **Qué dice.** "N tareas facturables sin Unidad sugerida tuvieron trabajo en el período", más un desplegable con cada tarea y en cuántos Clientes, y "Se definen en la app de campo".
- **No es una Alerta:** no entra en los cuadros ni en el Estado.
- **En el Detalle,** esas tareas dicen "Sin Unidad sugerida". En la Precarga, la Unidad queda vacía y marcada.

Porqué: es un problema del maestro, no de un mes y un Cliente. Por fila, el mismo aviso se repetiría.

Descartado:
- Una cuarta Alerta: cambia los estados cerrados en D8.
- El pie: no se ve.

Va al boceto F0.

**Decisión 6. El dato del Cruce**

- **Consulta base.** Va en `consulta_externa.py` de Facturación, con una fila por (parte, tarea), copiada de las ramas de `QUERY_PRINCIPAL`:
  - pulverización, sólo tractor 1 (`trancadas1`, `hsjornal1`, `hsmaquina1`), con `unidades` de la cabecera una sola vez (MAX);
  - maquinaria y tareas manuales, con SUM por cabecera y tarea.
  - Sin cosecha y sin la rama del tractor 2.
  - Las cuatro medidas pasan por el cast REGEXP de Terceros.
  - `estado <> 9` en cabecera y en registro.
  - El rango es semiabierto y sin `DATE()` en el filtro: `fecha >= :desde AND fecha < :hasta_exclusivo`. La hora 03:00 queda adentro.
  - El supervisor sale con el mismo join de cada rama de `QUERY_PRINCIPAL` (`:51`, `:119-120` y `:161-162`).
  - "Dónde" es el nombre de la finca del parte (pregunta 14).
- **Dos lecturas sobre esa base:**
  - **`trabajado_por_mes(desde, hasta)`:** GROUP BY cliente, tarea, año y mes, con las sumas y la cantidad de partes. La usa el Resumen.
  - **`partes_de_cliente(cliente_id, desde, hasta)`:** un parte por fila. La usan el Detalle, sumando en Python para que el panel dé igual que la columna, y la Precarga, que suma la quincena.
- **Caché**, con `_cacheado` y 10 minutos:
  - las claves son `("trabajado", desde, hasta)`, `("partes", cliente_id, desde, hasta)` y `("tareas_cruce",)`; esta última envuelve `obtener_tareas(incluir_baja=True)`, así la validación de la E2 no cambia;
  - cada valor guarda la hora de lectura (UTC), que se devuelve como `leido_en`;
  - `invalidar_cache_cruce()` borra sólo esas claves;
  - los GET aceptan `refrescar=true`;
  - lo facturado, los adjuntos y las Revisiones se leen siempre frescos de la base propia.
- **Rango del Resumen.** Hasta 12 meses, sin pasar el mes en curso. Si no, 422 `rango_invalido`. Arranca en el mes pasado.
- **Lo facturado.** Las Líneas de la base propia, agregadas en Python como `conciliar`:
  - **Fuera:**
    - los históricos `pendiente_de_facturar`;
    - las unidades de cosecha;
    - las tareas No facturable.
  - **Las Notas de crédito** restan cantidad e importe.
- **Motor puro `cruce.py`**
  - **Medida por unidad:**

    | Unidad | Medida del campo |
    |---|---|
    | `horas_peon` | horas de jornal |
    | `horas_tractor` | horas de máquina |
    | `plantas` | unidades |
    | `hectareas` | unidades |
    | `tancadas` | tancadas |

  - **Unidad de la fila:** la de lo facturado en el mes; si no hay, la sugerida; si tampoco hay, ninguna.
  - **Fuera del Cruce:** las tareas No facturable, y las de sugerida de cosecha sin facturado.
  - **Supera:**

    | Partes | Campo en su unidad | Facturado | Supera |
    |---|---|---|---|
    | cualquiera | > 0 | cualquiera | sí, si \|facturado − campo\| / campo > Umbral (estricto) |
    | sí | 0 o sin unidad | 0 | sí, porque D2 dice "trabajada y no facturada" (pregunta 4) |
    | cualquiera | 0 o sin unidad | distinto de 0 | sí |
    | no | — | 0 | no hay fila |

    El % es "—" si el campo es 0.
- **Estados del mes**, en orden de urgencia:

  | Situación | Estado |
  |---|---|
  | Mes anterior al corte | `antes_del_corte`, solo |
  | Mes en curso | `mes_en_curso`, más `falta_comprobante` si corresponde |
  | Hay partes facturables y ninguna Línea cuenta | `pendiente_de_facturar`, solo |
  | Alguna fila supera y no la cubre la Revisión vigente | `con_diferencia` |

  - `falta_comprobante`: un Comprobante a mano con alguna Línea que cuenta en el mes y sin Adjuntos.
  - Sin nada de lo anterior, `facturada`.
  - En los meses que no se controlan, `supera` es falso.
- **Revisión vigente:** la más reciente del (Cliente, mes) que no fue deshecha. Con S, las filas que superan, y T, las que guardó la vigente:
  - si S está incluido en T y no está vacío, `diferencia_revisada` y Facturada;
  - si alguna fila de S no está en T, Con diferencia;
  - si S está vacío, Facturada, y la Revisión queda en el registro.
- **Pesos del Detalle.**
  - Precio de cada (tarea, unidad): Σimporte / Σcantidad de las Facturas del mes. Si no hay, el Precio sugerido. Si tampoco hay, la fila queda sin valorizar.
  - TOTAL:
    - campo valorizado;
    - facturado, que es el neto real;
    - diferencia y %;
    - "N tareas sin precio".
- **`hoy()`** va en `fechas.py`, en UTC-3 fijo.

Descartado:
- Una sola consulta de partes para el Resumen: decenas de miles de filas en 12 meses.
- Caché por mes: más consultas y más lógica.
- `DATE(x) BETWEEN`: no puede usar un índice.
- `date.today()`: no se conoce el huso del VPS.
- `zoneinfo`: pide `tzdata`, una dependencia nueva.

**Decisión 7. Aceptación contra Power BI**

- **Script de sólo lectura `scripts/cruce_facturacion.py`**, contra `testing`, que tiene los históricos migrados.
  - Escribe un CSV en `docs/modulos/facturacion/fuentes/`, que está fuera de git (`.gitignore:10-12`).
  - Una fila por Cliente, mes, tarea y unidad, con:
    - grupo;
    - unidad sugerida;
    - medida "como Power BI": la medida de la unidad sugerida;
    - medida del módulo: la de la unidad de la fila;
    - cantidad facturada;
    - neto.
  - Avisa que la salida tiene nombres de clientes y que nunca se pega en PRs, chats ni en la bitácora.
- **El usuario** compara los meses cerrados que elija y anota cada diferencia con su causa:
  - unidad facturada distinta de la sugerida;
  - tractor;
  - `unidades` de pulverización;
  - No facturable o sin unidad;
  - sugerida del campo distinta de la de Power BI;
  - otra causa. Esta última es un error y frena el PR.
- **Lo confirmado** va a la §4, sin valores ni nombres (A12).

Descartado: comparar dentro de la app. Mostraría una medida que el producto no usa.

### 3.2 Contrato de la API

**Errores.**
- Formato: `{tipo, mensaje}`, con `campo` donde aplica.
- Si el campo no responde, 503: lo traduce `traducir_errores_externa`, como ya pasa en `_ejecutar`.
- 404: como en la E2, con `detail` de texto.

**Rutas nuevas**, numeradas a continuación de las 12 de la E2:

| # | Ruta | Exige | Etapa |
|---|---|---|---|
| 13 | `GET /api/facturacion/resumen?desde=AAAA-MM&hasta=AAAA-MM[&refrescar=true]` | `resumen`, ver | E3a |
| 14 | `GET /api/facturacion/resumen/{cliente_id}/{mes}[?refrescar=true]` | `resumen`, ver | E3a |
| 15 | `POST /api/facturacion/resumen/{cliente_id}/{mes}/revision` | `resumen`, editar | E3a |
| 16 | `DELETE /api/facturacion/resumen/{cliente_id}/{mes}/revision` | `resumen`, editar | E3a |
| 17 | `PUT /api/facturacion/configuracion` | admin | E3a |
| 18 | `GET /api/facturacion/precarga?cliente_id=&desde=AAAA-MM-DD&hasta=AAAA-MM-DD` | `comprobantes`, editar | E3b |

**13. Resumen**
- Respuesta: `{umbral_pct, mes_corte, mes_en_curso, leido_en, filas, tareas_sin_unidad, actualizado_en, actualizado_por_nombre}` (los dos últimos, `null` si nadie cambió la configuración; A10b).
- Cada fila trae:
  - `cliente_id`, `cliente_nombre` y `mes`;
  - `horas_peon`, `horas_tractor`, `tancadas`, `plantas`, `hectareas` y `facturado_neto`, como texto decimal; el neto, con signo;
  - `estados`: claves ordenadas por urgencia;
  - `diferencia_revisada`;
  - `comprobantes_sin_adjunto`: `[{id, tipo, numero}]`.
- Claves de estado: `pendiente_de_facturar`, `con_diferencia`, `falta_comprobante`, `facturada`, `mes_en_curso` y `antes_del_corte`.
- `tareas_sin_unidad`: `[{tarea_id, nombre, clientes}]`.
- Orden de las filas: mes descendente, urgencia, Cliente.
- Errores: 422 `rango_invalido` (con `campo`) y 422 `mes_invalido`.

**14. Detalle**
- Respuesta:
  - `cliente_id`, `cliente_nombre`, `mes`, `umbral_pct`, `mes_corte` y `leido_en` (`mes_corte` lo pide el aviso "Antes del corte" del boceto aprobado; sumado al ejecutar FA4);
  - `estados`, `diferencia_revisada` y `se_puede_revisar`;
  - `comprobantes`;
  - `grupos`;
  - `total`;
  - `revision`.
- `comprobantes`: `[{id, tipo, numero, cantidad_adjuntos, es_historico}]`, todos los que tienen alguna Línea en el mes.
- `grupos`: `[{grupo, tareas}]`. Una tarea sin grupo va en "Sin grupo".
- Cada tarea trae:
  - `tarea_id` y `tarea_nombre`; si la tarea no está en el maestro, el nombre se copia de la Línea;
  - `unidad` y `sin_unidad_sugerida`;
  - `en_varias_unidades`;
  - `campo` (null si no tiene unidad) y `facturado`;
  - `diferencia`, `diferencia_pct` y `supera`;
  - `precio`;
  - `partes`: `[{fecha, donde, supervisor, cantidad}]`.
- `total`: `{campo_pesos, facturado_pesos, diferencia_pesos, diferencia_pct, tareas_sin_precio}`.
- `revision`: la vigente (o null), con `{id, comentario, creada_en, creada_por_nombre, tareas: [{tarea_id, tarea_nombre, unidad}]}`.
- Errores: 404 si el Cliente no está en el maestro (con baja) y no tiene Comprobantes; 422 `mes_invalido`.

**15. Dejar una Revisión**
- Body: `{comentario}`.
- 201 con el Detalle.
- Errores:
  - 422 `revision_invalida`, campo `comentario`: vacío o de más de 500;
  - 409 `no_revisable`, con un mensaje según el estado;
  - 404.

**16. Deshacer la Revisión**
- 200 con el Detalle.
- 409 `sin_revision`.

**17. Configuración**
- Body: `{umbral_pct, mes_corte: "AAAA-MM"}`.
- 200 con `{umbral_pct, mes_corte, actualizado_en, actualizado_por_nombre}`.
- 422 `configuracion_invalida`, con `campo`.

**18. Precarga**
- Respuesta: `{cliente_id, cliente_nombre, empresa_sugerida, leido_en, trabajado, precios}`.
- `trabajado`: cada tarea con partes en el período, con:
  - `tarea_id`, `tarea_nombre` y `grupo_tarea`;
  - `unidad_sugerida` y `no_facturable`;
  - `campo: {horas_peon, horas_tractor, plantas, hectareas, tancadas}`.
- `precios`: `[{tarea_id, unidad, precio_unitario, comprobante_id, numero, fecha}]`.
  - Sale de la última Factura del Cliente por cada (tarea, unidad): mes de la Línea descendente, después `fecha` descendente, después id descendente.
  - Los históricos cuentan. Las Notas de crédito y los `pendiente_de_facturar` no.
- `empresa_sugerida`: la de la última Factura del Cliente que tiene empresa.
- Error: 422 `periodo_invalido`, con `campo`, si falta el período, si desde es posterior a hasta o si cruza de mes.

**Cambios en la E3b a las rutas que ya existen**
- `POST` y `PUT /comprobantes`:
  - sin `fecha` en la cabecera ni en las Líneas;
  - con `periodo_desde` y `periodo_hasta`.
  - 422 `comprobante_invalido`:
    - campo `periodo_desde`: "Falta el período facturado.";
    - campo `periodo_hasta`: "El período tiene que quedar dentro de un mismo mes.".
- La Fila y el Detalle suman `periodo_desde` y `periodo_hasta`, que vienen en null en un histórico.
- El Detalle suma `creado_por_nombre`.
- **Es un cambio de contrato:** el front de la E3a no guarda contra el backend de la E3b. Se deployan en la misma ventana.

### 3.3 Corte en PRs y orden

1. **BK-E3a y FT-E3a, hermanos.**
   - Incluyen:
     - claves;
     - fechas;
     - el modelo y las migraciones `004` y `005`;
     - la lectura del Cruce y el motor;
     - el Resumen, el Detalle y la Revisión;
     - la configuración y el aviso;
     - el Precio sugerido, que se usa para valorizar;
     - el script de aceptación;
     - las pantallas Resumen y Detalle.
   - Se mergea el BK y después el FT. El deploy (F7) va con OK.
2. **BK-E3b y FT-E3b, hermanos**, en una rama nueva desde `main` (F8).
   - Incluyen:
     - el Período facturado y la `006`;
     - la Fecha de carga;
     - la ruta 18;
     - la Precarga;
     - la vista del Comprobante;
     - los botones nuevos de Comprobantes.
   - Se mergea el BK y después el FT. El deploy (F13) va con los dos en la misma ventana.
3. **Sin PR del núcleo.**

Por qué se parte:
- Las dos condiciones de aceptación son independientes.
- La E3a sólo agrega cosas (tablas nuevas y rutas nuevas); la E3b concentra el cambio de contrato y el único ALTER sobre datos.
- La comparación con Power BI puede empezar apenas la E3a está en `testing`.
- Cada PR queda revisable en dos rondas.

Descartado:
- Un solo par: demasiado grande, y mezcla el ALTER con lo de sólo lectura.
- Tres pares: la Revisión es chica y está atada a los estados.

### 3.4 BK-E3a

**A0. Docs (sin test)**
- **Archivos:**
  - `docs/modulos/facturacion/plan-facturacion.md`
  - `docs/modulos/facturacion/pantallas.md`
  - `docs/modulos/facturacion/CONTEXT-facturacion.md`
- **Qué:**
  - **plan-facturacion:**
    - separar el ítem pegado en las líneas 270 y 271;
    - §3.3, líneas 132 y 133: decisión 3;
    - §3.7, líneas 220 a 227: decisiones 1 y 4;
    - §7, líneas 268 a 271: sacar lo resuelto (dónde va el Umbral y el Período de los existentes) y dejar Excel;
    - §3.1, línea 82: la finca según la pregunta 13;
    - §5, fila 3: "partida en E3a y E3b".
  - **pantallas.md:**
    - "Abierto", líneas 123 a 129: queda sólo Excel;
    - Resumen: el aviso (decisión 5) y el pie con "Cambiar", en la línea 52;
    - línea 112;
    - Precarga: la Nota de crédito y el modo edición, según F0.
  - **Glosario:**
    - Línea (74 a 77): en un histórico, que no tiene Período, cada Línea cuenta en el mes de su fecha;
    - Comprobante histórico (85 a 90);
    - Fecha de carga de un histórico (pregunta 8);
    - Umbral y Mes de corte: "se cambian desde el pie del Resumen".
- **Verificación:**
  - un grep de "lo decide el plan de la etapa 3" y "lo decide la etapa 3" no devuelve nada;
  - el diff no tiene nombres ni valores.

**A1. Par: claves de pantalla** (zona sensible: dos rondas)
- **Archivos:**
  - `app/modulos/facturacion/permisos.py`
  - `tests/facturacion/test_registro_y_permisos.py`
  - `tests/facturacion/test_api_comprobantes.py:191-192`: la persona `OTRA_PANTALLA` pasa de `pendientes` a `resumen`.
- **Rojo:**
  - el catálogo tiene 4 pantallas, en el orden de la decisión 1;
  - `resumen` es editable y `panel` no;
  - `pendientes`, `cruce` y `unidad` no están;
  - `/api/auth/modulos` publica las 4.
- **Verde:**
  - `PANTALLAS`;
  - las tres dependencias;
  - un comentario con las claves retiradas y la fecha.
- **Verificación:** `python -m pytest -q tests/facturacion/test_registro_y_permisos.py tests/facturacion/test_api_comprobantes.py tests/core/test_endpoints_con_permiso.py`

**A2. Par: fechas**
- **Archivos:**
  - `app/modulos/facturacion/fechas.py` (nuevo)
  - `tests/facturacion/test_fechas.py` (nuevo)
- **Rojo:**
  - `hoy()` en UTC-3: a las 02:00 UTC del día 1 todavía es el último día del mes anterior. Los tests reemplazan `_ahora()`, como `_reloj()`.
  - `leer_mes("2026-09")` da el 1 de septiembre de 2026.
  - "2026-13", "2026-9" y "x" dan error.
  - `fin_de_mes`, `mes_siguiente` y `meses(desde, hasta)` (inclusivo, cruzando el año).
  - `mismo_mes`.
- **Verde:** la implementación.
- **Verificación:** `python -m pytest -q tests/facturacion/test_fechas.py`

**A3. Par: modelo y migraciones 004 y 005** (zona sensible: dos rondas)
- **Archivos:**
  - `app/modulos/facturacion/models.py`
  - `migrations/facturacion/004_resumen.sql` (nuevo)
  - `migrations/facturacion/005_borrar_pendientes_y_cruce.sql` (nuevo)
  - `migrations/ORDEN.txt`
  - `migrations/facturacion/LEEME.md`
  - `tests/facturacion/test_migracion.py`
  - `tests/facturacion/test_modelo_resumen.py` (nuevo)
- **Modelos:**
  - **`Configuracion`** (`facturacion_configuracion`):
    - `id` PK;
    - `umbral_pct` DECIMAL(5,2) NOT NULL;
    - `mes_corte` DATE NOT NULL;
    - `actualizado_en` NOT NULL;
    - `actualizado_por` FK a `usuarios`, SET NULL.
  - **`RevisionDiferencia`** (`facturacion_revision`):
    - `cliente_id` y `mes` (DATE, día 1);
    - `comentario` VARCHAR(500);
    - `creada_en` y `creada_por`;
    - `deshecha_en` y `deshecha_por`;
    - índice `(cliente_id, mes)`;
    - relación `tareas` con cascade delete-orphan.
  - **`RevisionTarea`** (`facturacion_revision_tarea`):
    - `revision_id`, FK con CASCADE;
    - `tarea_id`;
    - `unidad`, NULL y con el largo de `LineaComprobante.unidad`.
- **004:**
  - tres `CREATE TABLE IF NOT EXISTS`, con el motor, el charset y la collation de la 003;
  - "NO DIFERIBLE": se aplica antes del reinicio, porque el arranque compara modelo y base; es idempotente;
  - vuelta atrás comentada, una tabla por línea y sin `;`. Se borran en este orden:
    1. `facturacion_revision_tarea`;
    2. `facturacion_revision`;
    3. `facturacion_configuracion`.
- **005:**
  - `DELETE FROM rol_permiso WHERE modulo = 'facturacion' AND pantalla IN ('pendientes', 'cruce')`;
  - "NO DIFERIBLE": se aplica después del reinicio; es idempotente;
  - deja escrita la excepción a la regla 6, como la 002;
  - vuelta atrás: reinsertar las filas del respaldo de F1 y F7.
- **Rojo:**
  - la 004 y la 005 entran en el parámetro de los `;` (`test_migracion.py:50-56`);
  - las sentencias de la 005 son exactamente el DELETE;
  - las dos dicen "-- NO DIFERIBLE";
  - en `ORDEN.txt`, la 004 va después de la 003 y la 005 después de la 004;
  - las columnas de cada `CREATE TABLE` de la 004 son las del modelo, con el patrón de `tests/core/test_migracion_roles.py:26` y `:71-84`;
  - en SQLite:
    - una Revisión con dos tareas se lee de vuelta;
    - borrarla borra sus tareas;
    - la configuración con id 1 persiste.
- **Verde:** los modelos, los `.sql`, `ORDEN.txt`, un renglón por migración en el `LEEME.md` y el docstring del test.
- **Verificación:** `python -m pytest -q tests/facturacion/test_migracion.py tests/facturacion/test_modelo_resumen.py tests/core`

**A4. Par: lectura del campo para el Cruce**
- **Archivos:**
  - `app/modulos/facturacion/services/consulta_externa.py`
  - `tests/facturacion/test_consulta_externa_cruce.py` (nuevo)
- **Rojo**, con `SesionFalsa`:
  - el SQL tiene las tres ramas de la decisión 6;
  - no aparecen la planilla de cosecha, `trancadas2`, `hsjornal2` ni `hsmaquina2`;
  - no hay `DATE(` en el filtro;
  - las cuatro medidas pasan por REGEXP;
  - el parámetro `hasta_exclusivo` es el primer día del mes siguiente;
  - una segunda llamada dentro de los 10 minutos no consulta, y con `_reloj` adelantado 600 segundos sí;
  - `invalidar_cache_cruce()` no borra clientes ni empresas;
  - `leido_en` es la hora de la lectura y no la de la llamada;
  - un None se lee como 0.
- **Verde:** las consultas y los tres métodos de la decisión 6.
- **Verificación:** `python -m pytest -q tests/facturacion/test_consulta_externa_cruce.py tests/facturacion/test_consulta_externa.py tests/facturacion/test_consulta_externa_comprobantes.py`. El SQL real recién corre en F4.

**A5. Par: motor del Cruce**
- **Archivos:**
  - `app/modulos/facturacion/services/cruce.py` (nuevo)
  - `tests/facturacion/test_cruce.py` (nuevo)
- **Rojo:**
  - **Medida por unidad:**
    - cada unidad compara su medida (la tabla de la decisión 6);
    - sin facturado se usa la sugerida;
    - facturado en otra unidad: se usa la de lo facturado.
  - **Dos unidades:** dos filas con `en_varias_unidades`.
  - **Qué entra:**
    - la cosecha y lo No facturable no entran;
    - una Nota de crédito resta.
  - **El Umbral:**
    - justo en el Umbral no supera;
    - apenas arriba sí;
    - para abajo, igual.
  - **Las filas de la tabla "Supera"**, incluida la tarea sin unidad (sin campo, supera y entra en `tareas_sin_unidad`).
  - **Columnas del Resumen:** suman por unidad, y una tarea sin unidad no suma.
  - **Estados:** todos los casos de la tabla de la decisión 6, más:
    - Pendiente de facturar y Facturada van solos;
    - mes en curso con falta;
    - Revisión que cubre;
    - una tarea nueva que supera;
    - ninguna supera.
- **Verde:** la implementación.
- **Verificación:** `python -m pytest -q tests/facturacion/test_cruce.py`

**A6. Par: servicio del Resumen y configuración**
- **Archivos:**
  - `app/modulos/facturacion/services/resumen_service.py` (nuevo)
  - `app/modulos/facturacion/config.py`: `UMBRAL_INICIAL`, `MES_CORTE_INICIAL`, `MESES_MAXIMOS = 12` y `LARGO_COMENTARIO = 500`
  - `tests/facturacion/test_resumen_service.py` (nuevo)
- **Rojo**, con SQLite y una `ConsultaFalsa` como la de `test_comprobantes_service.py:35-90`:
  - **Configuración:**
    - sin fila, da los iniciales;
    - después del cambio, da lo guardado;
    - errores de umbral (0, 100,01 y tres decimales) y de mes de corte futuro.
  - **Rango:**
    - más de 12 meses;
    - hasta antes de desde;
    - hasta después del mes en curso.
  - **Filas:**
    - pendiente, facturada y con diferencia;
    - antes del corte con números;
    - mes en curso;
    - falta comprobante: en uno a mano sí, en un histórico no;
    - un `pendiente_de_facturar` no factura;
    - un Cliente sin trabajo ni Comprobantes no aparece.
  - **Orden y aviso:** el orden de las filas y `tareas_sin_unidad` con su cantidad de Clientes.
  - **`refrescar`** invalida la caché del Cruce.
- **Verde:** lo facturado se lee con un `select` de Comprobante, Línea y cantidad de Adjuntos por rango de `LineaComprobante.fecha`, y se agrega en Python.
- **Verificación:** `python -m pytest -q tests/facturacion/test_resumen_service.py`

**A7. Par: Precio sugerido**
- **Archivos:**
  - `app/modulos/facturacion/services/precios.py` (nuevo)
  - `tests/facturacion/test_precios.py` (nuevo)
- **Rojo:**
  - gana la última Factura del mismo Cliente, por la tarea y la unidad;
  - las Notas de crédito, los `pendiente_de_facturar` y los otros Clientes no cuentan;
  - los históricos sí cuentan;
  - el desempate sigue el orden de la ruta 18;
  - la empresa sugerida es la de la última Factura con empresa.
- **Verde:** la implementación.
- **Verificación:** `python -m pytest -q tests/facturacion/test_precios.py`

**A8. Par: Detalle**
- **Archivos:**
  - `resumen_service.py`
  - `tests/facturacion/test_detalle.py` (nuevo)
- **Rojo:**
  - el Campo de cada fila es la suma de sus partes en su unidad;
  - una tarea en dos unidades muestra sus partes en cada fila, con la medida de esa fila;
  - agrupa por grupo de tareas;
  - los pesos:
    - salen del precio medio de las Facturas del mes;
    - si no hay, del Precio sugerido;
    - si tampoco hay, cuentan en `tareas_sin_precio`;
  - la Revisión vigente trae `creada_por_nombre`;
  - los estados son los del Resumen para el mismo mes;
  - en Antes del corte y en Mes en curso, `supera` es falso;
  - el 404.
- **Verde:** la implementación.
- **Verificación:** `python -m pytest -q tests/facturacion/test_detalle.py`

**A9. Par: Revisión**
- **Archivos:**
  - `resumen_service.py`
  - `tests/facturacion/test_revision.py` (nuevo)
- **Rojo:**
  - **Comentario:**
    - obligatorio: sólo espacios da 422;
    - de más de 500, 422.
  - **Estados:** sobre pendiente, antes del corte, mes en curso o facturada, 409 `no_revisable`.
  - **Qué guarda:** quién, cuándo (con `ahora_utc` reemplazado) y las (tarea, unidad) que superaban.
  - **El efecto de una Revisión:**
    - queda Facturada y revisada;
    - si después supera una tarea nueva, vuelve a Con diferencia y se puede dejar otra Revisión, que pasa a ser la vigente;
    - si no supera ninguna, queda Facturada sin nota.
  - **Deshacer:**
    - deja el registro con `deshecha_*`;
    - el mes vuelve a Con diferencia;
    - deshacer sin una vigente, o dos veces, da 409.
- **Verde:** la implementación. Las tareas que superan se calculan con los mismos datos en caché que vio el Detalle.
- **Verificación:** `python -m pytest -q tests/facturacion/test_revision.py`

**A10. Par: router, schemas y mapa**
- **Archivos:**
  - `app/modulos/facturacion/api/resumen.py` (nuevo). Usa el mismo `get_consulta_externa` de `api/comprobantes.py`, así un override sirve para los dos.
  - `app/modulos/facturacion/schemas.py`
  - `app/modulos/facturacion/__init__.py`: suma el router.
  - `tests/facturacion/test_api_resumen.py` (nuevo)
  - `tests/facturacion/test_mapa_permisos.py`
- **Rojo:**
  - el mapa tiene las filas 13 a 17 y pasa a `test_la_tabla_tiene_las_17_rutas`;
  - **permisos:**
    - sin sesión, 401;
    - alguien que sólo tiene `comprobantes`, 403;
    - alguien con Editar en `resumen` que no es admin, 403 en la ruta 17;
  - **errores:**
    - 422 para `mes` "2026-13" y para un rango de 13 meses;
    - 422 y 409 de la Revisión con `{tipo, mensaje}`;
  - **respuestas:**
    - 201 en la ruta 15;
    - la forma de cada respuesta pasa por los schemas.
- **Verde:** las rutas, los schemas (regla 16) y la traducción de errores, como `_http` de `api/comprobantes.py`.
- **Verificación:** `python -m pytest -q tests/facturacion tests/core/test_endpoints_con_permiso.py tests/core/test_arquitectura.py`

**A11. Par: script de aceptación**
- **Archivos:**
  - `scripts/cruce_facturacion.py` (nuevo)
  - `tests/facturacion/test_script_cruce.py` (nuevo)
- **El script:**
  - argumentos `--desde AAAA-MM --hasta AAAA-MM`;
  - usa `trabajado_por_mes`, `cruce.py` y el lector de lo facturado del servicio, sin SQL propio;
  - sigue las convenciones de `scripts/migrar_historico_facturacion.py`: `RAIZ`, `SessionExterna`, `SessionPropia` y el aviso de nombres.
- **Rojo:**
  - las filas del CSV muestran la medida "como Power BI" y la del módulo;
  - la Nota de crédito resta;
  - la cosecha no entra;
  - una salida fuera de `fuentes/` se rechaza;
  - se imprime el aviso.
- **Verde:** la implementación.
- **Verificación:** `python -m pytest -q tests/facturacion/test_script_cruce.py`. La corrida real es F5.

**A12. Docs después de la aceptación (sin test)**
- **Archivos:** `plan-facturacion.md` §4, líneas 232 a 239.
- **Qué:**
  - el tractor confirmado;
  - las causas de diferencia encontradas, sin valores ni nombres.
- **Verificación:** leer el diff.

**A13. Suite completa**
- `python -m pytest -q` con las variables de 3.9.
- Todo verde, y la cuenta de tests es la de `main` más los nuevos.

### 3.5 FT-E3a

**FA0. Arranque de impeccable (sin test)**
- Correr `impeccable context --target src/modulos/facturacion/pages/Resumen.jsx` y después `--target src/modulos/facturacion/pages/Detalle.jsx`.
- Leer `reference/new-work.md` y `reference/craft-floor.md`.
- El brief es:
  - `pantallas.md` (Resumen y Detalle);
  - los mockups aprobados `Resumen.dc.html` y `Detalle.dc.html`, sin copiar sus datos de ejemplo;
  - el boceto aprobado en F0.
- **Verificación:** la checklist de craft-floor queda anotada para FA5 y FA6.

**FA1. Par: períodos del Resumen**
- **Archivos:**
  - `src/modulos/facturacion/periodo.js` (nuevo)
  - `periodo.test.js` (nuevo)
- **Rojo**, con `hoy` fijo:
  - los atajos: Mes pasado, Este mes, Últimos 3 meses y Este año;
  - en enero, el mes pasado es diciembre y "Este año" es sólo enero;
  - "Últimos 3 meses" cruza el año;
  - `rangoValido`: hasta antes de desde, más de 12 meses, después del mes en curso.
- **Verde:** la implementación.
- **Verificación:** `npm test`

**FA2. Par: estados**
- **Archivos:**
  - `estados.js` (nuevo)
  - `estados.test.js` (nuevo)
- **Rojo:**
  - el mapa clave → etiqueta, badge y orden, tomado de la tabla del mockup;
  - el estado más urgente;
  - la acción de cada fila:
    - "Cargar factura" lleva a `/facturacion/comprobantes/nuevo?tipo=factura&cliente=…&mes=…` y pide Editar en `comprobantes`; si no lo tiene, "Ver detalle";
    - "Ver diferencia";
    - "Adjuntar PDF" lleva al primer Comprobante sin Adjunto y pide Editar en `comprobantes`;
    - "Ver detalle", también en Antes del corte y en Mes en curso;
  - qué etiqueta es link:
    - Pendiente y Falta comprobante, sólo con permiso;
    - Con diferencia;
    - Facturada, Mes en curso y Antes del corte van como texto.
- **Verde:** la implementación.
- **Verificación:** `npm test`

**FA3. Par: filas, cuadros, filtros y totales**
- **Archivos:**
  - `resumen.js` (nuevo)
  - `resumen.test.js` (nuevo)
  - `listado.js`: exportar `delMesMasNuevo`.
- **Rojo:**
  - `filaDelResumen`;
  - `CAMPOS_RESUMEN`: Mes ordenado por fecha, Cliente y Estado;
  - `datosParaFiltros` repite cada fila por estado, para que las opciones en cascada del núcleo salgan bien sin tocar el núcleo;
  - `filtrarResumen`: una fila pasa si alguno de sus estados está elegido;
  - `contarAlertas` cuenta filas que pasan Mes y Cliente, sin aplicar el Estado ni la Alerta, así el número del cuadro no cambia al tocarlo;
  - `totales`.
- **Verde:** la implementación.
- **Verificación:** `npm test`

**FA4. Par: lógica del Detalle**
- **Archivos:**
  - `detalle.js` (nuevo)
  - `detalle.test.js` (nuevo)
- **Rojo:**
  - `textoPct`: "—" cuando viene null;
  - `bannerDeDetalle`, con cuatro casos:
    - revisada;
    - con diferencia y una Revisión anterior que no cubre;
    - con diferencia sin Revisión;
    - sin control;
  - `puedeRevisar`;
  - `validarComentario`: obligatorio y hasta 500;
  - `totalPartes`.
- **Verde:** la implementación.
- **Verificación:** `npm test`

**FA5. Visual: Resumen** (antes, F0 con OK)
- **Archivos nuevos:**
  - `services/resumen.js`, con las claves de React Query;
  - `pages/Resumen.jsx` y `Resumen.module.css`;
  - `components/CuadrosAlertas.jsx`, `EtiquetasEstado.jsx`, `SelectorMeses.jsx`, `AvisoSinUnidad.jsx` y `PieConfiguracion.jsx`, cada uno con su CSS.
- **`rutas.jsx`:**
  - `/facturacion/resumen` primero, en el menú, con la pantalla `resumen`;
  - `/facturacion/resumen/:clienteId/:mes`;
  - las `pantallas` del asistente;
  - el comentario de `:6-14` pasa a cuatro pantallas.
- **Comando:** lo de FA0 sobre `Resumen.jsx`.
- **Comportamiento:**
  - **Carga:**
    - `CargandoContenido` con "Leyendo lo trabajado en el campo…";
    - un error con Reintentar, como `Comprobantes.jsx:120-134`;
    - "Datos del campo de las HH:MM · Volver a leer", que vuelve a pedir con `refrescar=true`.
  - **Estado de la pantalla:** `useEstadoPantalla('facturacion.resumen.periodo' | '.filtros' | '.orden')`.
  - **Tabla:**
    - con `EncabezadoOrdenable`, `ordenarFilas` y un `<tfoot>` TOTAL fijo;
    - las filas de Mes en curso y Antes del corte van en gris;
    - "Nada con estos filtros" cuando no queda ninguna.
  - **Período:** el selector va en el lugar `quincena` de `FiltrosBar`, con `mostrarAlertas={false}` y `mostrarBusqueda={false}`. Los cuadros fijan `filtros.alerta`.
  - **Pie:** el formulario de configuración, con `CargandoOverlay` y toast. Al guardar invalida el Resumen.
- **Verificación:** `npm test`, `npm run build` y `npm run lint` sin errores nuevos. Smoke en F4.

**FA6. Visual: Detalle**
- **Archivos:**
  - `pages/Detalle.jsx` y su CSS (nuevos);
  - `components/PanelPartes.jsx` y `components/PanelRevision.jsx`, con su CSS (nuevos);
  - `services/resumen.js`.
- **Comando:** `impeccable context --target src/modulos/facturacion/pages/Detalle.jsx`
- **Comportamiento:**
  - **Barra:**
    - Volver al Resumen, con el estado conservado;
    - "Cliente · mes" y los badges;
    - los links a los Comprobantes, sólo con `puedeVer(…'comprobantes')`;
    - "Marcar revisada", sólo con `puedeEditar(…'resumen')` y `se_puede_revisar`.
  - **Tabla:**
    - "Supera" como etiqueta y no sólo como color;
    - "Sin Unidad sugerida";
    - el TOTAL en pesos, con las tareas sin precio.
  - **Panel de 360 px** con la comparación y los partes.
  - **Revisión:** la textarea obligatoria, y Deshacer con overlay y toast. Las dos invalidan el Detalle y el Resumen.
- **Verificación:** la misma que FA5.

**FA7. Suite y revisión**
- `npm test`, `npm run build` y `npm run lint`.
- `/impeccable critique` y `/impeccable audit` sobre el Resumen y el Detalle.
- Los majors se arreglan. Los minors van al cuerpo del PR y a "A futuro".

### 3.6 BK-E3b (rama nueva, F8)

**B1. Par: modelo y migración 006** (zona sensible: dos rondas)
- **Archivos:**
  - `models.py`: `periodo_desde` y `periodo_hasta`, más el comentario de `LineaComprobante.fecha` (decisión 2);
  - `migrations/facturacion/006_periodo_facturado.sql` (nuevo);
  - `ORDEN.txt`;
  - `LEEME.md`;
  - `tests/facturacion/test_migracion.py`;
  - `tests/facturacion/test_modelo_comprobantes.py`.
- **006:**
  - **Encabezado:**
    - "NO DIFERIBLE": antes de reiniciar;
    - "NO idempotente: aplicar UNA vez por base; antes, mirar que la columna no exista", porque MySQL 8 no tiene `ADD COLUMN IF NOT EXISTS`. El precedente es `terceros/005`.
  - **El ALTER:**
    ```sql
    ALTER TABLE facturacion_comprobante
      ADD COLUMN periodo_desde DATE NULL AFTER fecha,
      ADD COLUMN periodo_hasta DATE NULL AFTER periodo_desde
    ```
  - **Un UPDATE idempotente:**
    - va sólo sobre `es_historico = 0 AND periodo_desde IS NULL`;
    - usa un JOIN a `MIN(facturacion_linea.fecha)` por Comprobante;
    - pone desde = el día 1 de ese mes y hasta = `LAST_DAY`.
  - **Vuelta atrás comentada:** `DROP COLUMN` de las dos.
- **Rojo:**
  - la 006 entra en el parámetro de los `;`;
  - el encabezado tiene los dos avisos;
  - el ALTER agrega exactamente las dos columnas, y sus nombres son los del modelo;
  - el UPDATE tiene esa condición;
  - en `ORDEN.txt` va después de la 005;
  - en SQLite, uno a mano con período y un histórico sin período se guardan.
- **Verde:** el modelo, el `.sql`, `ORDEN.txt` y el `LEEME.md`.
- **Verificación:** `python -m pytest -q tests/facturacion/test_migracion.py tests/facturacion/test_modelo_comprobantes.py tests/core`

**B2. Par: Fecha de carga y Período en el servicio**
- **Archivos:**
  - `schemas.py`: entrada y salidas del contrato 3.2;
  - `comprobantes_service.py`:
    - `crear`, `:134-153`;
    - `editar`, `:157-247`;
    - `_validar_cabecera`, `:424-479`;
    - `_validar_lineas`, `:514-585`;
    - `detalle`, `:357-397`;
  - los tests:
    - `test_comprobantes_service.py`: los ayudantes `linea()` y `entrada()` (`:91-102`), y las aserciones de fecha en `:153`, `:163`, `:433`, `:451`, `:506-507` y `:669-712`;
    - `test_api_comprobantes.py`;
    - `test_adjuntos.py`;
    - `test_historico.py`, si arma entradas.
- **Rojo:**
  - el alta guarda `fecha = hoy()`, con `hoy` reemplazado, e ignora una `fecha` que llegue;
  - la edición conserva la fecha original;
  - los dos 422 del período;
  - toda Línea se guarda con `fecha = periodo_desde`;
  - el `mes` del listado es el del período en uno a mano; en un histórico no cambia;
  - el Detalle trae `creado_por_nombre`.
- **Verde:** la implementación.
- **Verificación:** `python -m pytest -q tests/facturacion`

**B3. Par: ruta de la Precarga**
- **Archivos:**
  - `services/precarga_service.py` (nuevo), que usa `partes_de_cliente`, `cruce.MEDIDA_DE_UNIDAD` y `precios.py`;
  - `api/comprobantes.py`: la ruta 18, con `editar_comprobantes`;
  - `schemas.py`;
  - `tests/facturacion/test_precarga.py` (nuevo);
  - `test_mapa_permisos.py`: 18 rutas.
- **Rojo:**
  - **El período:** 422 si cruza de mes o si desde es posterior a hasta.
  - **Lo trabajado:**
    - una quincena excluye la otra mitad;
    - `campo` trae una medida por unidad.
  - **Precios y empresa:** salen de A7.
  - **Permisos:** la persona con sólo Ver recibe 403.
  - **El mapa:** la fila 18.
- **Verde:** la implementación.
- **Verificación:** `python -m pytest -q tests/facturacion/test_precarga.py tests/facturacion/test_mapa_permisos.py tests/core/test_endpoints_con_permiso.py`

**B4. Par: el histórico sigue andando**
- **Archivos:** `tests/facturacion/test_historico.py`, que suma un test.
- **Rojo:**
  - un histórico aplicado queda con el período en NULL y con las fechas de la planilla en sus Líneas;
  - los tests de `conciliar` y de `--reemplazar-cambiados` siguen verdes sin cambios.
- **Verde:** no se espera tocar `historico.py`. Si algo falla, el arreglo mínimo.
- **Verificación:** `python -m pytest -q tests/facturacion/test_historico.py tests/facturacion/test_script_historico.py`

**B5. Suite completa**, como A13.

### 3.7 FT-E3b

**FB0. Arranque de impeccable (sin test)**
- Correr `impeccable context --target src/modulos/facturacion/pages/Precarga.jsx` y `--target src/modulos/facturacion/pages/Comprobante.jsx`.
- Leer `reference/craft-floor.md`.
- El brief es:
  - `pantallas.md`: Precarga, Comprobante y Comprobantes;
  - los mockups `Precarga.dc.html` y `Comprobante.dc.html`;
  - el boceto de F0.

**FB1. Par: período de la Precarga**
- **Archivos:** `periodo.js` y `periodo.test.js`.
- **Rojo:**
  - **Quincena pasada:**
    - el día 10, del 16 al último del mes anterior (incluido febrero bisiesto);
    - el día 20, del 1 al 15 del mes actual.
  - **Mes pasado** en enero.
  - **"Este mes"** es el mes entero.
  - **`dentroDeUnMes`**.
  - **`textoPeriodo`:** "1 al 15 de octubre".
  - **`periodoPropuesto`:** el mes de la fila del Resumen, o el mes pasado.
- **Verde:** la implementación.
- **Verificación:** `npm test`

**FB2. Par: lógica de la Precarga**
- **Archivos:**
  - `precarga.js` (nuevo)
  - `precarga.test.js` (nuevo)
- **Rojo:**
  - `armarLineas` arma una por tarea trabajada, facturable y sin sugerida de cosecha, con:
    - la Unidad sugerida, o vacía y marcada;
    - Cantidad = campo, o vacía si es 0;
    - el Precio sugerido, o vacío y marcado;
  - `campoDeLinea`;
  - el precio se vuelve a sugerir al cambiar la unidad si nadie lo tocó;
  - "Agregar línea" frena en 15; la Precarga puede traer más;
  - `faltaParaGuardar` sigue la lista del mockup, y además:
    - la Factura que corrige en una Nota de crédito;
    - el PDF sólo en el alta (pregunta 5);
  - `recalcular` reemplaza las Líneas.
- **Verde:** la implementación.
- **Verificación:** `npm test`

**FB3. Par: formulario sin fecha**
- **Archivos:** `formulario.js`, `formulario.test.js`, `lineas.js` y `lineas.test.js`.
- **Rojo:**
  - `filaVacia()` no trae fecha;
  - `validarLinea` no exige fecha;
  - `validarCabecera` exige el período y que quede en un mes;
  - `armarEntrada` manda el período y no la fecha;
  - `estadoDesdeDetalle` conserva el `finca_id` de las Líneas;
  - `errorDeGuardado` traduce los dos campos nuevos.
- **Verde:** la implementación.
- **Verificación:** `npm test`

**FB4. Visual: Precarga** (antes, F0 con OK)
- **Archivos:**
  - `pages/Precarga.jsx` y su CSS, nuevos. Toman el `Formulario` de `pages/Comprobante.jsx` (desde `:211`): se mueve, no se copia.
  - `components/GrillaLineas.jsx` y su CSS:
    - en edición, sin Fecha ni Finca;
    - columna Campo, marcada si no coincide con la Cantidad;
    - `title` del precio: "Último precio: FC … del …";
    - "N de 15".
  - `components/PanelPdf.jsx` (nuevo): el PDF, el control del neto y "Falta para guardar".
  - `services/comprobantes.js`: `obtenerPrecarga`.
  - `rutas.jsx`: `/comprobantes/nuevo` y `/comprobantes/:id/editar` abren la Precarga.
- **Comportamiento:**
  - **Datos de la factura.**
    - **Desde el Resumen:** el Cliente queda fijo y el período es el mes de la fila.
    - **Desde Comprobantes:** el Cliente se elige y el período es el mes pasado.
    - **Empresa:** la sugerida.
    - **Fecha de carga:** hoy, sin editar.
  - **Período.**
    - Si cruza de mes, queda en rojo.
    - Si cambia el período o el Cliente con Líneas cargadas, aparece el aviso "Recalcular líneas" o "Dejar como están", y no se guarda hasta elegir.
    - Si la grilla está vacía, se recalcula sola.
    - Campo muestra siempre el período actual (pregunta 16).
  - **Guardar.**
    1. Overlay y alta o edición.
    2. Si hay PDF, se sube con `subirAdjunto` (`services/comprobantes.js:57-63`), con el tope de 10 MB.
    3. Toast, y se pasa a la vista del Comprobante.
    4. Si la subida falla, la vista muestra "Se guardó, pero no el PDF: adjuntalo acá".
  - **Nota de crédito:** pregunta 7.
  - **Edición:** el panel muestra los Adjuntos de la E2 y se conserva Borrar.
- **Verificación:** `npm test`, `npm run build` y `npm run lint`. Smoke en F11.

**FB5. Visual: Comprobante y Comprobantes**
- **Archivos:**
  - `pages/Comprobante.jsx` y su CSS: queda sólo la vista;
  - `pages/Comprobantes.jsx`;
  - `listado.js`: el comentario de `mes`.
- **Comando:** `impeccable context --target src/modulos/facturacion/pages/Comprobante.jsx`
- **Comportamiento:**
  - **Vista del Comprobante:**
    - **Encabezado:** número, badge y estos dos botones:
      - "Ver lo trabajado", que lleva al Detalle del Cliente y el mes, sólo con Ver en `resumen`;
      - "Editar", sólo con Editar y si no es histórico.
    - **Avisos:** los banners de falta y de adjuntado.
    - **Fechas:**
      - el Período, como "1 al 15 de octubre";
      - "Fecha de carga · persona".
    - **Panel lateral:** Adjuntos y totales.
    - **Histórico:** sin Período, y con la Fecha en sus Líneas.
  - **Comprobantes:**
    - "Nueva factura" y "Nueva nota de crédito" en lugar de "Nuevo comprobante" (`:145` y `:192-196`);
    - el rótulo "Fecha" pasa a "Fecha de carga".
- **Verificación:** la misma que FB4.

**FB6. Suite y revisión**
- `npm test`, `npm run build` y `npm run lint`.
- `/impeccable critique` y `/impeccable audit` sobre la Precarga y el Comprobante.

### 3.8 Pasos FRENADOS (los hace la sesión principal, con OK donde se indica)

**F0. Boceto de lo que el mockup no cubre, con OK del usuario.** Lo arma la sesión principal en el scratchpad, sin datos reales.
- **E3a, aprobado por el usuario el 2026-10-14** (`fact-mockup/boceto-f0-e3a.html`, fuera del repo). Fija:
  - "Datos del campo de las HH:MM · Volver a leer", arriba a la derecha del Resumen;
  - el aviso de tareas sin Unidad sugerida, banner warn sobre la tabla con "Ver cuáles" (tarea y en cuántos Clientes);
  - el pie con "Cambiar" sólo para el Admin, que abre el formulario en el mismo pie (Umbral con %, Mes de corte, Cancelar, Guardar, el error 422 debajo del campo y "Último cambio: quién, cuándo");
  - en el Detalle, cuatro avisos: Con diferencia con una Revisión anterior que no alcanza (nombra la fecha, quién, el comentario, qué cubría y qué supera ahora), Antes del corte (info), Mes en curso (info) y Revisada con Deshacer; la tarea cubierta por la Revisión lleva la etiqueta "Revisada" junto a "Supera", y una tarea sin Unidad sugerida lo dice junto al nombre.
  - Al hacer FA5, `pantallas.md` suma la línea de "Datos del campo de las HH:MM" (el A0 no la tenía).
- **E3b:** pendiente, antes de FB4.
- Antes de FA5:
  - el aviso de tareas sin Unidad sugerida;
  - el pie con "Cambiar" y su formulario;
  - "Datos del campo de las HH:MM";
  - los avisos del Detalle con una Revisión anterior.
- Antes de FB4:
  - la Nota de crédito en la Precarga;
  - el modo edición;
  - Campo después de "Dejar como están".

**F1. Pre-check de la E3a en `testing`** (sólo lectura).
```sql
SELECT r.nombre, rp.pantalla, rp.nivel,
       (SELECT COUNT(*) FROM usuario_rol ur WHERE ur.rol_id = r.id) AS personas
FROM rol_permiso rp JOIN rol r ON r.id = rp.rol_id
WHERE rp.modulo = 'facturacion' AND rp.pantalla IN ('pendientes', 'cruce')
```
Las filas `rol_id, modulo, pantalla, nivel` se guardan en un archivo local fuera de git: son el respaldo de la 005.

**F2. La 004 en `testing`.**
1. Confirmar que `SELECT DATABASE()` da `testing`.
2. Confirmar que `SHOW TABLES LIKE 'facturacion_configuracion'` y `SHOW TABLES LIKE 'facturacion_revision%'` vienen vacíos.
3. Aplicar.
4. Levantar el backend del worktree con las variables de `testing` y ver "Tablas y columnas BD propia: verificadas".

**F3. La 005 en `testing`**, con el backend nuevo arrancado. Repetir F1: tiene que dar 0 filas.

**F4. Smoke en el navegador contra `testing`.**
- **Usuario de smoke:** su clave se lee de `../.claude/smoke-testing.env` y nunca se escribe.
- **Lo que se prueba:**
  - el Resumen con Mes pasado: todo Antes del corte;
  - mover el Mes de corte a un mes con históricos, desde el pie;
  - cuadros, filtros, TOTAL y aviso;
  - el Detalle con los partes;
  - dejar y deshacer una Revisión;
  - un 422 visible del formulario de configuración;
  - "Volver a leer".
- **Lo que se mide:** cuánto tardan, con la caché fría, Mes pasado, Últimos 3 meses y Este año. Los tiempos van al PR.
- **Lo que no se prueba:**
  - "Cambiar" escondido para quien no es Admin, si no hay en `testing` un usuario así;
  - el link "Cargar factura", que en la E3a abre el formulario de la E2.
  Las dos cosas se anotan.

**F5. Aceptación.**
1. Correr `PYTHONUTF8=1 python scripts/cruce_facturacion.py --desde … --hasta …` contra `testing`.
2. Los meses los elige el usuario (pregunta 10).
3. El usuario compara contra Power BI y anota cada diferencia con su causa.
4. Después va A12.

**F6. Cierre de la E3a.**
- Commits y PRs BK-E3a y FT-E3a, con `--body-file`. El cuerpo lleva las decisiones 1 a 7 condensadas y los minors.
- Merge del BK y después del FT, con `gh pr merge N --merge --admin`.
- `/bitacora`.

**F7. Deploy de la E3a, con OK del usuario.**
1. Respaldo de la base.
2. F1 en producción, con el respaldo de las filas.
3. La 004.
4. Deploy del BK y del FT (swap de carpeta) y reinicio.
5. Ver "verificadas" en el banner.
6. La 005, y repetir F1 hasta que dé 0.
7. Smoke sin escribir:
   - `/health`;
   - `GET /api/facturacion/resumen` sin sesión da 401;
   - el log, sin errores.
8. Avisar al usuario dos cosas:
   - que sume Resumen al rol de las contadoras cuando lo asigne;
   - que mueva el Mes de corte si quiere controlar septiembre.

**F8. Ramas de la E3b.** En los dos repos, desde `main` actualizado.

**F9. Pre-check de la E3b en `testing`.**
```sql
SELECT c.id, COUNT(DISTINCT YEAR(l.fecha) * 100 + MONTH(l.fecha)) AS meses
FROM facturacion_comprobante c JOIN facturacion_linea l ON l.comprobante_id = c.id
WHERE c.es_historico = 0 GROUP BY c.id
```
Si alguno da más de un mes, se corrige o se borra, con OK.

**F10. La 006 en `testing`.**
1. Confirmar que la base es `testing`.
2. Confirmar que `SHOW COLUMNS FROM facturacion_comprobante LIKE 'periodo_desde'` viene vacío.
3. Aplicar una sola vez.
4. Arrancar el backend nuevo y ver el banner.
5. Confirmar que todo Comprobante a mano tiene período.

**F11. Smoke de la E3b.**
1. Con el corte movido, una fila Pendiente de facturar del mes pasado.
2. "Cargar factura" abre la Precarga.
3. Cargar el número, adjuntar el PDF y guardar.
4. Volver al Resumen: la fila cambia de estado y no queda Falta comprobante.
5. Cambiar el período, con Recalcular y con Dejar.
6. Una Nota de crédito desde Comprobantes.
7. Editar un Comprobante.
8. Abrir un histórico en sólo lectura.

**F12. Cierre de la E3b.** PRs de la E3b, merge del BK y después del FT, `/bitacora`.

**F13. Deploy de la E3b, con OK del usuario.**
1. Respaldo de la base.
2. F9 en producción: se espera que no haya Comprobantes a mano.
3. La 006, antes de reiniciar.
4. BK y FT en la misma ventana, y reinicio.
5. El banner.
6. Smoke sin escribir.

### 3.9 Antes de cada PR

**Backend**, desde el worktree y sin `.env` real:
```
DB_EXTERNA_HOST=externa.invalid DB_EXTERNA_USER=x DB_EXTERNA_PASSWORD=x DB_EXTERNA_NAME=x \
DB_SUELDOS_HOST=sueldos.invalid DB_SUELDOS_USER=x DB_SUELDOS_PASSWORD=x DB_SUELDOS_NAME=x \
DB_PROPIA_HOST=propia.invalid DB_PROPIA_USER=x DB_PROPIA_PASSWORD=x DB_PROPIA_NAME=testing \
SECRET_KEY=clave-de-prueba-solo-para-tests python -m pytest -q
```

**Front**, con `node_modules` enlazado por junction al checkout principal (nunca se instala):
- `npm test`;
- `npm run build`;
- `npm run lint`: los 6 errores conocidos de `.claude/hooks/ultimas-entregas.mjs`, y ninguno nuevo.

**Revisión**
- Dos rondas en `permisos.py`, `migrations/` y `models.py`.
- `/impeccable critique` y `/impeccable audit` en el front.
- El diff, sin nombres de clientes, tareas reales, personas, valores ni hosts.

## 4. Riesgos

1. **Lentitud del campo.** En desarrollo, la primera lectura después de un rato tardó cerca de un minuto, y nginx puede cortar un pedido largo.
   - Mitigación:
     - caché de 10 minutos;
     - rango de hasta 12 meses que arranca en un mes;
     - indicador de carga;
     - tiempos medidos en F4.
   - Si en producción pasa los 60 segundos, se baja el tope o se mira el timeout, con OK, porque toca el servidor.
2. **El SQL del Cruce no corre en los tests.** Sólo `SesionFalsa`.
   - Mitigación: F4 y el script de F5 lo corren contra la base real antes del PR.
3. **Varchar con basura.** Mitigación: REGEXP antes de convertir, como Terceros.
4. **Diferencias con Power BI.**
   - Causas posibles:
     - la unidad;
     - el tractor;
     - `unidades` de pulverización;
     - las tareas No facturable;
     - la sugerida del campo contra la de Power BI.
   - Mitigación: el script muestra las dos medidas, y lo que no se explica frena el PR.
5. **Huso horario de "hoy".**
   - Mitigación: UTC-3 fijo en un solo lugar (`fechas.py`). El front usa la fecha del navegador.
6. **DELETE en `rol_permiso`, tabla del núcleo.** El rol de las contadoras existe en producción y pierde `pendientes` y `cruce`.
   - Mitigación:
     - pre-check con respaldo de las filas;
     - se aplica después del reinicio y es idempotente;
     - la vuelta atrás es reinsertar;
     - el aviso al usuario para sumar Resumen.
   - Un refresco de `testing` vuelve a copiar `rol_permiso` de producción: si producción todavía no tiene la 005, se reaplica en `testing`.
7. **DDL en `testing`, que es compartida.**
   - Mitigación:
     - sólo nuestras tablas;
     - controlar que la base sea `testing`;
     - el `SHOW TABLES` o `SHOW COLUMNS` previo.
8. **La 006 no es idempotente.**
   - Mitigación: `SHOW COLUMNS` antes, y una sola vez por base.
9. **PDF en dos llamadas.**
   - Mitigación: un aviso visible, y el mes marca Falta comprobante.
10. **Riesgo alto: la 004 y la 006 en producción.**
    - Mitigación:
      - respaldo de la base antes (F7 y F13);
      - vuelta atrás escrita: la 004, DROP de las tres tablas mientras no tengan datos reales; la 006, DROP de las dos columnas;
      - con datos reales, se restaura el respaldo.
11. **Cambio de contrato en la E3b.**
    - Mitigación: BK y FT en la misma ventana. El módulo está escondido.
12. **Caché contra datos frescos.**
    - Mitigación:
      - `leido_en` y "Volver a leer";
      - la Revisión guarda lo que vio el Detalle.
13. **Sin Alertas en producción hasta noviembre**, si el corte queda donde está (premisa 1).
14. **Una Nota de crédito que sólo corrige precio** resta cantidad: el mes queda Con diferencia (pregunta 6).
15. **El CSV de aceptación tiene nombres.**
    - Mitigación: queda en `fuentes/`, fuera de git, con el aviso del script.

## 5. Preguntas abiertas (con lo que asumo si nadie contesta)

1. **¿Se mueve el Mes de corte al activar el módulo en producción?** Asumo que queda en octubre de 2026 y que el Admin lo mueve desde el pie cuando quiera.
2. **¿Qué es "Antes del corte, sin sumas"?** Asumo que los números se ven y suman en el TOTAL, sin Alertas ni "Supera".
3. **¿Con qué se valorizan en pesos las tareas sin facturado?** Asumo que con el Precio sugerido. Si no hay, quedan sin valorizar con "N tareas sin precio".
4. **¿Supera una tarea trabajada con Cantidad del campo 0 (o sin unidad) y nada facturado?** Asumo que sí, por la letra de D2; la fórmula del mockup dice que no.
5. **¿El PDF es obligatorio para guardar en la Precarga?** Asumo que sí en el alta, como el mockup, y que no en la edición.
6. **¿Una Nota de crédito que sólo corrige precio también resta cantidad?** Asumo que sí: el glosario dice "restan en el Cruce". Se resuelve con una Revisión.
7. **¿Cómo se carga una Nota de crédito en la Precarga?** Asumo la grilla vacía, la Factura que corrige, el Período de esa Factura y el Precio sugerido común.
8. **¿Qué fecha se muestra en un histórico?** Asumo la fecha de la planilla, rotulada "Fecha (planilla)".
9. **¿Lo facturado del Resumen excluye la cosecha y lo No facturable, y Falta comprobante sólo mira los Comprobantes que entran al Cruce?** Asumo que sí.
10. **¿Qué meses se comparan con Power BI?** Asumo los tres últimos meses cerrados con históricos, o los que elija el usuario.
11. **¿Qué tractor se cuenta?** Asumo el 1, en las tres medidas.
12. **¿Hay "Ver detalle" en Antes del corte y en Mes en curso?** Asumo que sí, sin "Supera" ni Revisión.
13. **¿La Precarga muestra la finca?** Asumo que no, y que al editar se conserva la que ya tenían las Líneas.
14. **¿"Dónde" es la finca del parte?** Asumo que sí.
15. **¿Hasta cuántos caracteres tiene el comentario de la Revisión, y quién la deshace?** Asumo 500, y que cualquiera con Editar en Resumen puede deshacer la de otro.
16. **¿Qué muestra Campo después de "Dejar como están"?** Asumo que lo trabajado en el período nuevo.
17. **¿Cambia el listado de Comprobantes?** Asumo que sólo cambian los dos botones y el rótulo "Fecha de carga".

## 6. Fuera de alcance

- Importar orden del portal y Equivalencias: son de la E4. También `AYUDA-facturacion.md`.
- El Panel: es de la E5.
- Pegar filas desde Excel.
- Un Umbral por Cliente o por tarea.
- La cosecha.
- La nota de débito.
- El rediseño completo del listado de Comprobantes (`pantallas.md:90-95`: período, Origen, PDF y TOTAL).
- Asignar roles. Lo hace el usuario.
- La limpieza de etapas anteriores, el CI y nginx.
- Cualquier cambio en Preliquidación, en Terceros o en el núcleo del front o del backend.

## Archivos de referencia (rutas absolutas)

Backend: `C:\Users\Administrador\Desktop\LA Gero\Sistema_Preliquidacion\backend_preliquidacion\.claude\worktrees\facturacion-e3\`
- `app\modulos\facturacion\permisos.py`
- `app\modulos\facturacion\models.py`
- `app\modulos\facturacion\schemas.py`
- `app\modulos\facturacion\config.py`
- `app\modulos\facturacion\__init__.py`
- `app\modulos\facturacion\api\comprobantes.py`
- `app\modulos\facturacion\services\comprobantes_service.py`
- `app\modulos\facturacion\services\consulta_externa.py`
- `app\modulos\facturacion\services\historico.py`
- `app\modulos\preliquidacion\services\consulta_externa.py`
- `app\modulos\terceros\services\consulta_externa.py`
- `app\core\permisos.py`
- `app\core\models.py`
- `migrations\ORDEN.txt`
- `migrations\facturacion\` (de `002` a `003` y `LEEME.md`)
- `tests\facturacion\` (`test_mapa_permisos.py`, `test_migracion.py`, `test_api_comprobantes.py`, `test_comprobantes_service.py`)
- `tests\core\test_migracion_roles.py`
- `scripts\refrescar_testing.py`
- `docs\modulos\facturacion\` (`plan-facturacion.md`, `pantallas.md`, `CONTEXT-facturacion.md`)
- `docs\modulos\GUIA-MODULOS.md`

Front: `C:\Users\Administrador\Desktop\LA Gero\Sistema_Preliquidacion\frontend_preliquidacion\.claude\worktrees\facturacion-e3\`
- `src\modulos\facturacion\` (`rutas.jsx`, `listado.js`, `formulario.js`, `lineas.js`, `services\comprobantes.js`, `pages\Comprobante.jsx`, `pages\Comprobantes.jsx`, `components\GrillaLineas.jsx`)
- `src\core\ui\` (`TablaOrdenable.jsx`, `ordenarFilas.js`, `CargandoOverlay.jsx`, `FiltrosBar.jsx`, `opcionesCascada.js`)
- `src\core\permisos.js`
- `package.json`
- `.claude\skills\impeccable\reference\` (`craft-floor.md`, `new-work.md`)