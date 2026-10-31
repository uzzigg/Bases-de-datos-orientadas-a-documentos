"""Audita cobertura real y profiler antes de aprobar un piloto MongoDB."""
import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from cargar_datos import ROOT, env_vars


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9_-]{1,50}', args.run_id):
        parser.error('run_id inválido')
    directory = ROOT / 'Otros' / 'benchmarks' / args.run_id
    detail = json.loads((directory / 'detail.json').read_text(encoding='utf-8'))
    metrics = json.loads((directory / 'metrics.json').read_text(encoding='utf-8'))
    config = json.loads((directory / 'config.json').read_text(encoding='utf-8'))
    if config['engine'] != 'mongo' or not detail['full_protocol']:
        raise ValueError('La auditoría requiere un piloto MongoDB con protocolo completo')
    duration = detail['phase_seconds']['measurement']
    start_mono = detail['cgroup_start']['at_monotonic'] - (detail['cgroup_start']['at_epoch'] - detail['row']['timestamp_epoch'])
    end_mono = start_mono + duration
    start_epoch = detail['row']['timestamp_epoch']
    end_epoch = detail['cgroup_end']['at_epoch'] - (detail['cgroup_end']['at_monotonic'] - end_mono)
    checks = {}
    for name in ('rss', 'cpu', 'up'):
        series = metrics.get(name, [])
        checked = []
        for item in series:
            values = item.get('values', [])
            timestamps = [float(v[0]) for v in values]
            gaps = [b-a for a, b in zip(timestamps, timestamps[1:])]
            coverage = min(1, len(values)/duration)
            okay = bool(values) and coverage >= 0.9 and (not gaps or max(gaps) <= 2.5)
            okay = okay and timestamps[0] <= start_epoch + 2.5 and timestamps[-1] >= end_epoch - 2.5
            if name == 'up':
                okay = okay and all(float(v[1]) == 1 for v in values)
            checked.append({'samples': len(values), 'coverage': coverage, 'max_gap_seconds': max(gaps) if gaps else None, 'passed': okay})
        checks[name] = checked
    events = []
    for path in sorted(directory.glob('worker_*.jsonl')):
        with path.open(encoding='utf-8') as f:
            events.extend(json.loads(line) for line in f)
    expected = {e['marker'] for e in events if e['started'] < end_mono and e['finished'] >= start_mono}
    from pymongo import MongoClient
    env = env_vars()
    client = MongoClient('127.0.0.1', int(env['MONGO_PORT']), username=env['MONGO_USER'], password=env['MONGO_PASSWORD'], authSource='admin', serverSelectionTimeoutMS=15000)
    db = client['document_benchmark']
    profile_status = db.command('profile', -1)['was']
    prefix = 'bench_' + args.run_id + '_'
    records = list(db.system.profile.find({'op': 'command', 'command.aggregate': 'cosechas', 'command.comment': {'$regex': '^' + re.escape(prefix)}}, {'command.comment': 1, 'usedDisk': 1, '_id': 0}))
    by_marker = {r['command']['comment']: r for r in records}
    missing = sorted(expected - by_marker.keys())
    spills = sorted(marker for marker in expected if by_marker.get(marker, {}).get('usedDisk') is True)
    client.close()
    spill_consistent = not missing and detail['row']['disk_spill'] == str(bool(spills)).lower()
    telemetry_ok = all(checks[name] and all(s['passed'] for s in checks[name]) for name in checks)
    result = {'run_id': args.run_id, 'telemetry': checks, 'wall_clock_window_seconds': end_epoch-start_epoch,
              'profile_level_after_run': profile_status, 'overlapping_operations': len(expected),
              'missing_profile_markers': missing, 'spilled_markers': spills, 'spill_consistent': spill_consistent,
              'clock_preflight_passed': detail.get('clock_preflight', {}).get('passed', False),
              'clock_postflight_passed': detail.get('clock_postflight', {}).get('passed', False),
              'approved': bool(detail['row']['status'] in ('ok', 'spill') and telemetry_ok and spill_consistent and profile_status == 0 and abs(end_epoch-start_epoch-duration) < 1 and detail.get('clock_preflight', {}).get('passed') and detail.get('clock_postflight', {}).get('passed'))}
    with (directory / 'audit.json').open('x', encoding='utf-8', newline='\n') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['approved'] else 2


if __name__ == '__main__':
    sys.exit(main())
