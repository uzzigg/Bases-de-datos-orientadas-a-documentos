"""Guarda resultados completos y planes agrícolas en archivos nuevos."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from cargar_datos import env_vars

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,indent=2,default=str)

def main():
    p=argparse.ArgumentParser();p.add_argument('motor',choices=['mongo','postgres']);a=p.parse_args();e=env_vars()
    target=ROOT/'Otros/consultas/agricola_detallada_01'; plans=ROOT/'resultados/planes_agricola'
    if a.motor=='mongo':
        from pymongo import MongoClient
        from bson import json_util
        c=MongoClient('127.0.0.1',int(e['MONGO_PORT']),username=e['MONGO_USER'],password=e['MONGO_PASSWORD'],authSource='admin'); db=c.document_benchmark
        for query,variant,allow in [('q1','disk',True),('q2','no_disk',False),('q2','disk',True)]:
            pipe=json.loads((ROOT/f'agricola/mongo_{query}.json').read_text(encoding='utf-8'))
            rows=list(db.cosechas.aggregate(pipe,allowDiskUse=allow));
            if query=='q2': rows=[{'cosecha_id':r['cosecha_id'],'productor_id':r['productor']['id'],'total_kg':r['resultado']['total_kg']} for r in rows]
            save(target/f'mongo_{query}_{variant}.json',rows)
            plan=db.command({'explain':{'aggregate':'cosechas','pipeline':pipe,'cursor':{},'allowDiskUse':allow},'verbosity':'executionStats'})
            save(plans/f'mongo_{query}_{variant}.json',json.loads(json_util.dumps(plan)))
            print(a.motor,query,variant,len(rows),flush=True)
        c.close()
    else:
        import psycopg
        with psycopg.connect(host='127.0.0.1',port=int(e['POSTGRES_PORT']),user=e['POSTGRES_USER'],password=e['POSTGRES_PASSWORD'],dbname=e['POSTGRES_DB']) as c:
            with c.cursor() as cur:
                for query,variant,mem in [('q1','4MB','4MB'),('q2','4MB','4MB'),('q2','64MB','64MB')]:
                    sql=(ROOT/f'agricola/postgres_{query}.sql').read_text(encoding='utf-8');cur.execute("SELECT set_config('work_mem',%s,false)",(mem,));cur.execute(sql)
                    rows=[dict(zip([x.name for x in cur.description],r)) for r in cur.fetchall()];save(target/f'postgres_{query}_{variant}.json',rows)
                    cur.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+sql);save(plans/f'postgres_{query}_{variant}.json',cur.fetchone()[0]);print(a.motor,query,variant,len(rows),flush=True)

if __name__=='__main__':main()
