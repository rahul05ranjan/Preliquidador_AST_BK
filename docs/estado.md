# Estado del trabajo

Sólo lo vivo: lo que está en curso, el próximo paso y lo que espera al usuario.
Lo entregado no va acá: su cierre está en `docs/BITACORA.md` (la más nueva abajo). Lo pospuesto, la
deuda y los minors de las revisiones están en los issues de GitHub de cada repo
(`docs/agents/issue-tracker.md`). La regla está en `AGENTS.md` ("Estado del trabajo"). Última
actualización: **2026-10-21**.

## En curso

- Nada en curso.

## Próximo paso

Todo deploy, con OK. Facturación se deploya por avances, escondida: nadie tiene su rol
(2026-10-13).

## Pendientes del usuario

- Facturación: borrar del servidor el respaldo de la `facturacion/007` cuando ya no haga falta como vuelta atrás (deploy del 2026-10-20).
- Facturación: borrar del servidor el respaldo de `rol_permiso` de la `facturacion/005` cuando ya no haga falta como vuelta atrás (deploy del 2026-10-17).
- Terceros, etapa 11 de Pitu (BK #101 y FT #82): revisados el 2026-10-15, con la revisión dejada como comentario en los dos PRs (3 urgent y 10 high). No se mergean hasta que Pitu los arregle. El FT #82, además, espera la decisión del usuario sobre la dependencia `html2pdf.js`. Antes del deploy, confirmar en producción lo que da por hecho la migración `terceros/010`.
- Cargar `TALLER_SHEET_URL` en el `.env` del servidor y reiniciar el backend: hasta entonces las alertas de Terceros responden 502 a propósito (deploy del 2026-09-30).
- Asignar el rol "Liquidador de terceros" desde Administración a quienes liquiden Terceros (nace sin personas; BK #83, deploy del 2026-10-11).
- Avisarle a Pitu que sumar las tablas `terceros_*` a `TABLAS` de `scripts/refrescar_testing.py` queda para él: el próximo refresco de `testing` pisaría sus datos de prueba de Terceros con los de producción (el usuario lo decidió así, 2026-10-11).
- De Pitu, también para el usuario: reinstalar los hooks en su clon del backend (`sh scripts/hooks/instalar.sh`); hasta entonces su `pre-commit` frena `docs/estado.md` en `main` (BK #72, 2026-10-05).
- De Pitu, también para el usuario: la aceptación de la etapa 7 de Terceros (agosto igual a la liquidación a mano) y la revisión de código de dos ejes del BK #59 (2026-09-30).
- Facturación: definir el respaldo de la carpeta de adjuntos del VPS (ya existe en producción desde el deploy del 2026-10-13), junto con el de la base que ya estaba pendiente en `docs/DEPLOY.md` (ADR-0019, BK #78).
- Facturación: los adjuntos del front (FT #80) no se probaron con un usuario de sólo Ver en `comprobantes`, porque no hay uno así en `testing` (2026-10-13).
- Facturación: borrar del servidor el respaldo de la `facturacion/002` cuando ya no haga falta como vuelta atrás (deploy del 2026-10-12).
- Avisarle a Pitu que la subida de archivos de las estaciones de Terceros (`subirArchivoEstacion` en `src/modulos/terceros/services/terceros.js` del front) probablemente manda JSON en vez del archivo: la instancia `api` del núcleo trae `Content-Type: application/json` por defecto y, con ese header, axios convierte el FormData en JSON. En Facturación pasó lo mismo y se arregló pasando `multipart/form-data` explícito (FT-B). No se probó en su pantalla (2026-10-13).
- Avisarle a Pitu que haga pull de `main` en los dos repos: `testing` ya no tiene la tabla de la Unidad sugerida, y un `main` anterior al BK #94 arranca contra `testing` avisando que faltan tablas (2026-10-12).
- Facturación: revisar en la app de campo las tareas facturables que quedan Sin definir (la Unidad sugerida ahora se define allá; BK #94).
- Facturación: el smoke del histórico en producción (F8 del plan de la E2): que el listado de Comprobantes cargue con los 353 históricos y uno abra en sólo lectura. Hace falta entrar con un usuario real. El primer adjunto real lo sube el usuario (deploy del 2026-10-13).
- Facturación: borrar del servidor el respaldo de la Factura de prueba 0000, ya borrada de la base, cuando no haga falta (deploy del 2026-10-13).
- Facturación: el rol de las contadoras ya existe en producción; no asignarlo a nadie hasta que esté la primera versión completa del módulo (decisión del usuario, 2026-10-12). Al asignarlo, probar una subida real de adjunto: en el deploy del 2026-10-13 no se pudo, porque nadie tiene el rol.
- Facturación: corregir en la planilla del histórico 3 Comprobantes que quedaron afuera (una UM vacía, dos FECHA FAC distintas en un mismo Comprobante y un precio ilegible) para sumarlos con otra corrida del script (BK #99, 2026-10-13).
- Facturación: las tareas de cosecha que no están en el maestro del campo quedaron migradas con tarea 0 y su nombre; hablar con el personal que carga en el campo y, cuando el campo las tenga, una corrida con `--reemplazar-cambiados` las pasa a su id (BK #99, 2026-10-13).
- Avisarle a Pitu que las etiquetas de aviso del núcleo (`.badge-*`) pasan a texto oscuro con el tono en el fondo y el borde, también en Terceros (Tarifario, "sin confirmar"); ya se ve en el sitio (deploy del 2026-10-09).
- Avisarle a Pitu que el esquema nuevo de permisos ya está en producción (BK #83 y #86, FT #70; deploy del 2026-10-11): el glosario de Terceros suma sus cinco pantallas con qué es ver y editar; Terceros declara `PANTALLAS` en `app/modulos/terceros/permisos.py`; cada ruta pide pantalla y nivel (salen `requiere_operativo` y `requiere_gerencial`); cada ruta de `src/modulos/terceros/rutas.jsx` nombra su pantalla; sus tests usan el rol "Liquidador de terceros". Que confirme las filas 25 y 28 del plan y qué pantallas usan `ver_inicio_o_quincena`, y que rebase sus ramas abiertas sobre `terceros.py`.
- Servidor (detalle en `docs/DEPLOY.md`, local), todo con OK porque toca el servidor: dejar una sola
  configuración de nginx, la activa con HTTPS y el límite de 12 MB, para que una reinstalación no los
  pierda; y borrar los respaldos viejos que ya no sirvan de vuelta atrás, primero la copia de la
  configuración del sistema del 2026-09-30, que puede tener contraseñas (visto en el deploy del
  2026-10-13; el usuario lo dejó para más adelante).
