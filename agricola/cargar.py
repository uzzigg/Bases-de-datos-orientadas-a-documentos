"""Carga cosechas en destinos nuevos, sin modificar las órdenes anteriores."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cargar_datos import env_vars

DATA = ROOT / 'Otros/dataset_agricola/cosechas.jsonl'
MANIFEST = ROOT / 'Otros/dataset_agricola/manifiesto.json'

def records():
    with DATA.open(encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('motor', choices=['mongo', 'postgres'])
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    digest = hashlib.sha256()
    with DATA.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            digest.update(block)
    if digest.hexdigest() != manifest['sha256']:
        raise ValueError('Hash del dataset incorrecto')
    e = env_vars()
    if args.motor == 'mongo':
        from pymongo import MongoClient
        client = MongoClient('127.0.0.1', int(e['MONGO_PORT']), username=e['MONGO_USER'], password=e['MONGO_PASSWORD'], authSource='admin')
        db = client.document_benchmark
        if 'cosechas' in db.list_collection_names():
            raise RuntimeError('La colección cosechas existe; no se modifica')
        coll = db.cosechas
        batch = []
        for record in records():
            batch.append(record)
            if len(batch) == 2000:
                coll.insert_many(batch); batch.clear()
        if batch: coll.insert_many(batch)
        coll.create_index('cosecha_id', unique=True); coll.create_index('fecha')
        count = coll.count_documents({})
        eligible = coll.count_documents({'resultado.estado':'finalizada','fecha':{'$gte':'2026-01-01T00:00:00Z'}})
        client.close()
    else:
        import psycopg
        with psycopg.connect(host='127.0.0.1', port=int(e['POSTGRES_PORT']), user=e['POSTGRES_USER'], password=e['POSTGRES_PASSWORD'], dbname=e['POSTGRES_DB']) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.cosechas')")
                if cur.fetchone()[0] is not None: raise RuntimeError('La tabla cosechas existe; no se modifica')
                cur.execute('CREATE TABLE public.cosechas (id UUID PRIMARY KEY, data JSONB NOT NULL)')
                with cur.copy('COPY public.cosechas (id, data) FROM STDIN') as copy:
                    for record in records(): copy.write_row((record['cosecha_id'], json.dumps(record, ensure_ascii=False)))
                cur.execute("CREATE INDEX cosechas_fecha_idx ON public.cosechas ((data->>'fecha'))")
                cur.execute('ANALYZE public.cosechas')
                cur.execute('SELECT count(*) FROM public.cosechas'); count = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM public.cosechas WHERE data->'resultado'->>'estado'='finalizada' AND (data->>'fecha')::timestamptz >= '2026-01-01 00:00:00Z'")
                eligible = cur.fetchone()[0]
    print(json.dumps({'motor': args.motor, 'registros': count, 'finalizadas_desde_2026': eligible}))
    if count != manifest['registros'] or eligible != manifest['finalizadas_desde_2026']:
        raise ValueError('Conteos incorrectos')

if __name__ == '__main__': main()
