"""Ejecuta consultas y planes por motor; compara resultados sin medir rendimiento."""
import argparse
import decimal
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from cargar_datos import env_vars, ROOT

QUERY = ROOT / 'queries'
OUT = ROOT / 'Otros/consultas/validacion_01'


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        f.write('\n')


def mongo():
    from bson import json_util
    from pymongo import MongoClient
    env = env_vars()
    client = MongoClient('127.0.0.1', int(env['MONGO_PORT']), username=env['MONGO_USER'], password=env['MONGO_PASSWORD'], authSource='admin', serverSelectionTimeoutMS=15000)
    db = client['document_benchmark']
    for query, variant, allow in [('q1', 'disk', True), ('q2', 'no_disk', False), ('q2', 'disk', True)]:
        pipeline = json.loads((QUERY / f'mongo_{query}.json').read_text(encoding='utf-8'))
        rows = list(db.orders.aggregate(pipeline, allowDiskUse=allow))
        if query == 'q1':
            normalized = [{'country': r['_id']['country'], 'category': r['_id']['category'], 'total_revenue': r['total_revenue'], 'avg_revenue': r['avg_revenue'], 'count': r['count']} for r in rows]
        else:
            normalized = [{'order_id': r['order_id'], 'customer_id': r['customer']['id'], 'final_total': r['payment']['final_total']} for r in rows]
        save(f'mongo_{query}_{variant}_result.json', normalized)
        plan = db.command({'explain': {'aggregate': 'orders', 'pipeline': pipeline, 'cursor': {}, 'allowDiskUse': allow}, 'verbosity': 'executionStats'})
        save(f'mongo_{query}_{variant}_plan.json', json.loads(json_util.dumps(plan)))
        print(f'MongoDB {query}/{variant}: {len(rows)} filas y plan guardados', flush=True)
    client.close()


def postgres():
    import psycopg
    env = env_vars()
    with psycopg.connect(host='127.0.0.1', port=int(env['POSTGRES_PORT']), user=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'], dbname=env['POSTGRES_DB']) as conn:
        with conn.cursor() as cur:
            for query, variant, mem in [('q1', '4MB', '4MB'), ('q2', '4MB', '4MB'), ('q2', '64MB', '64MB')]:
                statement = (QUERY / f'postgres_{query}.sql').read_text(encoding='utf-8')
                cur.execute("SELECT set_config('work_mem', %s, false)", (mem,))
                cur.execute(statement)
                names = [column.name for column in cur.description]
                rows = [dict(zip(names, row)) for row in cur.fetchall()]
                save(f'postgres_{query}_{variant}_result.json', rows)
                cur.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + statement)
                save(f'postgres_{query}_{variant}_plan.json', cur.fetchone()[0])
                print(f'PostgreSQL {query}/{variant}: {len(rows)} filas y plan guardados', flush=True)


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def compare():
    q1m = read('mongo_q1_disk_result.json')
    q1p = read('postgres_q1_4MB_result.json')
    def keyed(rows):
        result = {(r['country'], r['category']): r for r in rows}
        if len(result) != len(rows):
            raise ValueError('Q1 contiene grupos duplicados')
        return result
    a, b = keyed(q1m), keyed(q1p)
    if a.keys() != b.keys():
        raise ValueError('Q1: grupos distintos')
    for key in a:
        for field in ('count', 'total_revenue'):
            if decimal.Decimal(str(a[key][field])) != decimal.Decimal(str(b[key][field])):
                raise ValueError(f'Q1: {field} distinto en {key}')
        if abs(decimal.Decimal(str(a[key]['avg_revenue'])) - decimal.Decimal(str(b[key]['avg_revenue']))) > decimal.Decimal('0.00000001'):
            raise ValueError(f'Q1: promedio distinto en {key}')
    variants = [read('mongo_q2_no_disk_result.json'), read('mongo_q2_disk_result.json'), read('postgres_q2_4MB_result.json'), read('postgres_q2_64MB_result.json')]
    for rows in variants:
        amounts = [decimal.Decimal(str(r['final_total'])) for r in rows]
        if len(rows) != 1000 or len({r['order_id'] for r in rows}) != 1000 or amounts != sorted(amounts, reverse=True):
            raise ValueError('Q2: cantidad, duplicados u orden inválidos')
    amounts = [[decimal.Decimal(str(r['final_total'])) for r in rows] for rows in variants]
    if any(values != amounts[0] for values in amounts[1:]):
        raise ValueError('Q2: los importes del Top-1000 difieren')
    cutoff = amounts[0][-1]
    above = [{r['order_id']: (r['customer_id'], str(r['final_total'])) for r in rows if decimal.Decimal(str(r['final_total'])) > cutoff} for rows in variants]
    if any(group != above[0] for group in above[1:]):
        raise ValueError('Q2: órdenes por encima del empate de corte difieren')
    for rows in variants[1:]:
        baseline = {r['order_id']: (r['customer_id'], decimal.Decimal(str(r['final_total']))) for r in variants[0]}
        for r in rows:
            if r['order_id'] in baseline and baseline[r['order_id']] != (r['customer_id'], decimal.Decimal(str(r['final_total']))):
                raise ValueError('Q2: datos de orden común difieren')
    result = {'q1_groups': len(a), 'q1_counts_and_sums_equal': True, 'q1_average_absolute_tolerance': '0.00000001',
              'q2_variants': 4, 'q2_rows_each': 1000, 'q2_amounts_equal': True, 'q2_cutoff': str(cutoff),
              'q2_rows_above_cutoff': len(above[0]), 'q2_note': 'El manual no especifica desempate; en el corte pueden variar las órdenes empatadas. Se compararon importes, órdenes por encima del corte y datos de IDs comunes.',
              'scope': 'Validación funcional y planes; no son mediciones del benchmark.'}
    save('comparacion.json', result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('mongo', 'postgres', 'compare'))
    parser.add_argument('--run', default='validacion_01', help='Nombre único de la carpeta de evidencia')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run):
        parser.error('--run solo admite letras, números, guion y guion bajo')
    OUT = ROOT / 'Otros' / 'consultas' / args.run
    {'mongo': mongo, 'postgres': postgres, 'compare': compare}[args.action]()
