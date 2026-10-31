# Comparación de MongoDB y PostgreSQL JSONB

**Borrador histórico del caso de órdenes; debe adaptarse al caso agrícola.** Las mediciones previas no son resultados agrícolas. Véase `agricola/README.md`.

## 1. Equipo y entorno

El equipo cuenta con un Intel Core i7-13620H y 15.64 GiB de memoria utilizable, con Windows 11 y WSL2. Se emplearon Docker Desktop 4.55.0, Docker Engine 29.1.3, Ubuntu 24.04.3 y cgroups v2. Los motores se ejecutan por separado: MongoDB 9.0.4 y PostgreSQL 18.6, este último con documentos JSONB. Las imágenes se fijaron por versión y digest en `protocolo.json`.

La infraestructura incluye cAdvisor, Node Exporter y Prometheus. Se verificaron las seis combinaciones de motor y perfil, sus límites y su conectividad; el resumen se encuentra en `resultados/verificacion_fase1.json`. La memoria disponible y la carga del equipo deberán registrarse durante las mediciones definitivas.

## 2. Datos y método

Se generó un conjunto sintético común de 500,000 órdenes con semilla 243733 y 1,499,983 artículos. El archivo maestro tiene SHA-256 `c687f77ad6bd8b060943fe88810501630f0ab81a2c60d55c8e2315e98dc01a15`; su manifiesto está en `resultados/dataset_manifest.json`. Las dos bases recibieron 500,000 órdenes y se contrastaron diez documentos completos por motor contra el archivo maestro. Esta muestra no demuestra la igualdad exhaustiva de todos los documentos.

Los precios y totales son enteros, y los impuestos y descuentos son cero: estas simplificaciones limitan la generalización. El procedimiento de carga e índices se describe en `docs/carga_datos.md`.

| Perfil | CPU | Memoria | Swap del contenedor |
|---|---:|---:|---:|
| A | 4 | 4096 MiB | 0 |
| B | 2 | 2048 MiB | 0 |
| C | 1 | 1024 MiB | 0 |

El protocolo contempla concurrencias de 1, 10 y 50 clientes, tres repeticiones y fases de 60 segundos de calentamiento, 300 de medición y 60 de enfriamiento. Las variantes de Q2 amplían la matriz base a 54 escenarios y 162 corridas; esta ampliación es una decisión documentada del proyecto. Las opciones de memoria por consulta están en `protocolo.json` y `docs/consultas.md`.

## 3. Validación funcional y resultados

Q1 produjo 20 grupos equivalentes: conteos y sumas coincidieron y se empleó una tolerancia absoluta de 1e-8 para promedios. En Q2, las cuatro variantes produjeron 1,000 importes iguales; el importe de corte fue 2719, con 998 órdenes por encima. Existen empates en el corte y no se especifica un desempate, por lo que las órdenes empatadas pueden variar. Evidencia: `resultados/validacion_consultas.json`.

**Pendiente:** presentar las corridas válidas de rendimiento, sus errores, medianas y dispersión. Los dos pilotos completos realizados fueron rechazados por problemas de reloj y cobertura de telemetría; no se utilizan sus latencias ni QPS como resultados. Ver `resultados/piloto_01_diagnostico.json` y `resultados/piloto_02_diagnostico.json`.

## 4. Gráficas

**Pendiente:** generar las gráficas de latencia P99 frente a concurrencia, throttling frente a QPS, memoria y comparación de variantes Q2 a partir de mediciones válidas. Indicar unidades, perfiles y cantidad de repeticiones.

## 5. Planes de ejecución

Los planes de validación se conservan en `resultados/planes_validacion/`. En una ejecución puntual de Q2, MongoDB utilizó `IXSCAN` sobre `timestamp_1` y no registró spill; PostgreSQL con `work_mem=4MB` mostró `Seq Scan` y `top-N heapsort`, sin bloques temporales. Estas observaciones describen esas ejecuciones concretas y no permiten concluir cuál motor rinde mejor bajo contención.

## 6. Interpretación y limitaciones

**Pendiente:** interpretar las métricas y responder M1, M2 y M3 con datos válidos. Separar el RSS del uso total y working set: miden componentes diferentes de memoria. Señalar errores, cobertura y posibles muestras insuficientes para P99.

La limpieza de caché de Linux no garantiza eliminar los buffers internos de los motores ni la caché de Windows. El profiler de MongoDB utilizado para observar spill añade sobrecarga y debe considerarse al interpretar la comparación. La deriva observada entre relojes de WSL impide aceptar mediciones hasta que se resuelva y un piloto supere la auditoría.

## 7. Recomendaciones y reproducibilidad

**Pendiente:** formular recomendaciones basadas en los resultados finales, con sus límites. Los pasos de preparación, ejecución y fuentes de evidencia se documentan en `README.md` y `docs/medicion.md`; `protocolo.json` es la configuración canónica.
