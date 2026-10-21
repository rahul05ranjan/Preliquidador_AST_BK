# Issues de GitHub

Lo pospuesto, la deuda vista al pasar y los minors de las revisiones viven en issues de
GitHub, no en `docs/estado.md` (que queda sólo con lo vivo). Esta es la regla para crearlos,
etiquetarlos y cerrarlos. Vale para los dos repos.

## Dónde va cada issue

- **En el repo donde está el código**: `Gerorios/Preliquidador_AST_BK` (backend) o
  `Gerorios/Preliquidador_AST_FT` (frontend).
- **Si toca los dos repos**, un issue en cada uno, y cada uno nombra a su hermano en una
  línea: `Issue hermano: Gerorios/Preliquidador_AST_FT#N`.
- **Lo del servidor no va a issues**: los repos son públicos. Queda en "Pendientes del
  usuario" de `docs/estado.md` y su detalle en `docs/DEPLOY.md` (local).

## Qué lleva

- **Un issue por tanda de minors**: los de una revisión, con el enlace al PR que los
  trajo, como lista `- [ ]`. Si la revisión cubrió PRs hermanos, un issue por repo con los
  minors de su código.
- **Un issue por cada bug o deuda suelta**, con el escenario en que falla y dónde se vio.
- **Lo pospuesto**, con su porqué: quién lo decidió y cuándo.
- **Nada sensible**: sin IPs, hosts, credenciales, datos de terceros, nombres de clientes ni
  listados de tablas. El cuerpo va siempre desde archivo (`--body-file`).

## Etiquetas

Iguales en los dos repos. Una de tipo y una de área:

- **Tipo**: `bug` (algo que da mal), `prolijidad` (los minors de limpieza de código),
  `accesibilidad`, `mejora` (algo nuevo o una herramienta) y `proceso` (cómo se trabaja:
  CI, tests, scripts). `documentation` para lo que es sólo de docs.
- **Área**: `facturación`, `preliquidación`, `terceros` o `núcleo`.

## Cómo se cierran

- **El PR que lo arregla lo cierra** con `Closes #N` en el cuerpo (o
  `Closes Gerorios/Preliquidador_AST_BK#N` si el issue es del otro repo).
- **Lo descartado** ("se agrega si aparece un caso") se crea igual y se cierra como no
  planificado (`gh issue close N --reason "not planned"`), con su porqué: queda buscable y
  se reabre si hace falta.
- **Antes de proponer algo**, se buscan los issues del tema, abiertos y cerrados
  (`gh issue list --state all --search "<términos>"`), igual que la bitácora y los ADR.

## Comandos

```bash
gh issue create --repo Gerorios/Preliquidador_AST_BK --title "<título>" \
  --label prolijidad --label facturación --body-file <archivo>
gh issue view N --repo Gerorios/Preliquidador_AST_FT
gh issue list --repo Gerorios/Preliquidador_AST_BK --label bug
gh issue close N --repo Gerorios/Preliquidador_AST_FT --reason "not planned"
```

Dónde está `gh` en cada máquina va en su `CLAUDE.local.md`.
