"""Verifica el JSONL sin cargarlo por completo en memoria."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'Otros/dataset/orders.jsonl'
manifest = json.loads((root / 'Otros/dataset/manifest.json').read_text(encoding='utf-8'))
digest = hashlib.sha256()
count = items = eligible = 0
with path.open('rb') as stream:
    for line in stream:
        digest.update(line)
        record = json.loads(line)
        count += 1
        items += len(record['items'])
        if record['payment']['final_total'] != sum(i['qty'] * i['price'] for i in record['items']):
            raise ValueError(f'Total incorrecto en orden {count}')
        eligible += record['payment']['status'] == 'completed' and record['timestamp'] >= '2026-01-01T00:00:00Z'
if count != manifest['orders'] or items != manifest['items_total'] or digest.hexdigest() != manifest['sha256']:
    raise ValueError('El dataset no coincide con el manifiesto')
if eligible < 1000:
    raise ValueError('Insuficientes ordenes elegibles para Q2')
print(json.dumps({'orders': count, 'items': items, 'q2_eligible': eligible, 'sha256': digest.hexdigest(), 'totals_valid': True}, indent=2))
