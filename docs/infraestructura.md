# Infraestructura del experimento

Los scripts PowerShell se ejecutan desde la raíz del proyecto en Windows, con
Docker Desktop activo, integración de Ubuntu/WSL2 y Python 3 disponible.
`docker-compose.yml` también puede usarse desde Linux con Docker Compose v2;
la prueba automatizada publicada aquí se ejecuta desde Windows.

## Inicio y operación

```powershell
.\scripts\iniciar_entorno.ps1
.\scripts\stack.ps1 -Action Validate -Engine mongo -Profile A
.\scripts\stack.ps1 -Action Pull -Engine mongo -Profile A
.\scripts\stack.ps1 -Action Pull -Engine postgres -Profile A
.\scripts\stack.ps1 -Action Up -Engine mongo -Profile A
.\scripts\stack.ps1 -Action Status -Engine mongo -Profile A
```

`iniciar_entorno.ps1` genera dos contraseñas aleatorias en `.env`, ignorado por
Git. Si ya existe, lo conserva. No cambiar las credenciales de `.env` después
de inicializar volúmenes esperando que cambien los usuarios almacenados: ese
cambio requiere administrar los usuarios dentro de las bases.

Para cambiar de motor o perfil:

```powershell
.\scripts\stack.ps1 -Action Up -Engine postgres -Profile C
```

`Up` detiene el motor opuesto dentro del mismo proyecto, inicia el elegido y
espera su comprobación de salud. Compose recrea el contenedor si cambian los
límites; los volúmenes nombrados se conservan. No ejecutar dos comandos Up
simultáneamente. Los healthchecks se ejecutan cada 30 segundos; su carga y la
del monitoreo forman parte del entorno y se mantienen constantes.

Para detener todos los servicios sin borrar sus datos:

```powershell
.\scripts\stack.ps1 -Action Stop
```

No usar `docker compose down -v` para cambiar de escenario: elimina los
volúmenes. Los motores tienen `restart: no` para conservar evidencia de
errores/OOM; el runner futuro deberá gestionar su recuperación explícitamente.

## Puertos de acceso local

| Servicio | Dirección predeterminada |
| --- | --- |
| MongoDB | 127.0.0.1:27017 |
| PostgreSQL | 127.0.0.1:55432 |
| Prometheus | http://127.0.0.1:9090 |
| cAdvisor | http://127.0.0.1:8080 |
| Node Exporter | http://127.0.0.1:9100/metrics |

Se publica únicamente en loopback. PostgreSQL usa 55432 en Windows porque
5432 no estaba disponible en el equipo de prueba; su puerto interno es 5432.
Los puertos pueden configurarse en `.env`.

## Recursos y persistencia

| Perfil | CPU del motor | Memoria |
| --- | --- | --- |
| A | 4 | 4096 MiB |
| B | 2 | 2048 MiB |
| C | 1 | 1024 MiB |

memswap_limit igual a mem_limit desactiva swap para el contenedor y se verifica
con memory.swap.max=0. No se utiliza mem_swappiness, descartado en este entorno.
Las cuotas se verifican en cpu.max, no solo en el archivo de Compose.

Monitoreo: cAdvisor 1 CPU/384 MiB, Node Exporter 0.5 CPU/128 MiB y Prometheus
1 CPU/512 MiB. Son máximos, no reservas. Prometheus conserva hasta siete días
con un objetivo máximo de 2 GB de bloques TSDB; WAL y otros archivos pueden
añadir espacio. Antes de corridas largas hay que verificar la capacidad real.

Volúmenes nombrados independientes para MongoDB, su configdb, PostgreSQL y
Prometheus. En PostgreSQL 18 el volumen se monta en `/var/lib/postgresql`, de
acuerdo con la imagen oficial. El YAML de Prometheus se monta de solo lectura
desde el proyecto; los datos activos de las bases no se guardan en /mnt/c.

PostgreSQL: max_connections=100, shared_buffers=128MB, work_mem=4MB y
log_temp_files=0. El runner de Q2 deberá aplicar 4MB o 64MB en cada conexión.
MongoDB mantiene WiredTiger y sus valores automáticos; deben registrarse en el
reporte y revisar su comportamiento con los perfiles, especialmente el severo.

## Monitoreo y alcance

Prometheus recopila tres targets cada 1 s: cadvisor, node-exporter y prometheus.
cAdvisor utiliza housekeeping de 1 s, intervalo máximo de 1 s y ajuste dinámico
desactivado. La prueba exige métricas del ID actual del contenedor del motor,
para no confundir series históricas de otro perfil.
En el job de cAdvisor se configura honor_timestamps=false: Prometheus asigna
el instante de recopilación aunque el exporter repita un timestamp de su
housekeeping. Esto evita huecos por timestamps repetidos, pero no transforma
una muestra repetida en una observación nueva del kernel. Revisar también la
frescura y cobertura al aceptar las ventanas del benchmark.

- container_cpu_usage_seconds_total: CPU consumida.
- container_cpu_cfs_throttled_seconds_total: contador acumulado de throttling.
- container_memory_rss: memoria RSS que expone cAdvisor.
- container_last_seen: presencia del contenedor en el monitoreo.
- node_memory_MemAvailable_bytes, node_vmstat_pswpin/pswpout y
  node_disk_read_bytes_total: memoria, swap e I/O del entorno Linux.

El nombre real del contador Prometheus termina en `_total`; el manual contiene
un nombre ligeramente distinto. Esta correspondencia debe documentarse en el
reporte. Las consultas de la matriz calcularán deltas por ventana y máximos de
muestras, sin tratar contadores acumulados como resultados individuales.

Node Exporter observa el host Linux de Docker Desktop, no Windows. En este
equipo se omitió la propagación rslave del montaje raíz porque Docker Desktop
la rechazó; se usa un bind de solo lectura y los collectors se validan con
consultas reales. cAdvisor requiere acceso privilegiado, al socket Docker y a
/sys; este stack se destina al laboratorio local.

La evidencia OOM se recoge directamente de memory.events y del estado Docker.
La fase 1 comprueba que se puede leer, sin provocar agotamiento de memoria.
Spill a disco y corrección de Q1/Q2 se validarán con las consultas y el runner.

## Prueba reproducible

```powershell
python scripts/verify_stack.py --engine mongo --profile A --restart
python scripts/verify_stack.py --engine postgres --profile A --restart
```

La prueba usa una colección `_phase1_probe` y una tabla `_phase1.probes`,
inserta un identificador único, reinicia el motor y lee el registro. Después
borra únicamente ese registro. No modifica la colección/tabla orders.
Cada ejecución produce evidencia local en `Otros/fase1/verify_MOTOR_PERFIL.json`.
Si falla, el JSON contiene el error y el servicio queda disponible para revisar
logs. La prueba no es una corrida del benchmark.

Para repetir la validación en los seis casos, ejecutar verify_stack.py con
los motores mongo/postgres y los perfiles A/B/C, siempre de forma secuencial.
Después, con un motor activo:

```powershell
python scripts/verificar_muestreo.py
python scripts/resumir_fase1.py
```

La comprobación temporal espera 22 s y examina una ventana de 20 s: exige al
menos 18 muestras, hueco máximo de 2.5 s y last_seen no mayor de 5 s. Conserva
el resultado en Otros/fase1/muestreo.json. El resumen público se genera en
resultados/verificacion_fase1.json a partir de las seis pruebas y el muestreo.

Durante la puesta en marcha se observó un hueco de 4.335 s (17 muestras/20 s).
La observación se conservó como muestreo_inicial.json. Tras estabilizar el
monitoreo, la repetición obtuvo 20 muestras/20 s, mediana 1 s, hueco máximo
1.001 s y frescura aproximada de 1.106 s. Esto acredita la ventana comprobada;
el runner deberá verificar cobertura y frescura de cada corrida bajo carga.

## Fuentes de configuración

- [Servicios Compose y límites](https://docs.docker.com/reference/compose-file/services/).
- [Imagen oficial PostgreSQL y almacenamiento](https://hub.docker.com/_/postgres).
- [Ejecución de cAdvisor](https://github.com/google/cadvisor/blob/master/docs/running.md).
- [Node Exporter y host en contenedores](https://github.com/prometheus/node_exporter).
- [Configuración Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).
