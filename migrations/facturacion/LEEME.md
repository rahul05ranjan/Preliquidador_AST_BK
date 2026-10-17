Migraciones del módulo Facturación. Tablas con prefijo `facturacion_`.

- `001_unidad_por_tarea.sql`: creó `facturacion_tarea`, con la Unidad sugerida y la marca No facturable de cada tarea (E1).
- `002_borrar_unidad_por_tarea.sql`: borra esa tabla y los permisos guardados de la pantalla `unidad`, porque la Unidad
  sugerida se lee del sistema de campo (2026-10-12).
- `003_comprobantes.sql`: crea los Comprobantes, sus Líneas y sus Adjuntos (E2).
- `004_resumen.sql`: crea la configuración del Resumen (Umbral y Mes de corte) y la Revisión de diferencia con sus
  tareas (E3).
- `005_borrar_pendientes_y_cruce.sql`: borra los permisos guardados de las pantallas retiradas `pendientes` y
  `cruce`, que reemplaza Resumen (2026-10-14).
- `006_revision_por_grupo.sql`: la Revisión de diferencia pasa a guardar las (grupo, unidad) que superaban, en
  `facturacion_revision_grupo`, y su período (Desde y Hasta); borra `facturacion_revision_tarea` y cambia el índice
  de (Cliente, mes) por uno de (Cliente, mes, Desde, Hasta). Va antes de reiniciar el backend; en producción, la 004
  y la 006 antes del reinicio y la 005 después (2026-10-17).

Cada archivo nuevo se agrega al final de `migrations/ORDEN.txt` en el mismo PR (un test lo verifica). Las líneas
comentadas no llevan `;`: el aplicador corta el archivo por `;` y lo que siga quedaría sin `--`. Probar en `testing`; a
producción las aplica Gero con el deploy.
