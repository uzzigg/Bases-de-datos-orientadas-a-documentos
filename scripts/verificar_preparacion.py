"""Verifica espacio y capacidad de diagnóstico antes de medir, sin cambiar el motor."""
import argparse
import datetime as dt
import shutil

from archivos_evidencia import publicar_json
from cargar_datos import ROOT, env_vars


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True, choices=['mongo','postgres'])
    args = parser.parse_args()
    free = shutil.disk_usage(ROOT).free
    report = {'engine':args.engine, 'free_bytes':free, 'minimum_free_bytes':5*1024**3,
              'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'issues':[]}
    if free < report['minimum_free_bytes']:
        report['issues'].append('Menos de 5 GiB libres; revisar espacio antes de medir')
    if args.engine == 'mongo':
        from pymongo import MongoClient
        e=env_vars()
        with MongoClient('127.0.0.1',int(e['MONGO_PORT']),username=e['MONGO_USER'],
                         password=e['MONGO_PASSWORD'],authSource='admin',
                         serverSelectionTimeoutMS=10000,socketTimeoutMS=15000) as client:
            db=client.document_benchmark
            # La infraestructura también se levanta antes de la carga inicial.
            # Exigir el profiler ampliado solo cuando ya hay cosechas cargadas.
            report['agricultural_data_present']=bool(list(db.list_collections(filter={'name':'cosechas'})))
            info=list(db.list_collections(filter={'name':'system.profile'}))
            report['profiler_size_bytes']=info[0].get('options',{}).get('size',0) if info else 0
            report['profiler_level']=db.command('profile',-1)['was']
            if report['agricultural_data_present'] and report['profiler_size_bytes'] < 256*1024**2:
                report['issues'].append('Profiler menor que los 256 MiB usados desde la corrección; requiere revisión')
            if report['profiler_level'] != 0:
                report['issues'].append('Profiler activo al preparar corrida; verificar ejecución previa')
    name=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    publicar_json(ROOT/'Otros'/'benchmarks'/'preparacion'/f'{name}_{args.engine}.json',report)
    if report['issues']:
        raise RuntimeError('; '.join(report['issues']))
    print(f"Preparación verificada: {args.engine}; espacio libre {free/1024**3:.1f} GiB",flush=True)


if __name__ == '__main__': main()
