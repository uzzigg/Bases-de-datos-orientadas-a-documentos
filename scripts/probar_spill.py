"""Comprueba la detección positiva de archivos temporales en PostgreSQL."""
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from benchmark_runner import connect, env_vars, execute, experiment_lock


def main():
    env = env_vars()
    cid = execute(['docker', 'compose', '--env-file', '.env', '--env-file', 'config/recursos/A.env', '--profile', 'postgres', 'ps', '-q', 'postgresql']).strip()
    if not cid:
        raise RuntimeError('PostgreSQL debe estar activo')
    marker = 'prueba_spill_' + uuid.uuid4().hex[:12]
    start = int(time.time()) - 1
    conn = connect('postgres', env)
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('work_mem','64kB',false)")
        cur.execute(f'/* {marker} */ SELECT count(*) FROM (SELECT n FROM generate_series(1, 200000) n ORDER BY n DESC OFFSET 0) t')
        if cur.fetchone()[0] != 200000:
            raise RuntimeError('Resultado de prueba inesperado')
    conn.close()
    logs = subprocess.run(['docker', 'logs', '--timestamps', '--since', str(start), cid], cwd=ROOT, text=True, encoding='utf-8', errors='replace', capture_output=True)
    if logs.returncode:
        raise RuntimeError('No fue posible leer el log de PostgreSQL')
    text = logs.stdout + '\n' + logs.stderr
    found = 'temporary file:' in text and marker in text
    output = ROOT / 'Otros' / 'benchmarks' / (marker + '.json')
    with output.open('x', encoding='utf-8') as f:
        json.dump({'engine': 'postgresql', 'test': 'ordenamiento sintético forzado a disco', 'marker': marker, 'temporary_file_detected': found, 'log': text}, f, ensure_ascii=False, indent=2)
    print('Prueba de detección positiva de spill:', 'OK' if found else 'NO DETECTADO')
    return 0 if found else 1


if __name__ == '__main__':
    with experiment_lock():
        sys.exit(main())
