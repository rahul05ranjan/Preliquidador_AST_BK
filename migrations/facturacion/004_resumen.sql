-- facturacion/004 — La configuración del Resumen y la Revisión de diferencia con sus tareas (E3).
-- NO DIFERIBLE: va con el deploy de esta versión, ANTES de reiniciar el backend. El arranque
-- compara el modelo con la base, y el código de esta versión las lee y las escribe.
-- Aplicar UNA vez por base. Idempotente: si una tabla ya existe, no hace nada.
--
-- La configuración es una sola fila (id 1) con el Umbral y el Mes de corte.
-- Nace vacía: sin fila, el servicio usa los valores iniciales de config.py, y
-- el primer cambio del Admin la crea. Así los valores iniciales viven en un
-- solo lugar.
--
-- Una Revisión de diferencia es de un Cliente y un mes, y guarda las (tarea,
-- unidad) que superaban el Umbral cuando se dejó. Deshacerla no la borra: se
-- sellan deshecha_en y deshecha_por, y queda en el registro. Sus tareas caen
-- con ella (ON DELETE CASCADE).
--
-- Vuelta atrás (sólo si no hay datos reales, el código viejo convive con las tablas),
-- en este orden. Con datos reales, restaurar el respaldo tomado antes.
-- DROP TABLE facturacion_revision_tarea
-- DROP TABLE facturacion_revision
-- DROP TABLE facturacion_configuracion

CREATE TABLE IF NOT EXISTS facturacion_configuracion (
    -- Siempre 1: sin AUTO_INCREMENT a propósito.
    id                INT            NOT NULL PRIMARY KEY,
    -- Porcentaje: 5.00 es 5 %.
    umbral_pct        DECIMAL(5, 2)  NOT NULL,
    -- El día 1 del mes de corte.
    mes_corte         DATE           NOT NULL,
    actualizado_en    DATETIME       NOT NULL,
    actualizado_por   INT            NULL,
    CONSTRAINT fk_facturacion_configuracion_actualizado_por FOREIGN KEY (actualizado_por)
        REFERENCES usuarios (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE IF NOT EXISTS facturacion_revision (
    id                INT            AUTO_INCREMENT PRIMARY KEY,
    -- El id del maestro de clientes del sistema de campo.
    cliente_id        INT            NOT NULL,
    -- El día 1 del mes.
    mes               DATE           NOT NULL,
    comentario        VARCHAR(500)   NOT NULL,
    creada_en         DATETIME       NOT NULL,
    creada_por        INT            NULL,
    -- NULL = vigente, nadie la deshizo.
    deshecha_en       DATETIME       NULL,
    deshecha_por      INT            NULL,
    KEY ix_facturacion_revision_cliente_mes (cliente_id, mes),
    CONSTRAINT fk_facturacion_revision_creada_por FOREIGN KEY (creada_por)
        REFERENCES usuarios (id) ON DELETE SET NULL,
    CONSTRAINT fk_facturacion_revision_deshecha_por FOREIGN KEY (deshecha_por)
        REFERENCES usuarios (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- Una (tarea, unidad) que superaba cuando se dejó la Revisión.
CREATE TABLE IF NOT EXISTS facturacion_revision_tarea (
    id                INT            AUTO_INCREMENT PRIMARY KEY,
    revision_id       INT            NOT NULL,
    -- El id de la tarea en el sistema de campo.
    tarea_id          INT            NOT NULL,
    -- Una de las claves de app/modulos/facturacion/unidades.py, como en
    -- facturacion_linea. NULL = la tarea no tenía unidad.
    unidad            VARCHAR(20)    NULL,
    KEY ix_facturacion_revision_tarea_revision (revision_id),
    CONSTRAINT fk_facturacion_revision_tarea_revision FOREIGN KEY (revision_id)
        REFERENCES facturacion_revision (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
