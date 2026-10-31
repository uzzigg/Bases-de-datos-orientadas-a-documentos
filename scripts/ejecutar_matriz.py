"""Enumera o ejecuta la matriz, conservando intentos y deteniendo ante dudas."""
import argparse
import csv
import hashlib
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / 'protocolo.json').read_text(encoding='utf-8'))


def scenarios():
    randomizer = random.Random(PROTOCOL['dataset']['seed'])
    groups = [(e, p) for e in ('mongo', 'postgres') for p in ('A', 'B', 'C')]
    randomizer.shuffle(groups)
    runs = []
    for engine, profile in groups:
        queries = ('Q1', 'Q2_NO_DISK', 'Q2_DISK') if engine == 'mongo' else ('Q1', 'Q2_4MB', 'Q2_64MB')
        cells = [(q, c) for q in queries for c in PROTOCOL['concurrency']]
        randomizer.shuffle(cells)
        for query, concurrency in cells:
            for repetition in range(1, PROTOCOL['repetitions'] + 1):
                runs.append({'engine': engine, 'profile': profile, 'query': query, 'concurrency': concurrency, 'run_number': repetition})
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Ejecuta la matriz completa')
    parser.add_argument('--matrix-id', default='principal', help='Identificador estable, máximo 12 caracteres')
    parser.add_argument('--pilot-id', default='piloto_mongo_q1_01', help='Piloto completo aprobado antes de ejecutar')
    args = parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9_-]{1,12}', args.matrix_id):
        parser.error('matrix-id inválido')
    runs = scenarios()
    if len(runs) != 162 or len({tuple(sorted(r.items())) for r in runs}) != 162:
        raise RuntimeError('La matriz no contiene 162 repeticiones únicas')
    if not args.execute:
        print(json.dumps({'cells': 54, 'repetitions': len(runs), 'minimum_hours': 18.9, 'runs': runs}, ensure_ascii=False, indent=2))
        return 0
    home = ROOT / 'Otros' / 'benchmarks'
    home.mkdir(parents=True, exist_ok=True)
    if not re.fullmatch('[A-Za-z0-9_-]{1,50}', args.pilot_id):
        parser.error('pilot-id inválido')
    pilot_file = home / args.pilot_id / 'detail.json'
    if not pilot_file.is_file():
        raise RuntimeError('Se requiere un piloto completo aprobado antes de ejecutar la matriz')
    pilot = json.loads(pilot_file.read_text(encoding='utf-8'))
    if not pilot.get('full_protocol') or pilot['row']['status'] not in ('ok', 'spill') or pilot.get('telemetry_error'):
        raise RuntimeError('El piloto no está aprobado; revise la evidencia antes de continuar')
    audit_file = home / args.pilot_id / 'audit.json'
    if not audit_file.is_file() or not json.loads(audit_file.read_text(encoding='utf-8')).get('approved'):
        raise RuntimeError('La auditoría independiente del piloto no está aprobada')
    pilot_config = json.loads((home / args.pilot_id / 'config.json').read_text(encoding='utf-8'))
    source_hashes = pilot_config.get('source_sha256', {})
    expected_paths = {'benchmark_runner.py', 'protocolo.json', 'queries/mongo_q1.json', 'queries/mongo_q2.json', 'queries/postgres_q1.sql', 'queries/postgres_q2.sql'}
    if set(source_hashes) != expected_paths or any(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != value for name, value in source_hashes.items()):
        raise RuntimeError('El piloto no corresponde al código o protocolo actual; se necesita otro piloto')
    def completed(case, output):
        detail = output / 'detail.json'
        csvfile = output / 'measurement.csv'
        if not detail.exists() or not csvfile.exists():
            raise RuntimeError(f'Intento incompleto {output.name}; revise evidencia antes de continuar')
        data = json.loads(detail.read_text(encoding='utf-8'))
        with csvfile.open(encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if reader.fieldnames != PROTOCOL['csv_columns'] or len(rows) != 1:
                raise RuntimeError(f'CSV incorrecto: {output.name}')
        row = data['row']
        expected = ('mongodb' if case['engine'] == 'mongo' else 'postgresql', {'A': 'PROFILE_A_BASELINE', 'B': 'PROFILE_B_MEDIUM', 'C': 'PROFILE_C_SEVERE'}[case['profile']], case['query'], case['concurrency'], case['run_number'])
        if (row['engine'], row['profile'], row['query_id'], row['concurrency'], row['run_number']) != expected or rows[0]['status'] != row['status']:
            raise RuntimeError(f'Identidad o estado incoherente: {output.name}')
        if not data.get('full_protocol') or data.get('telemetry_error') or row['disk_spill'] == '' or row['status'] not in ('ok', 'spill', 'oom', 'error'):
            raise RuntimeError(f'Intento {output.name} requiere revisión: {row["status"]}')
        return data
    lock = home / '.matriz.lock'
    token = uuid.uuid4().hex
    try:
        with lock.open('x', encoding='utf-8') as f:
            json.dump({'pid': os.getpid(), 'matrix_id': args.matrix_id, 'token': token}, f)
    except FileExistsError:
        raise RuntimeError('Ya existe bloqueo de matriz; compruebe si el proceso sigue activo')
    try:
        if (home / '.runner.lock').exists():
            raise RuntimeError('Existe un runner activo o interrumpido; revise su bloqueo')
        log_path = home / f'matriz_{args.matrix_id}.log'
        with log_path.open('a', encoding='utf-8') as log:
            for number, case in enumerate(runs, 1):
                run_id = f"m_{args.matrix_id}_{case['engine']}_{case['profile']}_{case['query']}_{case['concurrency']}_{case['run_number']}"
                output = home / run_id
                if output.exists():
                    data = completed(case, output)
                    print(f'[{number}/162] ya completado: {run_id}', flush=True)
                    continue
                print(f'[{number}/162] {run_id}', flush=True)
                stack = ['powershell.exe', '-NoProfile', '-File', str(ROOT / 'scripts/stack.ps1'), '-Action', 'Up', '-Engine', case['engine'], '-Profile', case['profile']]
                started = subprocess.run(stack, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                if started.returncode:
                    raise RuntimeError(f'No arrancó el perfil {run_id}; revisar {log_path}')
                cmd = [sys.executable, str(ROOT / 'benchmark_runner.py'), '--engine', case['engine'], '--profile', case['profile'], '--query', case['query'], '--concurrency', str(case['concurrency']), '--run-number', str(case['run_number']), '--run-id', run_id]
                child_env = dict(os.environ, BENCH_MATRIX_TOKEN=token)
                result = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=child_env)
                if result.returncode:
                    if not output.exists():
                        raise RuntimeError(f'La ejecución {run_id} no produjo evidencia (código {result.returncode})')
                    completed(case, output)
        # La consolidación solo incluye filas completas; no altera evidencia.
        output = ROOT / 'resultados' / f'matriz_{args.matrix_id}.csv'
        if output.exists():
            raise FileExistsError(f'Ya existe {output}; no se sobrescribe')
        temporary = home / f'matriz_{args.matrix_id}.csv.tmp'
        with temporary.open('x', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=PROTOCOL['csv_columns'])
            writer.writeheader()
            for case in runs:
                run_id = f"m_{args.matrix_id}_{case['engine']}_{case['profile']}_{case['query']}_{case['concurrency']}_{case['run_number']}"
                detail = completed(case, home / run_id)
                writer.writerow(detail['row'])
            f.flush()
            os.fsync(f.fileno())
        os.rename(temporary, output)
        print(f'Matriz completa: {output}')
        return 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'Matriz detenida: {exc}', file=sys.stderr)
        sys.exit(1)
