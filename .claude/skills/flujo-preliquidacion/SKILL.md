---
name: flujo-preliquidacion
description: >
  La versión del Sistema de Preliquidación de La Asturiana de la skill `flujo`
  (backend_preliquidacion y frontend_preliquidacion): se usa en lugar de la
  global, nunca las dos. El circuito completo de una tarea de desarrollo, en dos
  carriles - corto para fixes y tareas simples (plan de 5 líneas, ejecución en
  sesión, una ronda de revisión) y completo para el resto (entrevista con ADRs y
  glosario, spec con tickets verticales escrita por la misma sesión que
  entrevistó, ejecución con el agente ejecutor Opus/high un ticket por vez,
  revisión con verificador y severidad). Usar al empezar cualquier tarea que modifique alguno de los dos
  repos. No usar para preguntas, explicaciones ni consultas de estado.
---

# Flujo de trabajo

Cinco fases y **dos carriles**. Cada fase termina en algo revisable, y **tres
fases frenan esperando al usuario** en los dos carriles. Nunca saltees una fase
en silencio: si la salteás, decilo y por qué.

**Esta es la skill de flujo del Sistema de Preliquidación**, para los dos
repos (`backend_preliquidacion` y `frontend_preliquidacion`). Se usa **en lugar
de la global `flujo`, nunca las dos**: esta es completa.

**Mandan `AGENTS.md` y `CLAUDE.md`** (y los `CLAUDE.local.md`, con lo de cada
máquina). El bloque común de `AGENTS.md` es idéntico en los dos repos; el
diario, el estado, el glosario y los ADR viven en el backend. Si algo de acá
choca con esos archivos, valen ellos. Si no definen algo que esta skill
necesita, preguntá en vez de asumir.

```
                 CORTO (fix / tarea simple)          COMPLETO (el resto)
0. Entrevista    solo si hay una decisión abierta     grilling + domain-modeling
1. Plan / spec   vos, 5-10 líneas → archivo           vos: spec + tickets → archivo
2. Aprobación    PARÁS ⏸ (OK de 30 s)                 PARÁS ⏸ + aviso (spec y corte)
3. Ejecución     vos, en sesión, test rojo primero    ejecutor (Opus/high), un TICKET por vez
4. Revisión      suite 1 vez → review → verificador   ídem, 2 rondas si toca zonas sensibles
                 → PARÁS ⏸                            → PARÁS ⏸ + aviso
5. Entrega       mostrar → OK → PR → merge → bitácora ídem                          ⏸
```

---

## Elegir el carril (antes de todo)

Leé el código afectado, dos minutos, y decidí. **Carril corto** si se cumplen
las cuatro:

1. La decisión ya está cerrada (el usuario dijo qué y cómo, o es un bug con
   comportamiento esperado obvio).
2. Hasta **3 archivos de código** (los tests y docs no cuentan).
3. **Sin DDL.**
4. **Sin cambio de contrato** entre partes que se deployan por separado: la
   API entre `backend_preliquidacion` y `frontend_preliquidacion`.

Si no, **carril completo**. Ante la duda, completo. Decilo en una línea al arrancar: "Carril corto: 1
archivo, sin API" o "Carril completo: hay DDL y decisiones abiertas". Si en el
medio descubrís que el corto no alcanza (aparece una decisión, un cuarto
archivo, un DDL), **pasás al completo desde donde estés y avisás**. Nunca al
revés en silencio.

**Antes de editar, aislá el trabajo.** Entrá al worktree con `EnterWorktree`
(las ediciones en el checkout compartido se rechazan), uno en cada repo que
toque la tarea. Dependencias en el worktree:

- **Frontend**: no instales. Enlazá el `node_modules` del checkout principal
  con un junction, desde el worktree:
  `cmd /c mklink /J node_modules <checkout principal del front>\node_modules`.
  **Antes de borrar el worktree, quitá el junction con `cmd /c rmdir
  node_modules`**, que borra sólo el enlace. **Nunca `rm -rf`** (ni ningún
  borrado recursivo) sobre el junction: sigue el enlace y vacía el
  `node_modules` del checkout principal.
- **Backend**: el venv del checkout principal sirve desde el worktree
  (activalo o llamá a su `python` por ruta absoluta); no crees otro.

**Configuración en el worktree**: nunca copies el `.env` real a un worktree
(el de una máquina de desarrollo puede traer credenciales de producción). Para
**tests**, creá un `.env` ficticio a partir de `.env.example` (hosts
`.invalid`, claves de prueba) o pasá las variables en línea al correr
`pytest`. Para **levantar la app**, exportá al proceso sólo las variables de
`testing` (`DB_PROPIA_NAME=testing`), nunca `DB_PROD_*` ni `DB_DEV_*`, y nunca
`PERMITIR_BASE_PRODUCCION` (ADR-0014: `preliquidacion` es producción y ninguna
máquina de desarrollo apunta ahí). Anotá en cada briefing cómo se cargan las
variables (ruta del `.env` ficticio o variables en línea).

Anotá la **ruta absoluta** de cada worktree: va en cada briefing.

---

## Tareas con interfaz (`impeccable`)

Si la tarea cambia algo visible en el front o suma una feature con interfaz, en
cualquiera de los dos módulos, se usa la skill `impeccable` del repo del front
(`.claude/skills/impeccable/SKILL.md`; `AGENTS.md`, "Cambios de interfaz"), en
los dos carriles. No reemplaza ninguna fase: entra en ellas así.

- **Entrevista**: lo de UX (quién usa la pantalla, qué ve, qué hace, qué
  estados tiene) se trabaja con `/impeccable shape <pantalla>`. Si el front no
  tiene `PRODUCT.md`, antes va `/impeccable init`. Si la tarea cambia la
  estética, la dirección nueva se decide con el usuario y queda en `DESIGN.md`.
  Corto: un ajuste sobre la estética actual no lleva `shape`.
- **Spec**: cada ticket de interfaz dice qué comando de `impeccable` corre y
  sobre qué pantalla. El briefing del ejecutor nombra la ruta absoluta de la
  skill en el worktree del front: los agentes no la ven solos.
- **Ejecución**: quien edita interfaz corre antes el setup de la skill
  (`impeccable context`) y lee `reference/craft-floor.md`. La lógica sigue con
  su par test rojo + implementación; lo puramente visual va como paso sin test,
  verificado en el navegador.
- **Revisión**: además de `revision-codigo`, una pasada de `/impeccable
  critique` y `/impeccable audit` sobre las pantallas tocadas. Sus hallazgos
  pasan por el `verificador-review` con la misma regla `urgent` / `high` /
  `minor`. Si la tarea es de diseño, cierra con `/impeccable polish`.
- **Entrega**: el smoke en el navegador muestra al usuario las pantallas
  tocadas. Si cambió la estética, `DESIGN.md` va en el mismo PR.

Las reglas del proyecto (`docs/modulos/GUIA-MODULOS.md`, sección 4.5) valen por
encima de lo que proponga `impeccable`; si chocan, se pregunta.

---

## Fase 0 — Entrevista

**Completo:** cuando el pedido tiene decisiones abiertas que no te
corresponden — alcance, reglas de negocio, casos borde, qué se muestra.
**Antes de preguntar, buscá antecedentes** en `docs/BITACORA.md` y `docs/adr/`
del backend (grep por los términos del tema): ahí está el porqué de lo
decidido y lo descartado. Si no está, no asumas que no se decidió: preguntá.
Invocá `grilling` (una pregunta por vez, con tu recomendación, citando los
antecedentes que encontraste) y, si aparece vocabulario nuevo o una decisión
arquitectónica que sobrevive a la tarea, `domain-modeling` para el ADR y el
glosario (el que indique `CONTEXT-MAP.md`). **Un ADR es un compromiso y se
escribe sólo con el usuario**, nunca como resumen de lo que pasó. **Listá los
ADR en el worktree del backend, no en el checkout local**: puede estar atrasado
y te hace repetir un número.

**Corto:** sin entrevista. Si aparece **una** decisión abierta, una sola
pregunta con recomendación y seguís. Si aparecen dos o más, es completo.

**Cuándo saltearla en el completo:** el usuario ya dijo exactamente qué quiere
y cómo. Decilo: "salteo la entrevista porque el pedido ya está cerrado".

## Fase 1 — Spec y tickets

La idea en una línea: **la spec dice qué y por qué; el cómo, archivo por
archivo, lo descubre el ejecutor con el código delante.**

**Completo:** la spec la escribís **vos, en esta misma sesión**, apenas cierra
la entrevista: ya tenés todo el contexto y nadie tiene que reconstruir las
decisiones. **No se lanza el `planificador`** (tardaba entre 40 y 70 minutos;
la spec, unos 4). Mirás el código **sólo para lo de Riesgo** (números de
migración, rutas y permisos, contrato); el resto lo lee el ejecutor una sola
vez. **Sin rutas de archivos ni código** (envejecen y el ejecutor las
encuentra), salvo en el bloque Riesgo, que va exacto. Va en
`docs/superpowers/plans/AAAA-MM-DD-<tema>.md` **del backend, aunque la tarea
sea sólo de front**. **Los repos son públicos**: specs y PRs sin IPs, hosts,
credenciales, datos de terceros ni listados de tablas.

### Plantilla de la spec

1. **Problema**: qué le pasa al usuario hoy, en dos o tres líneas.
2. **Solución**: qué va a poder hacer cuando esté.
3. **Historias de usuario**: "Como contadora, quiero … para …", una por cosa
   que se ve.
4. **Decisiones cerradas**: numeradas, con su porqué y lo descartado (salen de
   la entrevista).
5. **Riesgo**: lo único que va con nombres exactos, porque ningún test lo
   cubre solo:
   - **Migraciones**: número de cada una (sigue al último del módulo, al final
     de `migrations/ORDEN.txt`), qué hace, respaldo, vuelta atrás y **si va
     antes o después del reinicio del backend**.
   - **Contrato entre repos**: qué endpoints nacen o cambian, y en qué orden se
     deployan back y front.
   - **Permisos**: pantallas nuevas o que se van, y si cambia `ESPERADO` de
     `test_mapa_permisos.py`.
   - **Datos**: qué se borra o se transforma en `testing` y en producción.
   - **Zonas sensibles que toca** (las de la Fase 4): definen si van dos rondas
     de revisión.
6. **Decisiones de testeo**: en qué costuras se testea (preferir las que ya
   existen) y qué casos borde tienen que tener test.
7. **Casos borde en pantalla**: qué muestra la app en los casos raros (un mes
   sin trabajo, un cliente sin factura, el día 16 de la quincena…).
8. **Fuera de alcance**: lo que no entra, para que nadie lo dé por incluido.
9. **Preguntas abiertas**: si queda alguna, la spec no se aprueba hasta
   cerrarla.

### Plantilla de cada ticket (al final de la spec)

```
### Ticket N — <nombre de la funcionalidad>
Qué se construye: <el comportamiento de punta a punta, en prosa>
Repos: back | front | los dos
Depende de: Ticket M (o "ninguno")
Toca: <áreas, sin rutas: el motor del cruce, la API del Resumen, la pantalla del Detalle, la migración 006…>
En paralelo con: Ticket K (o "ninguno"), según las cinco condiciones
Decisiones que aplica: 2, 5
Criterios de aceptación:
- [ ] <algo que se puede comprobar: un test, una respuesta de la API, algo en pantalla>
PR: <en qué PR (o PRs hermanos) viaja>
```

**Cómo se corta la tarea en tickets** (los propone la sesión; los aprueba el
usuario):

- **Cada ticket se prueba solo**: cuando termina, hay algo que el usuario puede
  ver o comprobar (en pantalla, en la API o con un test). "Guardar y ver la
  observación" es un ticket; "la columna en la base" no, porque sola no se ve.
- **Verticales**: atraviesan esquema, API, pantalla y tests de una
  funcionalidad. Nada de "ticket de modelos" o "ticket de endpoints".
- **Primero lo que prepara el terreno** (una migración que todos necesitan, un
  refactor previo), como ticket propio.
- **Cada ticket entra en una sola sesión del ejecutor.** Si no entra, se parte.
- **Una migración va en el ticket que la necesita** (las migraciones no se
  difieren).
- **Las dependencias quedan escritas** en "Depende de"; los tickets se numeran
  en el orden en que se ejecutan.
- **Tamaño de referencia**: una sola cosa visible (un campo, un filtro, un
  aviso) es 1 ticket; una etapa como la E3a de Facturación ronda los 4 o 5. Si
  salen más de 7, probablemente son dos etapas y se pregunta.
- **Interfaz**: cada ticket de interfaz dice qué comando de `impeccable` corre.

**Qué tickets van en paralelo.** Sólo si cumplen las cinco condiciones; si
falla una, van en serie:

1. **Ninguno depende del otro** (ni directo ni a través de un tercero).
2. **No comparten ningún área de "Toca"**, así los cambios no chocan al
   juntarlos.
3. **A lo sumo uno crea una migración** (dos podrían tomar el mismo número o
   tocar la misma tabla).
4. **Ninguno cambia un contrato que el otro usa** (una ruta, la forma de una
   respuesta, un modelo compartido).
5. **No reescriben los mismos tests.**

El paralelo es la excepción: se marca sólo cuando las cinco se cumplen
claramente; en la duda, en serie. Lo que sale sólo de las decisiones y no del
código (docs, glosario, marcas en otro plan) suele poder ir en paralelo con
todo.

### Antes de mostrarla, la lista de control

- Cada migración: número correcto, `ORDEN.txt`, respaldo, vuelta atrás, antes
  o después del reinicio (comparado con los encabezados de las que ya existen).
- Cada cambio de contrato: ticket en los dos repos y orden de deploy.
- Cada pantalla nueva o que se va: anotado si cambia `ESPERADO`.
- Cada decisión de la entrevista está en "Decisiones cerradas"; ninguna quedó
  sólo en el chat.
- Cada ticket tiene criterios de aceptación comprobables y sus dependencias.
- Cada ticket se prueba solo: ninguno es una capa suelta (sólo base, sólo API).
- Cada "En paralelo con" cumple las cinco condiciones y es simétrico (si el 2
  va con el 5, el 5 va con el 2).

**El `planificador` queda guardado sólo para una tarea enorme** en la que esta
sesión se quedaría sin contexto, y se usa con OK del usuario. Antes de eso,
probá partir la spec en dos etapas.

**Corto:** escribís vos el plan en **5 a 10 líneas** en el mismo lugar que las
specs: qué se pide, archivos que tocás, test que va a fallar primero, cómo se
verifica. Un solo lugar para los planes, siempre.

## Fase 2 — Aprobación ⏸

Mostrá en el chat la spec, sobre todo **Riesgo, Casos borde y preguntas
abiertas completos**, y la ruta del archivo. **Parás.** Sin OK explícito no
ejecutás, aunque parezca obvio. Completo: mandá aviso (ver _Avisos_). Corto:
sin aviso, es un OK de 30 segundos.

**Completo: el corte en tickets también se aprueba.** Mostrá la lista numerada
(nombre, qué se prueba al terminar, de cuál depende y cuáles van en paralelo),
con el orden dibujado (`1 → 2 → 3`, y debajo `5b, en paralelo con todo`), y
preguntá si el corte le sirve. El usuario puede **juntar** ("el 2 y el 3 van
juntos"), **partir**, **reordenar**, **sacar** (va a "A futuro" de
`estado.md`) o pedir que algo en paralelo vaya en serie. Ajustás la spec y la
volvés a mostrar hasta el OK.

Con el OK, **actualizá `docs/estado.md`**: la tarea en "En curso", con su fase
y la ruta de la spec (o del plan, en el corto), y el "Próximo paso".
`estado.md` es sólo lo vivo (nada entregado), va directo a `main` como la
bitácora (la excepción de `AGENTS.md`, "Bitácora y estado"), se commitea con `/commit` y nunca lleva IPs,
hosts, URLs, credenciales, datos de terceros ni valores. **Se edita en el
checkout principal del backend, en `main`; nunca en el worktree de la tarea**:
ahí viajaría en el PR y chocaría con lo que `/bitacora` cambia en `main`.

## Fase 3 — Ejecución

**Antes de empezar, decí en qué modelo corre esta sesión y quién ejecuta.**

### Carril completo: orquestás al `ejecutor`, un TICKET por vez

El ejecutor **planifica su ticket** (qué archivos y qué tests) y lo hace en
**pares**: el test rojo y la implementación que lo pone verde. Lee el contexto
una vez por funcionalidad, no por par. Lo que no decide: nada de "Decisiones
cerradas" ni de "Riesgo"; si el código pide algo distinto, frena.

Para cada ticket:

1. Lanzá `ejecutor` con: **ruta absoluta de cada worktree**, ruta de la spec,
   número de ticket, qué tickets están hechos, cómo se cargan las variables de
   los tests y, si es de interfaz, la ruta absoluta de `impeccable` en el
   worktree del front. Sin `model` ni `effort`. **La spec escrita es la única
   fuente de verdad**: si falta una decisión, primero al archivo, después el
   agente.
2. El ejecutor lee la spec entera, explora el código del ticket, hace los
   pares pegando las dos salidas de cada uno y, antes de devolver, **busca con
   Grep lo que su cambio rompe** (símbolos, rutas o tablas que cambia o borra,
   en `tests/`, `scripts/`, `docs/`, `migrations/` y el otro repo) y corre los
   tests guardianes de lo que tocó.
3. Cuando vuelva, leé el reporte: cada par con **las dos salidas** (el test
   fallando y el test pasando) y los criterios de aceptación tildados. Si falta
   un rojo, el par no está hecho: lo reanudás con `SendMessage` pidiéndolo.
4. **Verificás con el reporte y `git diff --stat`**: que tocó lo que dice y
   nada más, y que los números cierran. **No re-corras los tests por rutina**:
   sólo si algo no cuadra (archivos de más, conteos que no coinciden, salida
   sospechosa). Ahí sí los corrés vos y, si difiere, lo reanudás con lo que
   viste.
5. Según el encabezado: **HECHO** → siguiente ticket. **FRENADO** → la
   pregunta al usuario tal cual, con aviso; al responder, **reanudá al mismo
   agente con `SendMessage`**, no lo relances. **SPEC ROTA** (la spec choca con
   el código: una premisa falsa, algo que ya existe distinto, un ticket
   anterior que figura hecho y no lo está) → frená, corregí la spec o
   preguntá.
6. **Si el corte salió mal** (un ticket no le entra en la sesión o depende de
   algo que no está hecho), el ejecutor vuelve FRENADO. Partís o reordenás el
   ticket en la spec y **se lo mostrás al usuario antes de seguir**, porque
   cambió lo que aprobó.
7. Respetá el corte en PRs que marcó la spec: si toca los dos repos, PRs
   hermanos en el backend y en el frontend.

### Tickets en paralelo

Sólo los que la spec aprobada marca "En paralelo con"; nunca se decide en el
momento.

1. **Cada uno en su propio worktree y su propia rama**, cortada de la rama de
   la tarea; nunca dos ejecutores en la misma carpeta. Se lanzan en el mismo
   mensaje.
2. El que crea la migración (a lo sumo uno) es el único que la toca; el DDL en
   `testing` sigue siendo tuyo, con OK, y no se aplica mientras el otro ticket
   esté corriendo contra esa base.
3. **Al volver los dos**, verificás cada reporte como siempre y juntás las
   ramas en la de la tarea, una por vez. Si el merge da conflicto, la spec se
   equivocó: no lo resolvés a ciegas; si toca lógica de los dos tickets,
   frenás y se lo mostrás al usuario.
4. Después del merge corrés **la suite completa una vez** (cada ejecutor sólo
   corrió lo de su ticket) y recién ahí sigue el próximo ticket o la Fase 4.
5. Si uno vuelve FRENADO o SPEC ROTA, el otro sigue; lo frenado se resuelve
   antes de juntarlos.
6. Los worktrees de cada ticket se borran al juntar las ramas (en el front,
   `cmd /c rmdir node_modules` antes).

**Al avanzar** (etapa cerrada, revisión terminada, pausa), la sesión principal
actualiza en `docs/estado.md` la fase y el próximo paso, en el checkout
principal del backend (nunca en el worktree). El ejecutor no lo toca.

**Lo que el ejecutor no hace y queda para vos**, con OK explícito del usuario:
`git commit`, ramas, PRs, merge, deploy y todo DDL contra `preliquidacion`
(producción). Un paso de esos vuelve como FRENADO con sentencia, backup y
rollback. Toda DDL va primero a `testing`, que es compartida con otros
sistemas: sólo se tocan nuestras tablas, nunca un drop general. Las migraciones
van en el mismo PR que el código que las necesita.

El archivo de la spec lo editás **sólo vos**; si cambió durante la ejecución,
actualizalo para que refleje lo que se hizo.

### Carril corto: ejecutás vos, en sesión

Mismas reglas, sin agente: par por par, **test rojo primero y pegá la salida**,
después verde, spec del área y build. Frená si el plan estaba equivocado o algo
te bloquea. No intentes lo mismo cinco veces.

## Fase 4 — Revisión ⏸

En los dos carriles, **en este orden y una sola pasada**:

1. **Suite completa y build, UNA vez**, cuando terminaron todos los tickets (o pasos).
   Pegá los números reales. **Distinguí regresión de flaky**: un test que
   falla se corre aislado; si pasa solo y es de un área ajena, es flaky y se
   anota, no se persigue.
2. **`revision-codigo`** (no el `code-review` incluido en Claude Code) sobre el diff contra el punto de partida. La skill lanza
   los revisores (completo: dos ejes en paralelo; corto: un solo agente con
   los dos ejes) y después el **`verificador-review`**, que comprueba cada
   hallazgo contra el código, tira los falsos y etiqueta el resto
   `urgent` / `high` / `minor`.
3. Regla mecánica: **`urgent` y `high` se arreglan; `minor` se listan en el
   PR y no se tocan.** Cómo se arreglan, **sin intervención del usuario**:
   - Cada `urgent`/`high` pasa a ser un **paso nuevo de la spec** ("Paso R1,
     R2…") que agregás vos al archivo, con el hallazgo, el escenario de
     falla y el arreglo mínimo que trajo el verificador. Queda registrado
     por qué se tocó.
   - Arreglo de **hasta 2 archivos de código**: va como un **par** (test
     que reproduce el escenario de falla en rojo → arreglo → verde). Carril
     completo: lo hace el `ejecutor`; carril corto: vos en sesión. El
     verificador ya dijo qué y dónde.
   - Arreglo **más grande**, o el verificador dice que el problema es de
     diseño: lo escribís vos como **ticket nuevo** en la spec. **Acá sí
     frenás** para el OK del usuario, porque cambió el alcance.
   - Un `urgent` cuyo arreglo **contradice una decisión aprobada** (regla de
     negocio, alcance): frenás y consultás. Es la única otra intervención
     del usuario en esta fase.
4. Después de arreglar: **spec tocado + build**. Suite completa otra vez solo
   si el arreglo tocó más de un archivo de código.
5. **Rondas**: corto, **una**. Completo, **una**; **dos** si el diff toca
   las zonas sensibles (la segunda ronda revisa solo los arreglos). Solo docs
   o comentarios: **ninguna**. Zonas sensibles de este sistema:
   - **Motor de reglas y cálculo de importes**:
     `app/modulos/preliquidacion/services/motor_reglas.py` y
     `app/modulos/preliquidacion/services/preliquidacion_service.py`.
   - **Maestro de conceptos y precios**:
     `app/modulos/preliquidacion/api/precios.py`.
   - **Exportación a sueldos**:
     `app/modulos/preliquidacion/services/export_service.py` (y su ruta,
     `app/modulos/preliquidacion/api/export.py`).
   - **Autenticación, roles y permisos de módulos**: `app/core/auth.py`,
     `app/core/permisos.py`, los `permisos.py` de cada módulo, y en el front
     `src/core/authStore.js` y `src/core/permisos.js`.
   - **Migraciones y DDL**: `migrations/` y los `models.py` (`app/core/` y
     cada módulo).

   Los controles de lectura y las pantallas, con **una** ronda.
6. **Evidencia antes de afirmar.** No digas "pasa", "arreglado" ni "listo"
   sin haber corrido en esta misma fase el comando que lo prueba y leído su
   salida completa: conteo de tests, exit code, build. Si no lo corriste, decí
   que no está verificado.

Mostrá el resultado en una línea: "revisión: N urgent, N high arreglados, N
minor sin tocar". Mandá aviso si algo necesita su decisión (completo).

## Fase 5 — Entrega ⏸

1. **Mostrar el cambio al usuario y esperar su OK** antes del PR. Si lo quiere
   probar, levantá la app en local desde el worktree, contra `testing` (ver
   _Configuración en el worktree_).
2. Rama → commits con `/commit` → PR **bien comentado** (qué, por qué y qué se
   descartó, verificación, qué pasa después, rollback; el cuerpo del PR es la
   única fuente del porqué que archiva la bitácora), siempre con
   `--body-file`, nunca inline. Si la tarea toca los dos repos, **PRs hermanos**
   en el orden que marque la spec. Merge con OK: `main` exige una aprobación y
   no se puede auto-aprobar, así que va `gh pr merge N --merge --admin`.
3. Deploy **solo si lo pidió explícitamente**: mergear a `main` no es
   deployar, y el sistema está en producción. Con el par del otro repo si
   hubo cambio de API. El detalle del deploy va en `docs/DEPLOY.md` (local,
   fuera de git) y la bitácora lleva una **entrada de deploy aparte**, sin
   datos del servidor.
4. **Anotar el cierre**: después de cada merge, corré `/bitacora` sin
   preguntar (`AGENTS.md`, "Bitácora y estado"). El agente
   `bitacora` escribe la entrada **al final** de `docs/BITACORA.md` (la más
   nueva abajo) y **saca la tarea de `docs/estado.md`** (si dejó algo
   pendiente, por ejemplo el smoke del usuario, queda sólo eso, en una línea).
   Commiteás **los dos juntos a `main`**, en el checkout principal del
   backend, con `/commit`, sin push: el push de `main` espera el OK del
   usuario. Si hubo deploy, su entrada va aparte. Al avisar que quedó
   anotado, nombrá los archivos.

---

## Avisos

Usá `PushNotification` cuando el trabajo **queda frenado esperando al usuario**
y hay chance de que se haya ido. Si está mirando la terminal, la herramienta lo
omite sola.

| Momento                        | Ejemplo                                                              |
| ------------------------------ | -------------------------------------------------------------------- |
| Spec lista (completo)          | `Spec lista: 5 tickets, 1 riesgo alto (migración). Espera tu OK.`    |
| Pregunta que bloquea           | `Frenado en el ticket 3: decidir si la baja es lógica o real.`       |
| Tests en rojo que no resolvés  | `Build en rojo: 2 tests de auth fallan y no es flaky.`               |
| La revisión encontró un urgent | `Revisión: 1 urgent en permisos de módulos. Espera tu decisión.`     |
| Cambio listo para el PR        | `Listo para revisar: 6 archivos, 85 tests. Espera tu OK para el PR.` |

**No avises** de progreso rutinario, ni en el carril corto salvo que algo se
trabe. Una línea, menos de 200 caracteres, sin markdown, arrancando por lo
accionable.
