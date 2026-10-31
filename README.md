# Bases de datos orientadas a documentos

Experimento académico de comparación de MongoDB y PostgreSQL JSONB mediante
agregaciones sobre 500,000 órdenes, con límites de CPU y memoria en Docker.

## Estado

Fase 0: verificaciones previas realizadas. Docker Desktop, Ubuntu en WSL2,
cgroups v2, límites A/B/C, contadores de CPU y limpieza de caché comprobados.
La integración de telemetría y la viabilidad bajo carga requieren el piloto.

Fase siguiente: construir Docker Compose, monitoreo y consultas equivalentes.
Los comandos de ejecución se incorporarán cuando estén implementados y probados.

## Organización

- Código, consultas, configuración y documentación reproducible: en Git.
- `Otros/`: diagnósticos locales, archivos temporales, dataset masivo y telemetría
  cruda. Esta carpeta queda excluida de Git.
- Resultados consolidados, CSV finales, planes seleccionados y reporte: se
  versionarán en las carpetas de entrega correspondientes.
- Credenciales locales: `.env` excluido de Git; la plantilla pública será
  `.env.example` sin secretos.

La carpeta del proyecto permanece en Windows. Los datos activos de las bases
se alojarán en volúmenes nombrados de Docker para evitar medir I/O sobre /mnt/c.

## Protocolo

`protocolo.json` contiene los parámetros del experimento y las imágenes de los
motores fijadas por etiqueta y digest. Las configuraciones se validarán al
levantar el stack; seleccionar una imagen no demuestra todavía su funcionamiento.

Se ejecutará un motor a la vez. Perfiles: 4 CPU / 4096 MiB, 2 CPU / 2048 MiB
y 1 CPU / 1024 MiB; concurrencias 1, 10 y 50; tres repeticiones; calentamiento
60 s, medición 300 s y enfriamiento 60 s.

El manual define 36 celdas base. Al ejecutar ambas variantes de Q2 se adoptan
54 escenarios y 162 corridas; esta ampliación es una interpretación documentada
del equipo. Duración nominal mínima: 18 h 54 min, más preparación y recuperación.
Las variantes se identifican en `query_id`, conservando el esquema CSV exigido.

En este entorno cgroups v2 descarta `memory-swappiness=0`. La adaptación es fijar
memoria y memoria+swap al mismo límite, comprobando `memory.swap.max=0`.
Los buffers internos de los motores y la caché de Windows no se vacían mediante
`drop_caches`; el reporte explicará el alcance de la limpieza y el calentamiento.

Permitir disco en MongoDB o cambiar `work_mem` en PostgreSQL no asegura que ocurra
spill. Los errores de memoria del motor y los OOM del kernel se registrarán
con evidencia y se distinguirán en los detalles de cada corrida.

## Entrega prevista

`docker-compose.yml`, generador reproducible, runner, consultas MongoDB/SQL,
`run_benchmarks.sh`, CSV de mediciones y reporte con las siete secciones del manual.
El criterio de aceptación es reproducir las mediciones y responder M1/M2/M3
mediante métricas, planes de ejecución y evidencia.
