# Prevención y recuperación de la matriz

Las medidas operativas se incorporaron durante la matriz agrícola. No cambian las consultas, los tiempos ni los límites de recursos. Los cambios de captura y los criterios de calidad aplicados en distintas etapas deben explicarse al comparar resultados.

| Riesgo | Medida activa | Qué ocurre si persiste |
|---|---|---|
| Profiler pierde registros | Capacidad ampliada a 256 MiB; antes de preparar MongoDB con cosechas se verifica capacidad y nivel del profiler | Se conserva el estado de error y el spill desconocido; no se presupone ausencia de spill |
| Motor tarda en recuperar salud | Hasta tres intentos de preparación, con esperas de 45 s | Se detiene para revisión conservando los resultados |
| Prometheus no responde temporalmente al extraer memoria adicional | Hasta tres consultas al mismo intervalo, con esperas de 2 y 4 s, solo ante errores transitorios | Se conserva el fallo; no se repite el benchmark para obtener mejores cifras |
| Interrupción al escribir memoria adicional | Publicación de archivo completo mediante temporal, sincronización y renombrado; se rechaza sobrescribir evidencia | Un archivo previo se conserva; el temporal incompleto no se presenta como evidencia válida |
| Falta de espacio | Verificación de 5 GiB libres antes de preparar el siguiente motor | No se inicia la medición; se revisa espacio sin eliminar datos automáticamente |
| Detención antes del consolidado | Respaldos parciales de CSV con hashes, estado y control de identidad | Se conservan resultados anteriores, incluso errores y spill desconocido |
| Corte de energía o proceso terminado abruptamente | Bloqueos y registros de continuación; supervisión revisa procesos y restauración de hora | Se verifican PID y procesos antes de mover bloqueos; nunca se retiran a ciegas |
| Huecos de métricas o reloj inestable | Se mantienen los controles y la evidencia individual | Se informa la limitación y se preserva el intento; no se amplían criterios silenciosamente |

`scripts/stack.ps1 -Action Up` ejecuta `scripts/verificar_preparacion.py` cuando existe el entorno Python de la práctica. Los diagnósticos de preparación se guardan en `Otros/benchmarks/preparacion/`. El requisito de 256 MiB corresponde a la configuración posterior a la corrección del profiler; para una instalación nueva con cosechas cargadas se debe preparar esa colección antes del benchmark.

`python scripts/resguardar_matriz.py --matrix-id agricola` lee únicamente evidencia terminada y crea un CSV parcial y un JSON en `Otros/respaldos_matriz/`. No cambia la matriz ni certifica que todas las filas sean válidas: incluye estados de error y advierte sobre desconocidos, evidencia faltante o inconsistencias. Una corrida todavía sin archivos completos queda pendiente de una próxima revisión. El consolidado final sigue reservado para las 162 corridas.

La retención de Prometheus está limitada por tiempo y espacio; por eso la memoria adicional se recupera después de cada corrida. Ninguna de estas medidas garantiza evitar fallas físicas o del sistema operativo. Las pruebas funcionales y la revisión de percentiles con muestras insuficientes se completan al analizar el conjunto final.
