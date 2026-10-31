"""Conserva muestras adicionales de memoria para una corrida terminada."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from benchmark_runner import PROTOCOL, env_vars, prometheus


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
        series = prometheus(env_vars(), name + selector, start, end)
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
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('Memoria adicional capturada:', args.run_id)


if __name__ == '__main__':
    main()
