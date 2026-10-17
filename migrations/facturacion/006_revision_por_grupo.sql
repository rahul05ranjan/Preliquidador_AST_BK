-- facturacion/006 — La Revisión de diferencia pasa a grupos de tareas y suma su período (E3a por grupo).
-- NO DIFERIBLE: va con el deploy de esta versión, ANTES de reiniciar el backend, como la 004. El
-- arranque compara el modelo con la base, y el código de esta versión lee y escribe el período y
-- los grupos. Desde que se aplica, el código anterior falla al leer Revisiones.
-- Orden: en ORDEN.txt va después de la 005 (004, 005, 006), que es el orden de una base nueva. En
-- una base que no tiene ninguna de las tres (producción), la 004 y la 006 van antes del reinicio y
-- la 005 después. Que la 004 cree la tabla por tarea y la 006 la borre en el mismo deploy no hace
-- daño.
-- Idempotente: se puede correr dos veces. Lo que depende de lo que ya hay en la base (sumar las
-- columnas, cambiar el índice) se decide leyendo information_schema y va por PREPARE. El resto
-- es IF NOT EXISTS, IF EXISTS o no cambia nada la segunda vez.
--
-- Una Revisión guarda ahora las (grupo, unidad) que superaban, y el período en que se dejó (desde
-- y hasta, los dos incluidos, dentro del mes). Cubre sólo ese período exacto. Las que ya existen
-- quedan con el mes entero. Se siguen guardando todas, con quién revisó y quién deshizo: la que
-- vale es la más reciente no deshecha de ese período. Las (tarea, unidad) que guardaban las
-- Revisiones por tarea no se pasan a grupos: se pierden con la tabla (respaldarla antes).
--
-- Vuelta atrás (sólo si se vuelve al código anterior), en este orden, y recién después el código:
-- DROP TABLE facturacion_revision_grupo
-- ALTER TABLE facturacion_revision DROP INDEX ix_facturacion_revision_cliente_mes_periodo, ADD INDEX ix_facturacion_revision_cliente_mes (cliente_id, mes), DROP COLUMN desde, DROP COLUMN hasta
-- Correr de nuevo la 004, que crea facturacion_revision_tarea vacía (las otras dos tablas ya
-- están y no las toca), y cargar sus filas del respaldo tomado antes de esta migración.


-- 1. Una (grupo, unidad) que superaba cuando se dejó la Revisión.
CREATE TABLE IF NOT EXISTS facturacion_revision_grupo (
    id                INT            AUTO_INCREMENT PRIMARY KEY,
    revision_id       INT            NOT NULL,
    -- El grupo de tareas del maestro del campo, como se leyó. NULL = Sin grupo.
    grupo             VARCHAR(255)   NULL,
    -- Una de las claves de app/modulos/facturacion/unidades.py, como en
    -- facturacion_linea. NULL = la línea no tenía unidad.
    unidad            VARCHAR(20)    NULL,
    KEY ix_facturacion_revision_grupo_revision (revision_id),
    CONSTRAINT fk_facturacion_revision_grupo_revision FOREIGN KEY (revision_id)
        REFERENCES facturacion_revision (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- 2. Sale la tabla por tarea.
DROP TABLE IF EXISTS facturacion_revision_tarea;


-- 3. El período de la Revisión: se suma con NULL, se llena con el mes entero y
--    recién ahí pasa a obligatorio.
SET @falta_periodo := (
    SELECT COUNT(*) = 0 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'facturacion_revision'
      AND COLUMN_NAME = 'desde'
);
SET @sentencia := IF(@falta_periodo,
    'ALTER TABLE facturacion_revision ADD COLUMN desde DATE NULL AFTER mes, ADD COLUMN hasta DATE NULL AFTER desde',
    'DO 0');
PREPARE paso FROM @sentencia;
EXECUTE paso;
DEALLOCATE PREPARE paso;

UPDATE facturacion_revision SET desde = mes, hasta = LAST_DAY(mes)
WHERE desde IS NULL OR hasta IS NULL;

ALTER TABLE facturacion_revision
    MODIFY COLUMN desde DATE NOT NULL,
    MODIFY COLUMN hasta DATE NOT NULL;


-- 4. El índice (no único) pasa de (Cliente, mes) a (Cliente, mes, período).
SET @falta_indice := (
    SELECT COUNT(*) = 0 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'facturacion_revision'
      AND INDEX_NAME = 'ix_facturacion_revision_cliente_mes_periodo'
);
SET @sentencia := IF(@falta_indice,
    'ALTER TABLE facturacion_revision ADD INDEX ix_facturacion_revision_cliente_mes_periodo (cliente_id, mes, desde, hasta)',
    'DO 0');
PREPARE paso FROM @sentencia;
EXECUTE paso;
DEALLOCATE PREPARE paso;

SET @hay_indice_viejo := (
    SELECT COUNT(*) > 0 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'facturacion_revision'
      AND INDEX_NAME = 'ix_facturacion_revision_cliente_mes'
);
SET @sentencia := IF(@hay_indice_viejo,
    'ALTER TABLE facturacion_revision DROP INDEX ix_facturacion_revision_cliente_mes',
    'DO 0');
PREPARE paso FROM @sentencia;
EXECUTE paso;
DEALLOCATE PREPARE paso;
