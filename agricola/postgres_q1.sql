SELECT data->'productor'->'ubicacion'->>'country' AS pais,
       lote->>'cultivo' AS cultivo,
       SUM((lote->>'cajas')::numeric * (lote->>'kg_por_caja')::numeric) AS total_kg,
       AVG((lote->>'cajas')::numeric * (lote->>'kg_por_caja')::numeric) AS promedio_kg,
       COUNT(*) AS conteo
FROM cosechas, jsonb_array_elements(data->'lotes') AS lote
WHERE (lote->>'kg_por_caja')::numeric > 50
GROUP BY 1, 2;
