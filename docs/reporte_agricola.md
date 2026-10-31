# Comparación de MongoDB y PostgreSQL JSONB: producción agrícola

**Borrador de trabajo.** Las conclusiones comparativas y gráficas dependen de la matriz agrícola en curso. Las mediciones anteriores del caso de órdenes son antecedentes, no resultados de este caso.

## Caso y datos

Se modelan cosechas sintéticas con productor, ubicación y lotes de cultivo. Cada lote contiene cajas y kilogramos por caja; el total de la cosecha es la suma de ambos valores multiplicados. El conjunto se derivó de forma determinista del dataset sintético inicial, por lo que no representa observaciones agrícolas reales. El filtro de más de 50 kg por caja es una condición artificial de la carga y no caracteriza tamaños habituales de cajas.

Se generaron 500.000 cosechas y 1.499.983 lotes; 199.729 cosechas finalizadas cumplen el filtro temporal de Q2. El SHA-256 del JSONL agrícola es `2f73f8a70f7d59b4ef0e6f932a725000c7b7be2e0368ec774c6358e03d2b9d1a`. Se verificaron los conteos en ambos motores, sin afirmar una comparación exhaustiva de todos los documentos.

## Método y validación

Q1 desanida lotes, filtra por peso y agrupa peso total y promedio por país y cultivo. Q2 selecciona cosechas finalizadas desde 2026-01-01 y ordena las 1.000 de mayor producción. Las consultas y su alcance se describen en `agricola/README.md`. La comparación funcional obtuvo 20 grupos Q1 equivalentes y 1.000 totales Q2 equivalentes; no constituye una comparación exhaustiva de identificadores empatados en el corte.

Los perfiles, concurrencias y variantes están en `protocolo.json`. El piloto agrícola pasó la auditoría con 300 muestras en la ventana de 300 segundos y un hueco máximo de aproximadamente 1,004 segundos; la evidencia está en `resultados/piloto_agricola_01.json`. El límite de diferencia de ritmo de reloj se fijó en menos de 2,5 % por decisión del estudiante ante el plazo; esto aumenta la incertidumbre y no elimina los controles de telemetría.

## Resultados, gráficas y análisis

Pendiente: consolidar las repeticiones agrícolas, distinguir resultados exitosos de errores y calcular las métricas y gráficas solicitadas. No anticipar un ganador ni usar como resultados las corridas del caso de órdenes. Documentar muestras insuficientes para P99, spill, OOM y las limitaciones del entorno cuando se observen.

## Planes, conclusiones y recomendaciones

Pendiente: obtener o seleccionar planes del caso agrícola, responder M1/M2/M3 con evidencia de la matriz y formular recomendaciones acordes con los resultados y limitaciones. Los planes anteriores de órdenes son históricos.
