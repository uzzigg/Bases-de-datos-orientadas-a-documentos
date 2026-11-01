"""Conserva muestras adicionales de memoria para una corrida terminada."""
import argparse
import json
import re
import sys
import time
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from benchmark_runner import PROTOCOL, env_vars, prometheus
from archivos_evidencia import publicar_json


def consultar_con_reintentos(env, query, start, end):
    for attempt in range(3):
        try:
            return prometheus(env, query, start, end)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            # Un error de autenticación o de consulta no se corrige esperando.
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (408, 429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9_-]{1,50}', args.run_id):
        parser.error('run_id inválido')
    folder = ROOT / 'Otros' / 'benchmarks' / args.run_id
    config = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    detail = json.loads((folder / 'detail.json').read_text(encoding='utf-8'))
    output = folder / 'memory_extra.json'
    if output.exists():
        raise FileExistsError('Ya existe evidencia adicional; no se sobrescribe')
    start = float(detail['row']['timestamp_epoch'])
    duration = detail['phase_seconds']['measurement']
    end = start + duration
    selector = '{id=~".*' + config['container_id'] + '.*"}'
    extra = {}
    for name in ('container_memory_usage_bytes', 'container_memory_working_set_bytes', 'container_memory_cache'):
        series = consultar_con_reintentos(env_vars(), name + selector, start, end)
        if len(series) != 1 or not series[0].get('values'):
            raise RuntimeError(f'No hay una serie válida: {name}')
        stamps = [float(v[0]) for v in series[0]['values']]
        gaps = [b-a for a, b in zip(stamps, stamps[1:])]
        if len(stamps) / duration < 0.9 or (gaps and max(gaps) > PROTOCOL['max_telemetry_gap_seconds']) or stamps[0] > start + 2.5 or stamps[-1] < end - 2.5:
            raise RuntimeError(f'Cobertura insuficiente: {name}')
        extra[name] = series
    result = {'scope': 'Métricas adicionales; uso incluye caché y memoria compartida, no equivale a RSS',
              'run_id': args.run_id, 'passed': True, 'window_start_epoch': start, 'window_end_epoch': end,
              'metrics': extra}
    publicar_json(output, result)
    print('Memoria adicional capturada:', args.run_id)


if __name__ == '__main__':
    main()
