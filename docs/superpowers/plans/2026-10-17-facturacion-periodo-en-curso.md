# Facturación: el Estado se controla por el período filtrado, no por el mes (2026-10-17)

## El pedido

Del usuario, textual: "los controles se harán quincenales para facturar. Por lo que veo las alertas
son mensuales. Ejemplo: yo pongo quincena pasada y me dice mes en curso, cuando de hecho ya podría
yo querer facturarle y tener el acceso directo. [...] El contador entrará, filtrará un rango de
fechas y quiere saber cuáles clientes tiene facturados y cuáles no. Aquello que no, precargar la
factura con lo que hay en campo en ese período."

Hoy `cruzar_mes` (`app/modulos/facturacion/services/cruce.py`) controla un mes sólo si es anterior
al mes en curso (`controlado = mes_corte <= mes < mes_en_curso`). El 17 de octubre, "Quincena
pasada" (1 al 15) cae en octubre y sale "Mes en curso": no avisa Pendiente de facturar ni muestra
"Cargar factura". Así lo decían el BK #100 y `pantallas.md` ("Desde el día 16, Quincena pasada cae
en el Mes en curso"); esto lo revierte.

## Decisiones cerradas (usuario, 2026-10-17)

1. **El Estado sale del período filtrado.** Todo mes desde el Mes de corte se controla: Pendiente
   de facturar, Con diferencia, Falta comprobante, Sin comparar y Facturada, también en el mes en
   curso. Sale el estado "Mes en curso".
2. **Un período que todavía no terminó se controla igual que uno terminado**, con un aviso de que
   el campo todavía puede sumar partes. "No terminó" = el último día del período filtrado (Hasta,
   recortado al mes) es hoy o posterior.
3. Sin cambios: Antes del corte; el tope de Hasta (fin del mes en curso); el Mes de corte no
   posterior al mes en curso; la Revisión (se puede revisar un período en curso; si cambian los
   grupos que superan, vuelve a Con diferencia, como siempre).

## Tickets

Carril completo: cambia la API entre los dos repos (sale una clave de estado y entra `en_curso`).
Sin DDL ni migración. Worktrees: `backend_preliquidacion/.claude/worktrees/facturacion-periodo` y
`frontend_preliquidacion/.claude/worktrees/facturacion-periodo`, rama
`feature/facturacion-periodo-en-curso` en los dos. Los Tickets 1 y 2 van en paralelo: el contrato
está fijado acá.

### Ticket 1 — Backend (par)

- `services/cruce.py`: `cruzar_mes` y `cruzar` reciben `hoy: date` en lugar de `mes_en_curso`.
  `controlado = mes >= mes_corte`. Sale la rama de `MES_EN_CURSO` y la constante, también de
  `ESTADOS`. `CruceMes` suma `en_curso: bool = hasta >= hoy` (`hasta`, el ya recortado al mes).
- `services/resumen_service.py`: pasa `fechas.hoy()`; `_por_que_no_se_revisa` pierde el caso del
  mes en curso. `mes_en_curso()` se queda para los topes de Hasta y del Mes de corte, y el campo
  `mes_en_curso` de la respuesta del Resumen también (es el tope del selector en el front).
- `schemas.py`: `EstadoMes` sin `"mes_en_curso"`; `FilaResumen` y la respuesta del Detalle suman
  `en_curso: bool`.
- Test rojo primero (`tests/facturacion/test_cruce.py`, con hoy fijo el 2026-10-17): un Cliente
  con partes del 1 al 15 de octubre y sin facturas, filtrado del 1 al 15, da Pendiente de facturar
  y `en_curso` falso (hoy da Mes en curso); filtrado del 16 al 31 con partes del 16, Pendiente de
  facturar y `en_curso` verdadero. Uno de API: la fila del Resumen trae `en_curso`. Se ajustan los
  tests que esperaban `mes_en_curso` (`test_cruce`, `test_resumen_service`, `test_api_resumen`,
  `test_detalle`, `test_revision`).
- `scripts/cruce_facturacion.py`: sólo si deja de andar.

### Ticket 2 — Front (par en lo lógico; lo visual, en el navegador)

- `estados.js`: sale `mes_en_curso`. `fueraDelFiltro.js` (`SIN_CONTROL`) y `esGris` de
  `pages/Resumen.jsx` quedan sólo con `antes_del_corte`.
- Resumen: si la fila trae `en_curso`, al lado del estado una etiqueta tenue **"En curso"**, con
  el texto "El período todavía no terminó: el campo puede sumar partes." como `title` y para
  lectores de pantalla.
- Detalle (`detalle.js` y su página): sale el aviso "Mes en curso:"; con `en_curso`, una línea
  info arriba, aparte del aviso de la Revisión: **"Período en curso: el campo todavía puede sumar
  partes hasta el {Hasta}."**
- `PieConfiguracion.jsx`: "Mes en curso: sólo se controla que cada factura tenga su PDF." pasa a
  "Un período que todavía no terminó se controla igual, pero el campo puede sumar partes."
- Test rojo primero en `estados.test.js`, `detalle.test.js` y `fueraDelFiltro.test.js`.

### Ticket 4 — Front: el período se elige en un calendario (sumado el 2026-10-17, después del Ticket 2)

Del usuario, textual: "no quiero un filtro estandarizado como el que está, quiero tener un
calendario para filtrar como se me dé la gana". Eligió, sobre un boceto, **calendario de rango con
los atajos al costado**, en este mismo cambio. Reemplaza al desplegable de atajos con "Otro
período" de `components/SelectorMeses.jsx`.

- Cerrado: un campo muestra el período elegido ("01/10/2026 – 15/10/2026"); al hacer clic abre un
  panel con el calendario de un mes (‹ mes anterior, mes siguiente ›) y, al costado, los atajos de
  `ATAJOS_RESUMEN` como botones chicos (Quincena pasada, Esta quincena, Mes pasado, Este mes,
  Últimos 3 meses, Este año). Un clic en un atajo aplica su rango (una consulta, se guarda
  `{ atajo: id }`) y cierra el panel, como el desplegable de antes; para corregirlo se vuelve a
  abrir y el calendario muestra ese rango marcado, con su mes a la vista (decisión del usuario,
  2026-10-17, ante el FRENADO del ejecutor). Un rango elegido a mano se guarda
  `{ atajo: OTRO_PERIODO, desde, hasta }`. Primer clic en un día = Desde, segundo clic = Hasta
  (si es anterior al primero, se dan vuelta); con el segundo clic el filtro se aplica (una sola
  consulta) y el panel se cierra. Escape o clic afuera cierran sin cambiar. Los días posteriores
  al tope (`topeDelPeriodo`, fin del mes en curso) no se eligen. El rango elegido y hoy se
  distinguen en el calendario; el atajo cuyo rango coincide con el elegido se ve marcado. Arranca
  en Mes pasado, como ahora.
- Sin librerías (una dependencia nueva necesita aprobación), CSS Modules con los tokens de
  `src/index.css`. Teclado: el campo abre con Enter o Espacio; en la grilla, flechas para moverse
  por los días, Enter para elegir; el foco vuelve al campo al cerrar. Etiquetas para lectores de
  pantalla (nombre del día completo con la fecha).
- Lo que tiene que seguir andando: el botón del aviso "fuera del filtro" que pasa el filtro al
  período entero de la factura; el período que lee la pantalla (`periodoElegido`, `vistaResumen`)
  y el que manda al backend (Desde y Hasta, sin cambios en la API).
- Par: la lógica del rango (dos clics, dar vuelta, tope, qué atajo coincide) en una función pura
  con su test rojo primero; lo visual, en el navegador. `impeccable`: setup y `craft-floor.md`
  antes de editar; entra en el `critique` y el `audit` de la Verificación.
- Después: el Período facturado de la Precarga (E3b) usa este mismo calendario.

### Ticket 3 — Docs

`CONTEXT-facturacion.md` (sale "Mes en curso" de los estados, entra el aviso de período en curso),
`pantallas.md` (la línea de "Desde el día 16…") y `plan-facturacion.md` (el estado y su regla).

## Verificación

Suites completas de los dos repos, build y lint, una vez. `revision-codigo` de dos ejes, una ronda
(no toca zonas sensibles ni migraciones). Smoke contra `testing`: Quincena pasada (1 al 15 de
octubre) muestra Pendiente de facturar y Facturada donde corresponde, con "Cargar factura"; Esta
quincena muestra "En curso"; el Detalle, la línea del aviso.

### Pasos R (revisión de código, 2026-10-17: 0 urgent, 2 high, 8 minor, 2 descartados)

- **R1 (high).** `pantallas.md` decía que los atajos "sólo marcan su rango y se pueden corregir
  a mano", lo contrario de la decisión del usuario y de lo que hace el código. Falla: quien arme
  la E3b con este calendario construye la versión descartada. Arreglo: "un clic en un atajo
  aplica su rango y cierra el panel, y para corregirlo se vuelve a abrir". Sólo doc, sin test.
- **R2 (high).** `PRODUCT.md` del front juntaba la frase nueva con "el trabajo es mensual y
  sobre meses cerrados: las alertas se evalúan sobre el último mes cerrado", que la contradice.
  Falla: la próxima pasada de `impeccable` lee dos instrucciones opuestas. Arreglo: el párrafo
  dice que el control es por período, casi siempre una quincena, y que uno sin terminar se
  controla con el aviso. Sólo doc, sin test.

### Pasos R de `impeccable` (critique y audit, 2026-10-17: 0 urgent, 4 high, 7 minor, 6 descartados)

Los cuatro son del front (`src/modulos/facturacion/`), sin test de lógica pura: se verifican en
el navegador.

- **R3 (high).** Escape deja de cerrar el panel. Falla: con Mes pasado, "Mes siguiente" lleva al
  mes del tope, el botón queda `disabled` con el foco puesto y el foco cae al `body`; Escape (el
  `onKeyDown` está en la raíz) y el blur (`relatedTarget` nulo) ya no cierran. Confirmado en el
  navegador. Arreglo: en `irAMes` de `components/SelectorMeses.jsx`, si el mes nuevo no tiene
  siguiente, `moverFoco.current = true` (el efecto lleva el foco al día 1).
- **R4 (high).** El rango casi no se ve: `--accent-dim` sobre `--bg-base` da 1,07:1, y el hover
  de un día en rango le saca el tono. Falla: con Últimos 3 meses, en la vista del mes del medio
  los días del rango se ven iguales a los de afuera. Arreglo, en `SelectorMeses.module.css`: un
  borde arriba y abajo con `--accent` en `.enRango` (no depende sólo del fondo) y el hover sin
  perderlo.
- **R5 (high).** El panel se recorta con zoom: `.page` del Resumen tiene `100vh` y `overflow:
  hidden`. Falla: a 1366x768 con zoom al 200%, la última semana y la ayuda quedan cortadas.
  Arreglo: `.panel` con `max-height` al alto que queda debajo del campo y `overflow-y: auto`.
  Ese alto se mide al abrir (`SelectorMeses.jsx`, una variable CSS): un número fijo no alcanzaba,
  porque a 683 px de ancho la barra de filtros baja y el campo arranca a 290 px y no a 106.
- **R6 (high, arreglo mínimo).** El calendario deja armar un rango de más de 12 meses y la
  pantalla responde con un texto viejo ("Hasta no puede ser anterior a Desde ni posterior al fin
  del mes en curso"), de campos que ya no existen. Arreglo: en `pages/Resumen.jsx`, el texto dice
  que el período abarca 12 meses como máximo y que se elija uno más corto en el calendario.
  Descartado por ahora: deshabilitar en el calendario los días a más de 12 meses del Desde (3
  archivos; queda como minor).

## Después

Sin migración. Va al deploy junto con la E3a, que todavía no está en producción: no hay nada que
compatibilizar. La Precarga armada con lo trabajado es la E3b: "Cargar factura" hoy abre el
Comprobante nuevo vacío. Al planear la E3b, la Precarga toma el período del filtro como Período
facturado.
