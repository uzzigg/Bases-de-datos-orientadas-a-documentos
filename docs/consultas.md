# Consultas y validación funcional

Las consultas siguen el manual: Q1 desanida `items`, filtra precio mayor a 50
y agrupa por país/categoría; Q2 selecciona completadas desde 2026-01-01 UTC y
obtiene las primeras 1,000 por `payment.final_total` descendente. Los tiempos
son cadenas ISO-8601 UTC uniformes en MongoDB y JSONB; PostgreSQL usa el cast
del manual. No se añadió un índice sobre el total ni un desempate secundario.

- `queries/mongo_q1.json`, `queries/mongo_q2.json`: pipelines para PyMongo.
- `queries/postgres_q1.sql`, `queries/postgres_q2.sql`: SQL.
- `scripts/validar_consultas.py`: resultados y planes de ejecución para ambos.

Las opciones de memoria se pasan por operación/conexión: MongoDB Q1 con
`allowDiskUse=true`, Q2 con false y true; PostgreSQL Q1 con `work_mem=4MB`,
Q2 con 4MB y 64MB. Los valores de Q1 son decisiones documentadas del proyecto.

## Repetir validación

Con el dataset ya cargado y Docker Desktop activo, usar un nombre de corrida
nuevo (solo letras, números, guion y guion bajo). Se conserva la evidencia de
las anteriores; el script no sobrescribe archivos existentes.

```powershell
.\scripts\stack.ps1 -Action Up -Engine mongo -Profile A
.\Otros\venv\Scripts\python.exe scripts/validar_consultas.py mongo --run validacion_02
.\scripts\stack.ps1 -Action Up -Engine postgres -Profile A
.\Otros\venv\Scripts\python.exe scripts/validar_consultas.py postgres --run validacion_02
.\Otros\venv\Scripts\python.exe scripts/validar_consultas.py compare --run validacion_02
.\scripts\stack.ps1 -Action Stop
```

Los resultados completos y planes se guardan en `Otros/consultas/<run>/`. Los
planes se obtienen con `explain` verbosity `executionStats` en MongoDB y
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` en PostgreSQL. Ejecutar EXPLAIN con
estas opciones realiza la consulta; estas pruebas no son mediciones de la matriz.

Q1 compara todos los grupos, conteos y sumas exactos y promedios con tolerancia
absoluta de 1e-8. Q2 compara el orden y los 1,000 importes de las cuatro
variantes, los IDs y valores por encima del corte y los datos de los IDs comunes.
El manual no define desempate: cuando hay empates en el puesto 1000, algunos
IDs con el importe de corte pueden variar sin implicar resultados incorrectos.

## Primera validación con perfil A

Q1 obtuvo 20 grupos equivalentes. Q2 obtuvo 1,000 filas e importes equivalentes
en las cuatro variantes; importe del puesto 1000: 2719, con 998 filas por
encima del corte. Estos números describen el dataset de esta ejecución.

En el plan MongoDB de Q2 con disco permitido se observó `IXSCAN` sobre
`timestamp_1`, 249,767 documentos examinados, `usedDisk=false` y `spills=0`.
El plan PostgreSQL de Q2 con 4MB mostró `Seq Scan`, `top-N heapsort` y cero
bloques temporales leídos/escritos. Son observaciones de una ejecución de
validación con perfil A, no conclusiones generales de rendimiento ni prueba
de lo que ocurrirá bajo concurrencia. Los seis planes están en
`resultados/planes_validacion/`; el resumen funcional está en
`resultados/validacion_consultas.json`.

Referencias: [MongoDB explain](https://www.mongodb.com/docs/manual/reference/command/explain/)
y [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/18/sql-explain.html).
