"""Carga JSONL verificado en un destino vacío, sin borrar ni sobrescribir datos."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'Otros/dataset/orders.jsonl'
MANIFEST = ROOT / 'resultados/dataset_manifest.json'


def env_vars():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines() if line and not line.startswith('#') and '=' in line)


def check_source():
    m = json.loads(MANIFEST.read_text(encoding='utf-8'))
    digest = hashlib.sha256()
    with DATA.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != m['sha256'] or DATA.stat().st_size != m['bytes']:
        raise ValueError('El dataset no coincide con el manifiesto')
    return m


def records():
    with DATA.open(encoding='utf-8') as source:
        for line in source:
            yield json.loads(line)


def qualifies(record):
    return record['payment']['status'] == 'completed' and record['timestamp'] >= '2026-01-01T00:00:00Z'


def mongo_load(env, manifest):
    from pymongo import MongoClient, ASCENDING
    client = MongoClient('127.0.0.1', int(env['MONGO_PORT']), username=env['MONGO_USER'], password=env['MONGO_PASSWORD'], authSource='admin', serverSelectionTimeoutMS=15000)
    db = client['document_benchmark']
    if 'orders' in db.list_collection_names():
        raise RuntimeError('La colección orders ya existe. No se modifica; revise su contenido.')
    orders = db['orders']
    batch = []
    count = 0
    expected_eligible = 0
    for record in records():
        expected_eligible += qualifies(record)
        batch.append(record)
        if len(batch) == 2000:
            orders.insert_many(batch, ordered=True)
            count += len(batch)
            batch.clear()
    if batch:
        orders.insert_many(batch, ordered=True)
        count += len(batch)
    orders.create_index([('order_id', ASCENDING)], name='order_id_1', unique=True)
    orders.create_index([('timestamp', ASCENDING)], name='timestamp_1')
    actual = orders.count_documents({})
    eligible = orders.count_documents({'payment.status': 'completed', 'timestamp': {'$gte': '2026-01-01T00:00:00Z'}})
    samples = []
    for idx, record in enumerate(records()):
        if idx % 50000 == 0:
            loaded = orders.find_one({'order_id': record['order_id']}, {'_id': 0})
            if loaded != record:
                raise ValueError(f'Muestra MongoDB incorrecta: {idx}')
            samples.append(record['order_id'])
    indexes = list(orders.index_information())
    client.close()
    if count != manifest['orders'] or actual != count or eligible != expected_eligible:
        raise ValueError('Conteo MongoDB incorrecto')
    return {'count': actual, 'q2_eligible': eligible, 'sample_order_ids': samples, 'indexes': indexes}


def postgres_load(env, manifest):
    import psycopg
    conn = psycopg.connect(host='127.0.0.1', port=int(env['POSTGRES_PORT']), user=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'], dbname=env['POSTGRES_DB'])
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.orders')")
            if cur.fetchone()[0] is not None:
                raise RuntimeError('La tabla public.orders ya existe. No se modifica; revise su contenido.')
            cur.execute('CREATE TABLE public.orders (id UUID PRIMARY KEY, data JSONB NOT NULL)')
            count = 0
            expected_eligible = 0
            with cur.copy('COPY public.orders (id, data) FROM STDIN') as copy:
                for record in records():
                    expected_eligible += qualifies(record)
                    copy.write_row((record['order_id'], json.dumps(record, ensure_ascii=False, separators=(',', ':'))))
                    count += 1
            cur.execute("CREATE INDEX orders_timestamp_idx ON public.orders ((data->>'timestamp'))")
            cur.execute('ANALYZE public.orders')
            cur.execute('SELECT count(*) FROM public.orders')
            actual = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM public.orders WHERE data->'payment'->>'status' = 'completed' AND (data->>'timestamp')::timestamptz >= '2026-01-01 00:00:00Z'")
            eligible = cur.fetchone()[0]
            samples = []
            for idx, record in enumerate(records()):
                if idx % 50000 == 0:
                    cur.execute('SELECT data FROM public.orders WHERE id=%s', (record['order_id'],))
                    row = cur.fetchone()
                    if row is None or row[0] != record:
                        raise ValueError(f'Muestra PostgreSQL incorrecta: {idx}')
                    samples.append(record['order_id'])
            cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename='orders' ORDER BY indexname")
            indexes = [row[0] for row in cur.fetchall()]
            if count != manifest['orders'] or actual != count or eligible != expected_eligible:
                raise ValueError('Conteo PostgreSQL incorrecto')
    conn.close()
    return {'count': actual, 'q2_eligible': eligible, 'sample_order_ids': samples, 'indexes': indexes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('engine', choices=('mongo', 'postgres'))
    args = parser.parse_args()
    output = ROOT / 'Otros' / 'dataset' / f'carga_{args.engine}.json'
    if output.exists():
        raise FileExistsError('Ya existe evidencia de carga para este motor; revise antes de continuar')
    manifest = check_source()
    start = time.monotonic()
    result = (mongo_load if args.engine == 'mongo' else postgres_load)(env_vars(), manifest)
    result.update({'engine': args.engine, 'source_sha256': manifest['sha256'], 'elapsed_seconds': round(time.monotonic()-start, 2), 'method': 'batch insert 2000' if args.engine == 'mongo' else 'COPY STDIN', 'sample_comparison': '10 full documents'})
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Error de carga: {exc}', file=sys.stderr)
        sys.exit(1)
