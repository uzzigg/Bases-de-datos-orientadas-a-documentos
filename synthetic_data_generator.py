"""Genera JSONL determinista para el experimento; no sobrescribe archivos."""
import argparse
import collections
import datetime as dt
import hashlib
import json
import random
import sys
import uuid
from pathlib import Path

COUNTRIES = {
    "MX": ("Chiapas", "Tuxtla Gutierrez", "29000", [16.75, -93.12]),
    "US": ("Texas", "Austin", "73301", [30.27, -97.74]),
    "CA": ("Ontario", "Toronto", "M5H", [43.65, -79.38]),
    "ES": ("Madrid", "Madrid", "28001", [40.42, -3.70]),
}
CATEGORIES = ("electronics", "books", "clothing", "home", "sports")
START = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
SECONDS = 2 * 365 * 24 * 60 * 60


def generate(count, seed, output, manifest):
    if count < 1:
        raise ValueError('count debe ser positivo')
    if output.resolve() == manifest.resolve():
        raise ValueError('dataset y manifiesto deben ser archivos distintos')
    if output.exists() or manifest.exists():
        raise FileExistsError('El dataset o el manifiesto ya existe; elija otras rutas')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    digest = hashlib.sha256()
    status_counts = collections.Counter()
    item_counts = collections.Counter()
    items_total = 0
    with output.open('xb', buffering=1024 * 1024) as stream:
        for index in range(count):
            oid = str(uuid.UUID(int=rng.getrandbits(128), version=4))
            timestamp = (START + dt.timedelta(seconds=rng.randrange(SECONDS))).strftime('%Y-%m-%dT%H:%M:%SZ')
            country = rng.choice(tuple(COUNTRIES))
            state, city, postal, coordinates = COUNTRIES[country]
            number_items = rng.choice((1, 2, 3, 4, 5))
            items = []
            for _ in range(number_items):
                category = rng.choice(CATEGORIES)
                qty = rng.randint(1, 5)
                price = rng.randint(10, 200)
                items.append({'sku': f'SKU-{rng.randrange(10000):04d}', 'category': category,
                              'brand': f'brand-{rng.randrange(20):02d}', 'qty': qty, 'price': price,
                              'tax_pct': 0, 'discounts': []})
            total = sum(item['qty'] * item['price'] for item in items)
            status = rng.choices(('completed', 'pending', 'failed'), weights=(80, 15, 5))[0]
            record = {
                'order_id': oid, 'timestamp': timestamp,
                'customer': {'id': f'customer-{rng.randrange(100000):06d}', 'tier': rng.choice(('basic', 'silver', 'gold')),
                             'segment': rng.choice(('consumer', 'business')), 'geo': {'country': country, 'state': state,
                             'city': city, 'zip': postal, 'coordinates': coordinates}},
                'items': items,
                'payment': {'method': rng.choice(('card', 'transfer', 'wallet')), 'status': status,
                            'transaction_id': f'txn-{index:08d}', 'gateway_latency_ms': rng.randint(10, 500),
                            'totals': {'subtotal': total, 'tax': 0, 'discount': 0}, 'final_total': total},
                'metadata': {'channel': rng.choice(('web', 'mobile', 'store')), 'user_agent': 'synthetic/1.0',
                             'session_id': f'session-{index:08d}', 'flags': []},
            }
            line = (json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
            stream.write(line)
            digest.update(line)
            status_counts[status] += 1
            item_counts[number_items] += 1
            items_total += number_items
    info = {'format': 'jsonl-utf8-lf', 'generator_version': 1, 'seed': seed, 'orders': count,
            'items_total': items_total, 'mean_items': items_total / count, 'item_count_distribution': dict(sorted(item_counts.items())),
            'payment_status_distribution': dict(sorted(status_counts.items())), 'bytes': output.stat().st_size,
            'sha256': digest.hexdigest(), 'timestamp_min_inclusive': START.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'timestamp_max_exclusive': (START + dt.timedelta(seconds=SECONDS)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'numeric_model': 'integer prices and totals; zero tax and discounts'}
    with manifest.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(info, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=500000)
    parser.add_argument('--seed', type=int, default=243733)
    parser.add_argument('--output', type=Path, default=Path('Otros/dataset/orders.jsonl'))
    parser.add_argument('--manifest', type=Path, default=Path('Otros/dataset/manifest.json'))
    args = parser.parse_args()
    try:
        info = generate(args.count, args.seed, args.output, args.manifest)
    except (ValueError, FileExistsError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
