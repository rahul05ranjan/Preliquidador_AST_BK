# "A futuro" pasa a issues de GitHub (carril corto)

**Qué se pide.** Lo pospuesto, la deuda y los minors de las revisiones dejan de vivir en "A
futuro" de `docs/estado.md` y pasan a issues de GitHub, como fuente única. `estado.md` queda
con "En curso", "Próximo paso" y "Pendientes del usuario", más una línea que dice dónde están
los issues. Lo del servidor no va a issues (los repos son públicos): pasa a "Pendientes del
usuario" y sigue detallado en `docs/DEPLOY.md`.

**Decisiones.**
1. Cada issue va al repo donde está el código (decisión del usuario; descartado: un solo
   tablero en el backend). Lo que toca los dos repos lleva un issue en cada uno, y cada uno
   nombra a su hermano. El PR que lo arregla lo cierra con `Closes #N`.
2. Un issue por tanda de minors (la de cada revisión), con los minors de su PR y el enlace a
   él; un issue por cada bug o deuda suelta.
3. Etiquetas, iguales en los dos repos: tipo (`bug`, `prolijidad`, `accesibilidad`, `mejora`,
   `proceso`) y área (`facturación`, `preliquidación`, `terceros`, `núcleo`).
4. Lo descartado ("se agrega si aparece un caso") va como issue cerrado como no planificado:
   queda buscable y se reabre si hace falta.
5. Cada issue lleva el texto que ya era público en `estado.md`: sin IPs, hosts, credenciales,
   datos de terceros ni nombres de clientes.

**Archivos.**
- Issues y etiquetas en GitHub, con `gh` y `--body-file`.
- `AGENTS.md` de los dos repos (bloque común idéntico): la tabla "Dónde se anota cada cosa" y
  "Estado del trabajo". PRs hermanos.
- `.claude/skills/flujo-preliquidacion/SKILL.md`, `.claude/agents/bitacora.md` y un
  `docs/agents/issue-tracker.md` nuevo (cómo se crean, etiquetan y cierran los issues; la
  skill `revision-codigo` lo busca ahí).
- Fuera de los repos, con OK: la skill global `revision-codigo` (los minors al PR y a un
  issue) y la memoria `limpieza-codigo-a-futuro`.
- `docs/estado.md`, directo a `main`, al final.

**Verificación.** `gh issue list` muestra los issues con sus etiquetas, uno por cada ítem de
"A futuro". El chequeo del bloque común de `AGENTS.md` pasa en el `pre-commit` de los dos repos.
Ningún "A futuro" queda nombrado en reglas, skills ni agentes.
