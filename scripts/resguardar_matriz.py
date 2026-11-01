"""Respalda los CSV terminados y registra su calidad sin modificar la matriz."""
import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import re
import shutil
from pathlib import Path

from archivos_evidencia import publicar_bytes, publicar_json

ROOT = Path(__file__).resolve().parents[1]


def recopilar(root, matrix_id):
    from ejecutar_matriz import scenarios
    columns = json.loads((root / 'protocolo.json').read_text(encoding='utf-8'))['csv_columns']
    expected = {f"m_{matrix_id}_{c['engine']}_{c['profile']}_{c['query']}_{c['concurrency']}_{c['run_number']}": c for c in scenarios()}
    rows, evidence, issues = [], [], []
    for run_id, case in expected.items():
        folder = root / 'Otros' / 'benchmarks' / run_id
        detail, csvfile = folder / 'detail.json', folder / 'measurement.csv'
        if not detail.exists() or not csvfile.exists():
            continue
        try:
            raw = csvfile.read_bytes()
            reader = csv.DictReader(io.StringIO(raw.decode('utf-8')))
            records = list(reader)
            if reader.fieldnames != columns or len(records) != 1:
                raise ValueError('CSV con columnas o número de filas incorrectos')
            data = json.loads(detail.read_text(encoding='utf-8'))
            row = data['row']
            if any(records[0][key] != str(row[key]) for key in columns):
                raise ValueError('CSV y detail.json no coinciden')
            identity = ('mongodb' if case['engine'] == 'mongo' else 'postgresql',
                        {'A':'PROFILE_A_BASELINE','B':'PROFILE_B_MEDIUM','C':'PROFILE_C_SEVERE'}[case['profile']],
                        case['query'], case['concurrency'], case['run_number'])
            if tuple(row[k] for k in ('engine','profile','query_id','concurrency','run_number')) != identity:
                raise ValueError('Identidad del escenario incorrecta')
            rows.append(records[0])
            evidence.append({'run_id': run_id, 'status': row['status'],
                             'csv_sha256': hashlib.sha256(raw).hexdigest(),
                             'full_protocol': data.get('full_protocol', False),
                             'telemetry_error': data.get('telemetry_error'),
                             'spill_desconocido': row['disk_spill'] == '',
                             'memoria_extra_presente': (folder/'memory_extra.json').is_file()})
        except (OSError, ValueError, KeyError) as exc:
            issues.append({'run_id':run_id, 'error':str(exc)})
    return columns, rows, evidence, issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix-id', default='agricola')
    args = parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9_-]{1,12}', args.matrix_id):
        parser.error('matrix-id inválido')
    columns, rows, evidence, issues = recopilar(ROOT, args.matrix_id)
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader(); writer.writerows(rows)
    csvdata = buffer.getvalue().encode('utf-8')
    name = args.matrix_id + '_' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT / 'Otros' / 'respaldos_matriz'
    csvfile = folder / (name + '.csv')
    publicar_bytes(csvfile, csvdata)
    metadata = {'scope':'Respaldo parcial; no sustituye el CSV final ni certifica validez de las corridas',
                'matrix_id':args.matrix_id, 'filas':len(rows), 'previstas':162,
                'estados':dict(collections.Counter(x['status'] for x in rows)),
                'csv':csvfile.name, 'sha256':hashlib.sha256(csvdata).hexdigest(),
                'espacio_libre_gib':round(shutil.disk_usage(ROOT).free/1024**3,2),
                'evidencia':evidence, 'inconsistencias':issues}
    publicar_json(folder / (name + '.json'), metadata)
    print(json.dumps({k:metadata[k] for k in ('filas','previstas','estados','inconsistencias')},ensure_ascii=False))
    print(str(csvfile))
    return 2 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
