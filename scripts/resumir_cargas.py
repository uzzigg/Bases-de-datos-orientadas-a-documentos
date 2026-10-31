"""Compara la evidencia de las cargas sin afirmar identidad exhaustiva."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root / 'Otros/dataset'
mongo = json.loads((folder / 'carga_mongo.json').read_text(encoding='utf-8'))
postgres = json.loads((folder / 'carga_postgres.json').read_text(encoding='utf-8'))
for key in ('count', 'q2_eligible', 'source_sha256', 'sample_order_ids'):
    if mongo[key] != postgres[key]:
        raise ValueError(f'La evidencia no coincide: {key}')
summary = {'scope': 'Carga y comprobaciones de integridad; no es medicion de benchmark',
           'source_sha256': mongo['source_sha256'], 'orders_per_engine': mongo['count'],
           'q2_eligible_per_engine': mongo['q2_eligible'], 'full_document_samples_checked_per_engine': len(mongo['sample_order_ids']),
           'mongo_indexes': mongo['indexes'], 'postgres_indexes': postgres['indexes'],
           'limitations': ['La comparación de documentos se basa en diez muestras y conteos, no en una comparación exhaustiva de cada documento.', 'El índice PostgreSQL es B-Tree sobre texto ISO-8601; la consulta del manual convierte a timestamptz y el uso del índice requiere EXPLAIN.']}
out = root / 'resultados/carga_datos.json'
with out.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(summary, stream, indent=2, ensure_ascii=False)
    stream.write('\n')
print(json.dumps(summary, indent=2, ensure_ascii=False))
