-- facturacion/007 — El Comprobante suma su Período facturado (Desde y Hasta) (E3b).
-- NO DIFERIBLE: va con el deploy de esta versión, ANTES de reiniciar el backend. El código de
-- esta versión lee y escribe el período, y el código anterior no nota las columnas nuevas.
-- No es idempotente: el ALTER falla si las columnas ya existen. El pre-check lo confirma antes.
-- Los dos UPDATE sí se pueden correr dos veces: sólo tocan lo que todavía no tiene período o
-- las Líneas cuya fecha no es todavía el Desde.
--
-- El Período facturado lo elige quien carga, dentro de un mismo mes, y el cruce cuenta cada
-- Línea con él. Un histórico queda sin período y se sigue contando por la quincena de la
-- fecha de cada Línea. Los cargados a mano antes de esta versión se llenan con las quincenas
-- de sus Líneas: todas en la 1.ª, del 1 al 15, todas en la 2.ª, del 16 a fin de mes, y en
-- las dos, el mes entero. Después, la fecha de esas Líneas pasa al Desde, como la guarda el
-- código nuevo. La fecha de cabecera queda como estaba y desde ahora se lee como Fecha de carga.
--
-- Pre-check, antes de correrla:
-- 1. Las columnas no existen (tiene que dar 0 filas):
--    SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'facturacion_comprobante' AND COLUMN_NAME IN ('periodo_desde', 'periodo_hasta')
-- 2. Cuántos cargados a mano hay (todos quedan sin período hasta el UPDATE):
--    SELECT COUNT(*) FROM facturacion_comprobante WHERE es_historico = 0
-- 3. Cuáles tienen Líneas en dos meses (tiene que dar 0 filas. Si da alguna, se frena y se
--    consulta al usuario: el UPDATE los deja sin período):
--    SELECT l.comprobante_id, MIN(l.fecha), MAX(l.fecha) FROM facturacion_linea l JOIN facturacion_comprobante c ON c.id = l.comprobante_id WHERE c.es_historico = 0 GROUP BY l.comprobante_id HAVING LAST_DAY(MIN(l.fecha)) <> LAST_DAY(MAX(l.fecha))
--
-- Respaldo, antes de correrla: las filas de los cargados a mano en facturacion_comprobante
-- (es_historico = 0) y sus Líneas en facturacion_linea. El UPDATE de las Líneas pisa su fecha
-- original, que sólo queda en el respaldo.
--
-- Vuelta atrás (sólo si se vuelve al código anterior), en este orden, y recién después el código:
-- devolver la fecha de las Líneas de los cargados a mano desde el respaldo (por id)
-- ALTER TABLE facturacion_comprobante DROP COLUMN periodo_desde, DROP COLUMN periodo_hasta


-- 1. Las dos columnas, vacías. Un histórico no tiene período.
ALTER TABLE facturacion_comprobante
    ADD COLUMN periodo_desde DATE NULL AFTER fecha,
    ADD COLUMN periodo_hasta DATE NULL AFTER periodo_desde;


-- 2. El período de los cargados a mano, por las quincenas de sus Líneas. Uno con Líneas en dos
--    meses no se llena (el pre-check lo frena antes).
UPDATE facturacion_comprobante c
JOIN (
    SELECT comprobante_id,
           DATE_SUB(MIN(fecha), INTERVAL DAY(MIN(fecha)) - 1 DAY) AS mes,
           MIN(DAY(fecha)) <= 15 AS hay_primera,
           MAX(DAY(fecha)) >= 16 AS hay_segunda
    FROM facturacion_linea
    GROUP BY comprobante_id
    HAVING LAST_DAY(MIN(fecha)) = LAST_DAY(MAX(fecha))
) l ON l.comprobante_id = c.id
SET c.periodo_desde = CASE WHEN l.hay_primera THEN l.mes ELSE l.mes + INTERVAL 15 DAY END,
    c.periodo_hasta = CASE WHEN l.hay_segunda THEN LAST_DAY(l.mes) ELSE l.mes + INTERVAL 14 DAY END
WHERE c.es_historico = 0 AND c.periodo_desde IS NULL;


-- 3. La fecha de sus Líneas pasa al Desde, como la guarda el código nuevo: la consulta por mes
--    del cruce y su índice siguen sirviendo.
UPDATE facturacion_linea l
JOIN facturacion_comprobante c ON c.id = l.comprobante_id
SET l.fecha = c.periodo_desde
WHERE c.es_historico = 0 AND c.periodo_desde IS NOT NULL
  AND l.fecha <> c.periodo_desde;
