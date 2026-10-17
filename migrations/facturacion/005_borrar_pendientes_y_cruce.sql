-- facturacion/005 — Borra los permisos guardados de las pantallas retiradas `pendientes` y `cruce`.
-- NO DIFERIBLE: va con el deploy de esta versión, DESPUÉS de reiniciar el backend. El código
-- anterior todavía declara esas pantallas, y el de esta versión ya no (las reemplaza Resumen).
-- Idempotente: si los permisos ya no están, no hace nada.
-- Toca rol_permiso, que es del núcleo: excepción a la regla 6 de GUIA-MODULOS.md, ver el plan
-- docs/superpowers/plans/2026-10-14-facturacion-e3.md (decisión 1). Las claves `pendientes` y
-- `cruce` se retiraron y no se reutilizan, y sus permisos no tienen que quedar guardados. No se
-- copian a `resumen`: el Admin suma Resumen al rol que corresponda.
-- Vuelta atrás (sólo si se vuelve al código anterior): reinsertar en rol_permiso las filas
-- (rol_id, modulo, pantalla, nivel) del respaldo tomado antes de esta migración, con el
-- pre-check de esa base (F1 en testing, F7 en producción). Recién después se vuelve el código.

DELETE FROM rol_permiso WHERE modulo = 'facturacion' AND pantalla IN ('pendientes', 'cruce');
