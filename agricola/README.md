# Caso de producción agrícola

Cada documento representa una cosecha sintética con productor, ubicación y lotes de cultivos. Cada lote registra cajas y kilogramos por caja. El total de la cosecha se calcula como la suma de cajas por kilogramos por caja. Son datos sintéticos derivados de los números del dataset inicial, no observaciones agrícolas reales.

Q1 desanida lotes, filtra los de más de 50 kg por caja y agrupa el peso total y promedio por país y cultivo. Q2 selecciona cosechas finalizadas desde el 1 de enero de 2026 y obtiene las 1000 con mayor producción. Conserva las operaciones y variantes de memoria del manual, pero cambia el dominio, los atributos y las unidades. El umbral es una condición artificial de la carga, no una afirmación sobre cajas habituales.

El generador utiliza el archivo maestro previo y crea una copia separada bajo `Otros/dataset_agricola/`; no altera las bases existentes. `cargar.py` carga destinos nuevos y `validar.py` compara los resultados de ambas consultas. Se verificaron 500.000 cosechas por motor, 199.729 elegibles y equivalencia de los 20 grupos y 1.000 pesos. Las mediciones previas de órdenes no son resultados agrícolas; faltan un piloto y una matriz nuevos.
