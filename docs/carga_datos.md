# Carga del dataset

## Preparación

Se requiere el dataset `Otros/dataset/orders.jsonl`, el manifiesto versionado
`resultados/dataset_manifest.json`, Docker Desktop y Python 3. Los controladores
están fijados en `requirements.txt`. En Windows:

```powershell
python -m venv Otros/venv
.\Otros\venv\Scripts\python.exe -m pip install -r requirements.txt
python scripts/verificar_dataset.py
```

Si el JSONL falta, `python synthetic_data_generator.py` lo genera; no sobrescribe
archivos existentes. Ambos cargadores calculan el SHA-256 del archivo completo
y comparan su tamaño y hash con el manifiesto antes de tocar las bases.

## Cargar motores por separado

```powershell
.\scripts\stack.ps1 -Action Up -Engine mongo -Profile A
.\Otros\venv\Scripts\python.exe scripts/cargar_datos.py mongo
.\scripts\stack.ps1 -Action Up -Engine postgres -Profile A
.\Otros\venv\Scripts\python.exe scripts/cargar_datos.py postgres
.\Otros\venv\Scripts\python.exe scripts/resumir_cargas.py
```

Los scripts leen credenciales de `.env` sin imprimirlas. MongoDB almacena en
`document_benchmark.orders`; PostgreSQL en `public.orders` de la base indicada
por `POSTGRES_DB`. Ambas cargas usan los mismos campos y valores JSON. El
identificador UUID se conserva en el JSON de ambos; PostgreSQL además lo guarda
como clave primaria UUID.

Por seguridad, si la colección o tabla `orders` ya existe, el script se detiene
sin modificarla. Si falla MongoDB durante una inserción por lotes, puede quedar
una carga parcial; hay que inspeccionarla y decidir explícitamente cómo
recuperarla. PostgreSQL efectúa creación, COPY, índices y validaciones dentro
de una transacción. No se borran tablas, colecciones ni volúmenes existentes.
Si existe un archivo de evidencia de carga para el motor, también se detiene.

MongoDB usa lotes de 2,000 documentos e índices `order_id_1` (único) y
`timestamp_1`. PostgreSQL crea clave primaria en id y `orders_timestamp_idx`
con B-Tree sobre `data->>'timestamp'`, y ejecuta ANALYZE. El JSON usa tiempos
UTC con formato fijo. La consulta SQL literal del manual convierte el texto
a timestamptz; que el índice exista no demuestra que dicha expresión lo use.
Eso se comprobará con EXPLAIN durante la validación de Q2.

Cada carga comprueba conteo total, conteo del filtro Q2 y diez documentos completos
seleccionados del archivo maestro. El resumen compara los valores y hashes de
origen registrados para ambos motores; estas muestras no prueban identidad
exhaustiva de todos los documentos. La carga y sus duraciones no son mediciones
de benchmark. Evidencia local detallada en `Otros/dataset/carga_*.json`.
