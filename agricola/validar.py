"""Ejecuta las consultas agrícolas y guarda resultados para comparación funcional."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from cargar_datos import env_vars

def main():
    p=argparse.ArgumentParser(); p.add_argument('motor', choices=['mongo','postgres','comparar']); a=p.parse_args()
    out=ROOT/'Otros/dataset_agricola'; e=env_vars()
    if a.motor == 'comparar':
        m=json.loads((out/'validacion_mongo.json').read_text(encoding='utf-8'))
        s=json.loads((out/'validacion_postgres.json').read_text(encoding='utf-8'))
        assert m['q1']==s['q1'] and m['q2_totales']==s['q2_totales'] and len(m['q2_totales'])==1000
        print(json.dumps({'grupos_q1':len(m['q1']),'totales_q2':len(m['q2_totales']),'equivalentes':True}))
        return
    if a.motor == 'mongo':
        from pymongo import MongoClient
        c=MongoClient('127.0.0.1',int(e['MONGO_PORT']),username=e['MONGO_USER'],password=e['MONGO_PASSWORD'],authSource='admin')
        coll=c.document_benchmark.cosechas
        q1=list(coll.aggregate(json.loads((ROOT/'agricola/mongo_q1.json').read_text()),allowDiskUse=True))
        q2=list(coll.aggregate(json.loads((ROOT/'agricola/mongo_q2.json').read_text()),allowDiskUse=True))
        groups=sorted([[x['_id']['pais'],x['_id']['cultivo'],x['total_kg'],round(x['promedio_kg'],6),x['conteo']] for x in q1])
        totals=[x['resultado']['total_kg'] for x in q2]; c.close()
    else:
        import psycopg
        with psycopg.connect(host='127.0.0.1',port=int(e['POSTGRES_PORT']),user=e['POSTGRES_USER'],password=e['POSTGRES_PASSWORD'],dbname=e['POSTGRES_DB']) as c:
            with c.cursor() as cur:
                cur.execute((ROOT/'agricola/postgres_q1.sql').read_text()); groups=sorted([[r[0],r[1],int(r[2]),round(float(r[3]),6),r[4]] for r in cur.fetchall()])
                cur.execute((ROOT/'agricola/postgres_q2.sql').read_text()); totals=[int(r[2]) for r in cur.fetchall()]
    target=out/f'validacion_{a.motor}.json'
    with target.open('x',encoding='utf-8') as f: json.dump({'q1':groups,'q2_totales':totals},f)
    print(json.dumps({'motor':a.motor,'grupos_q1':len(groups),'filas_q2':len(totals)}))

if __name__=='__main__': main()
