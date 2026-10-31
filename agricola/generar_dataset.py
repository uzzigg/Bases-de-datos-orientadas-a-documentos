"""Transforma el conjunto maestro en cosechas agrícolas reproducibles, sin sobrescribirlo."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'Otros/dataset/orders.jsonl'
OUT = ROOT / 'Otros/dataset_agricola/cosechas.jsonl'
MANIFEST = ROOT / 'Otros/dataset_agricola/manifiesto.json'
CROPS = {'electronics': 'maiz', 'books': 'cafe', 'clothing': 'frijol', 'home': 'cacao', 'sports': 'mango'}
STATES = {'completed': 'finalizada', 'pending': 'pendiente', 'failed': 'cancelada'}

def main():
    if OUT.exists() or MANIFEST.exists():
        raise FileExistsError('La salida agrícola ya existe; no se sobrescribe')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = lots = eligible = 0
    with SOURCE.open(encoding='utf-8') as source, OUT.open('xb') as target:
        for line in source:
            old = json.loads(line)
            batches = [{'cultivo': CROPS[item['category']], 'cajas': item['qty'],
                        'kg_por_caja': item['price'], 'lote_id': item['sku']} for item in old['items']]
            total = sum(x['cajas'] * x['kg_por_caja'] for x in batches)
            record = {'cosecha_id': old['order_id'], 'fecha': old['timestamp'],
                      'productor': {'id': old['customer']['id'], 'ubicacion': old['customer']['geo']},
                      'lotes': batches, 'resultado': {'estado': STATES[old['payment']['status']], 'total_kg': total},
                      'registro': {'canal': old['metadata']['channel'], 'sesion': old['metadata']['session_id']}}
            data = (json.dumps(record, ensure_ascii=False, separators=(',', ':'))+'\n').encode('utf-8')
            target.write(data); digest.update(data)
            count += 1; lots += len(batches)
            eligible += record['resultado']['estado'] == 'finalizada' and record['fecha'] >= '2026-01-01T00:00:00Z'
    manifest = {'registros': count, 'lotes': lots, 'finalizadas_desde_2026': eligible,
                'bytes': OUT.stat().st_size, 'sha256': digest.hexdigest(),
                'origen': 'Transformación determinista del dataset sintético de la práctica',
                'unidades': 'cajas enteras y kilogramos enteros por caja'}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False))

if __name__ == '__main__':
    main()
