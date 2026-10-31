SELECT data->>'cosecha_id' AS cosecha_id, data->'productor'->>'id' AS productor_id,
       (data->'resultado'->>'total_kg')::numeric AS total_kg
FROM cosechas
WHERE data->'resultado'->>'estado' = 'finalizada'
  AND (data->>'fecha')::timestamptz >= '2026-01-01 00:00:00Z'
ORDER BY (data->'resultado'->>'total_kg')::numeric DESC
LIMIT 1000;
