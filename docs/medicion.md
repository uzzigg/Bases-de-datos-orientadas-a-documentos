# Runner y protocolo de medición

## Requisitos y seguridad

El dataset debe estar cargado en ambos motores y el stack Docker debe funcionar.
Las dependencias Python están en `requirements.txt`. El runner actual usa WSL2 y
`docker-desktop` para ejecutar `sync; echo 3 > /proc/sys/vm/drop_caches`: afecta
la caché Linux compartida y requiere ejecutar en una máquina de laboratorio.
El vaciado no limpia buffers internos de los motores ni garantiza limpiar la
caché de Windows. No ejecutar otro trabajo intensivo o benchmark en paralelo.

Cada repetición tiene una carpeta nueva en `Otros/benchmarks/<run-id>/`; se
rechaza la reutilización de nombres. `.runner.lock` y `.matriz.lock` impiden
ejecuciones simultáneas. Tras una interrupción abrupta puede quedar un bloqueo:
antes de retirarlo, comprobar que el PID registrado y sus procesos hijos ya
no están activos. No borrar evidencia parcial. El profiler MongoDB debe quedar
desactivado al finalizar; si el proceso termina de forma abrupta, comprobar
manualmente el nivel antes de volver a medir.

Estado del primer piloto: no aprobado. Aunque las consultas terminaron, hubo
270 muestras para una ventana de 300 s y huecos de hasta 4.338 s. Una prueba
independiente también mostró discrepancia entre los relojes de WSL y Windows.
Se detuvo temporalmente el servicio de hora de Ubuntu y se restauró al acabar;
la deriva persistió durante esa prueba. Los datos y su alcance se documentan en
`resultados/piloto_01_diagnostico.json`. No se debe iniciar la matriz hasta
comprobar un reloj estable y repetir un piloto completo con el runner actual.

## Una repetición

```powershell
.\scripts\stack.ps1 -Action Up -Engine mongo -Profile A
.\Otros\venv\Scripts\python.exe benchmark_runner.py --engine mongo --profile A --query Q1 --concurrency 1 --run-number 1 --run-id ejemplo_01
```

Valores permitidos: perfil A/B/C, concurrencia 1/10/50. Para MongoDB, query_id
Q1/Q2_NO_DISK/Q2_DISK; para PostgreSQL, Q1/Q2_4MB/Q2_64MB. El runner verifica
los límites reales Docker, limpia la caché Linux y usa por defecto 60 segundos
de calentamiento, 300 de medición y 60 de enfriamiento. Los parámetros de tiempo
pueden acortarse para pruebas, pero esas ejecuciones quedan marcadas como no
pertenecientes al protocolo completo y no habilitan la matriz.

Antes y después de cada repetición el runner compara durante cinco segundos
`CLOCK_MONOTONIC` y `CLOCK_MONOTONIC_RAW` de Ubuntu y el tiempo observado por
Windows. Como criterio del proyecto exige diferencia de frecuencia no mayor al
0.5% y diferencia absoluta RAW/Windows de hasta 0.75 s incluyendo el arranque
de WSL. Esta prueba no corrige el reloj y no garantiza por sí sola su estabilidad
durante toda la ventana; se combina con la comprobación de muestras. El control
actual rechazó iniciar una prueba por deriva de aproximadamente 8.38%.

Cada cliente es un proceso con conexión propia, usa la consulta guardada y
consume todas las filas. Los errores y tiempos de cada operación se conservan
en JSONL. El QPS cuenta operaciones exitosas que terminan durante la ventana;
los percentiles usan solo operaciones exitosas iniciadas y terminadas dentro de
ella, mediante nearest-rank. Las operaciones que cruzan el límite se conservan
y se contabilizan por separado. Un P99 con pocas observaciones es inestable;
el número de muestras va en detail.json y debe aparecer en el reporte.

Los contadores cgroup se leen al inicio y final; estos comandos `docker exec`
añaden una pequeña carga al contenedor. RSS proviene de cAdvisor y se expresa en
MiB. Las muestras reales de Prometheus se consultan como vector de rango, sin
interpolar huecos: la corrida se marca error si RSS, CPU o los recolectores
tienen menos del 90% de cobertura, hay un hueco superior a 2.5 s, faltan
muestras en los extremos o cAdvisor/Node Exporter aparecen inactivos.
Se conserva el vector completo para auditoría; revisar también CPU, fronteras
y otros recolectores en el piloto y al aceptar cada ventana.

MongoDB activa profiler nivel 2 temporalmente y etiqueta cada consulta para
detectar `usedDisk`. Si faltan registros del profiler, el spill queda vacío y
la repetición es error. El profiler escribe datos y añade sobrecarga; esta
instrumentación es una limitación de la comparación y debe documentarse.
PostgreSQL usa `log_temp_files=0` y conserva su log de contenedor. La ventana
de log se amplía hasta que terminan consultas en curso: un archivo temporal
cerca de los límites puede corresponder al calentamiento o a un cruce del
final; se guarda la evidencia para interpretarlo.

`measurement.csv` conserva exactamente las columnas del manual; un spill no
determinado se deja vacío y marca estado error. `detail.json` registra número
de muestras, errores, cobertura, métricas cgroup, uso de CPU, eventos OOM y
evidencia de spill. `metrics.json` y los archivos de clientes son datos crudos
locales. Si el proceso se interrumpe antes del cierre, la carpeta parcial se
conserva y no se considera una repetición completa.

## Matriz

Desde PowerShell se puede previsualizar la matriz sin arrancar motores:

```powershell
.\Otros\venv\Scripts\python.exe scripts/ejecutar_matriz.py
```

También se incluye `run_benchmarks.sh` para invocación desde WSL. La matriz
contiene 54 escenarios y tres repeticiones cada uno. Se mezclan grupos y celdas
con la semilla registrada, y se conservan las repeticiones agrupadas por celda.
La duración nominal mínima es 18 h 54 min más preparación y recuperación.

El programa exige un piloto MongoDB completo aprobado y su `audit.json` antes
de `--execute`. Después del piloto, con MongoDB activo, ejecutar:

```powershell
.\Otros\venv\Scripts\python.exe scripts/auditar_piloto.py ID_DEL_NUEVO_PILOTO
```

La auditoría independiente revisa cobertura y huecos de RSS, CPU y `up`,
incluyendo extremos de la ventana; confirma que el profiler volvió a nivel 0 y
que existen registros para operaciones que cruzaron el inicio de medición. Si
falta evidencia o los relojes discrepan, no aprueba el piloto.

El código del runner, protocolo y consultas debe coincidir por SHA-256 con la
versión usada en el piloto. La matriz usa un
identificador estable y bloquea otra matriz o runner. Al reanudar comprueba
identidad, CSV, protocolo y telemetría; si encuentra evidencia incompleta o
inconsistente se detiene para revisión. No borra intentos ni los repite por
su cuenta. Las fallas observadas del motor pueden quedar con estado error u
oom si su telemetría y evidencia están completas. Al terminar todos los casos,
consolida 162 filas mediante un archivo temporal y cambio de nombre atómico.

```powershell
.\Otros\venv\Scripts\python.exe scripts/ejecutar_matriz.py --execute --matrix-id principal --pilot-id ID_DEL_PILOTO_APROBADO
```

No iniciar la matriz solo por obtener un CSV del piloto: revisar el muestreo,
spill, archivos temporales, conectividad de ambos motores y carga del host.
Los scripts no evitan que Windows se suspenda. Una interrupción o suspensión
puede invalidar una ventana; registrar el estado antes de retomar.
