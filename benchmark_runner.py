"""Ejecuta una repetición del experimento y conserva evidencia por separado."""
import argparse
import csv
import contextlib
import hashlib
import json
import math
import multiprocessing as mp
import os
import queue
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'scripts'))
from cargar_datos import env_vars  # noqa: E402

PROTOCOL = json.loads((ROOT / 'protocolo.json').read_text(encoding='utf-8'))
PROFILE = {'A': 'PROFILE_A_BASELINE', 'B': 'PROFILE_B_MEDIUM', 'C': 'PROFILE_C_SEVERE'}


def execute(args, *, capture=True):
    result = subprocess.run(args, cwd=ROOT, text=True, encoding='utf-8', errors='replace', capture_output=capture)
    if result.returncode:
        raise RuntimeError(f'{args[0]} terminó con código {result.returncode}: {(result.stderr or "")[-1000:]}')
    return result.stdout if capture else ''


def connect(engine, env):
    if engine == 'mongo':
        from pymongo import MongoClient
        client = MongoClient('127.0.0.1', int(env['MONGO_PORT']), username=env['MONGO_USER'], password=env['MONGO_PASSWORD'], authSource='admin', serverSelectionTimeoutMS=15000, socketTimeoutMS=330000, appname='documental-benchmark')
        client.admin.command('ping')
        return client
    import psycopg
    return psycopg.connect(host='127.0.0.1', port=int(env['POSTGRES_PORT']), user=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'], dbname=env['POSTGRES_DB'], connect_timeout=15, autocommit=True)


def worker(index, args, env, start_event, start_value, ready, directory):
    connection = None
    try:
        connection = connect(args.engine, env)
        if args.engine == 'postgres':
            cur = connection.cursor()
            memory = '64MB' if args.query == 'Q2_64MB' else '4MB'
            cur.execute("SELECT set_config('work_mem', %s, false), set_config('statement_timeout','310000',false), pg_backend_pid()", (memory,))
            _, _, pid = cur.fetchone()
            sql = (ROOT / 'agricola' / ('postgres_q1.sql' if args.query == 'Q1' else 'postgres_q2.sql')).read_text(encoding='utf-8')
        else:
            pid = None
            pipeline = json.loads((ROOT / 'agricola' / ('mongo_q1.json' if args.query == 'Q1' else 'mongo_q2.json')).read_text(encoding='utf-8'))
        ready.put({'worker': index, 'ready': True, 'pid': pid})
        if not start_event.wait(90):
            raise TimeoutError('No llegó la señal de inicio')
        start = start_value.value
        measure_start, measure_end = start + args.warmup, start + args.warmup + args.measurement
        while time.monotonic() < start:
            time.sleep(min(0.05, start-time.monotonic()))
        seq = 0
        with (directory / f'worker_{index:02d}.jsonl').open('x', encoding='utf-8', buffering=1) as log:
            while time.monotonic() < measure_end:
                begin = time.monotonic()
                marker = f'bench_{args.run_id}_{index}_{seq}'
                record = {'marker': marker, 'started': begin, 'phase': 'measurement' if begin >= measure_start else 'warmup'}
                try:
                    if args.engine == 'mongo':
                        cursor = connection['document_benchmark'].cosechas.aggregate(pipeline, allowDiskUse=args.query != 'Q2_NO_DISK', maxTimeMS=310000, comment=marker)
                        count = sum(1 for _ in cursor)
                    else:
                        cur.execute(f'/* {marker} */ ' + sql)
                        count = len(cur.fetchall())
                    if count != (20 if args.query == 'Q1' else 1000):
                        raise ValueError(f'Cantidad inesperada de filas: {count}')
                    record.update(ok=True, rows=count)
                except Exception as exc:
                    record.update(ok=False, error=f'{type(exc).__name__}: {str(exc)[:350]}')
                record['finished'] = time.monotonic()
                record['latency_ms'] = (record['finished'] - begin) * 1000
                log.write(json.dumps(record, ensure_ascii=False) + '\n')
                seq += 1
                if not record['ok']:
                    break
    except Exception as exc:
        ready.put({'worker': index, 'ready': False, 'error': f'{type(exc).__name__}: {str(exc)[:350]}'})
    finally:
        if connection:
            connection.close()


def stats(cid):
    raw = execute(['docker', 'exec', cid, 'sh', '-c', 'cat /sys/fs/cgroup/cpu.stat; echo ---; cat /sys/fs/cgroup/memory.events'])
    cpu, memory = raw.split('---', 1)
    def parse(text):
        return {key: int(value) for key, value in (line.split() for line in text.splitlines() if line.strip())}
    return {'at_epoch': time.time(), 'at_monotonic': time.monotonic(), 'cpu': parse(cpu), 'memory_events': parse(memory)}


def wait_until(target):
    while time.monotonic() < target:
        time.sleep(min(0.5, target-time.monotonic()))


def clock_check():
    # Compara CLOCK_MONOTONIC con MONOTONIC_RAW dentro de WSL; el segundo
    # contrasta además con perf_counter de Windows. No altera el reloj.
    code = ('import time,json; m=time.monotonic(); r=time.clock_gettime(time.CLOCK_MONOTONIC_RAW); '
            'time.sleep(5); print(json.dumps({"monotonic":time.monotonic()-m,"raw":time.clock_gettime(time.CLOCK_MONOTONIC_RAW)-r}))')
    before = time.perf_counter()
    result = json.loads(execute(['wsl', '-d', 'Ubuntu', '--', 'python3', '-c', code]))
    result['host_elapsed_including_wsl_startup'] = time.perf_counter() - before
    result['rate_difference'] = abs(result['monotonic'] / result['raw'] - 1) if result['raw'] > 0 else 1
    result['host_raw_difference_seconds'] = abs(result['host_elapsed_including_wsl_startup'] - result['raw'])
    result['passed'] = result['rate_difference'] < PROTOCOL['max_clock_rate_difference_exclusive'] and result['host_raw_difference_seconds'] <= 0.75
    return result


def prometheus(env, query, start, end):
    # Vector de rango: conserva marcas de tiempo reales, sin interpolar valores
    # antiguos en cada paso de query_range.
    duration = max(1, math.ceil(end - start))
    query_string = urllib.parse.urlencode({'query': f'{query}[{duration}s]', 'time': f'{end:.3f}'})
    with urllib.request.urlopen(f"http://127.0.0.1:{env.get('PROMETHEUS_PORT', '9090')}/api/v1/query?{query_string}", timeout=30) as response:
        payload = json.load(response)
    if payload.get('status') != 'success':
        raise RuntimeError('Consulta de Prometheus falló')
    return payload['data']['result']


def percentile(values, p):
    if not values:
        return ''
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(p * len(ordered))-1)], 3)


def prepare_profiler(env):
    client = connect('mongo', env)
    db = client['document_benchmark']
    previous = db.command('profile', -1)
    if previous['was'] != 0:
        client.close()
        raise RuntimeError('El profiler de MongoDB ya está activado; revise antes de cambiarlo')
    db.command('profile', 2)
    return client, previous


@contextlib.contextmanager
def experiment_lock():
    directory = ROOT / 'Otros' / 'benchmarks'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / '.runner.lock'
    try:
        with path.open('x', encoding='utf-8') as f:
            json.dump({'pid': os.getpid(), 'created_epoch': time.time()}, f)
    except FileExistsError as exc:
        raise RuntimeError('Ya existe .runner.lock: revise si hay una corrida activa antes de continuar') from exc
    try:
        matrix_lock = directory / '.matriz.lock'
        if matrix_lock.exists():
            lock_data = json.loads(matrix_lock.read_text(encoding='utf-8'))
            if not os.environ.get('BENCH_MATRIX_TOKEN') or os.environ['BENCH_MATRIX_TOKEN'] != lock_data.get('token'):
                raise RuntimeError('Existe una matriz activa o interrumpida; revise su bloqueo')
        yield
    finally:
        path.unlink(missing_ok=True)


def get_spill(args, env, directory, events, measure_epoch, window_end_epoch, profiler):
    relevant = events
    if args.engine == 'mongo':
        client, _ = profiler
        db = client['document_benchmark']
        db.command('profile', 0)
        prefix = f'bench_{args.run_id}_'
        docs = list(db.system.profile.find({'op': 'command', 'command.aggregate': 'cosechas', 'command.comment': {'$regex': '^' + re.escape(prefix)}}, {'command.comment': 1, 'usedDisk': 1, 'errCode': 1, '_id': 0}))
        matching = {d['command']['comment']: d for d in docs}
        expected = {e['marker'] for e in relevant}
        missing = sorted(expected - matching.keys())
        spilled = [marker for marker in expected if matching.get(marker, {}).get('usedDisk') is True]
        detail = {'method': 'MongoDB profiler nivel 2 (agrega sobrecarga)', 'expected': len(expected), 'profile_records': len(matching), 'missing': len(missing), 'spilled_markers': spilled}
        client.close()
        return (True if spilled else None if missing else False), detail
    # log_temp_files=0 reporta cada archivo temporal. Los mensajes se conservan
    # completos; si no puede asociarse al periodo se marca la evidencia como parcial.
    proc = subprocess.run(['docker', 'logs', '--timestamps', '--since', str(int(measure_epoch)), '--until', str(math.ceil(window_end_epoch)), args.container_id], cwd=ROOT, text=True, encoding='utf-8', errors='replace', capture_output=True)
    if proc.returncode:
        raise RuntimeError(f'No se pudo leer el log PostgreSQL: {proc.stderr[-500:]}')
    log = proc.stdout + '\n' + proc.stderr
    (directory / 'postgres_docker.log').write_text(log, encoding='utf-8')
    lines = log.splitlines()
    temporary = [line for line in lines if 'temporary file:' in line]
    return (True if temporary else False), {'method': 'PostgreSQL log_temp_files=0, ventana ampliada hasta fin de consultas iniciadas', 'temporary_file_lines': temporary, 'note': 'Un archivo temporal en el límite puede corresponder a una consulta de calentamiento o posterior al final de ventana.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('mongo', 'postgres'), required=True)
    parser.add_argument('--profile', choices=('A', 'B', 'C'), required=True)
    parser.add_argument('--query', required=True)
    parser.add_argument('--concurrency', type=int, choices=(1, 10, 50), required=True)
    parser.add_argument('--run-number', type=int, default=1, choices=(1, 2, 3))
    parser.add_argument('--warmup', type=int, default=60)
    parser.add_argument('--measurement', type=int, default=300)
    parser.add_argument('--cooldown', type=int, default=60)
    parser.add_argument('--run-id', default=None)
    args = parser.parse_args()
    allowed = {'mongo': ('Q1', 'Q2_NO_DISK', 'Q2_DISK'), 'postgres': ('Q1', 'Q2_4MB', 'Q2_64MB')}
    if args.query not in allowed[args.engine] or args.warmup < 0 or args.measurement < 1 or args.cooldown < 0:
        parser.error('Consulta o duraciones inválidas')
    args.run_id = args.run_id or uuid.uuid4().hex[:12]
    if not re.fullmatch('[A-Za-z0-9_-]{1,50}', args.run_id):
        parser.error('run-id inválido')
    directory = ROOT / 'Otros' / 'benchmarks' / args.run_id
    directory.mkdir(parents=True, exist_ok=False)
    env = env_vars()
    service = 'mongodb' if args.engine == 'mongo' else 'postgresql'
    compose = ['docker', 'compose', '--env-file', '.env', '--env-file', f'config/recursos/{args.profile}.env', '--profile', args.engine]
    cid = execute(compose + ['ps', '-q', service]).strip()
    if not cid:
        raise RuntimeError('El motor no está activo')
    args.container_id = cid
    inspect = json.loads(execute(['docker', 'inspect', cid]))[0]
    if inspect['Config']['Labels'].get('experiment.profile') != PROFILE[args.profile]:
        raise RuntimeError('El perfil activo no coincide')
    expected_cpu, expected_memory = {'A': (4, 4096), 'B': (2, 2048), 'C': (1, 1024)}[args.profile]
    if (inspect['HostConfig']['NanoCpus'], inspect['HostConfig']['Memory'], inspect['HostConfig']['MemorySwap']) != (expected_cpu * 10**9, expected_memory * 1048576, expected_memory * 1048576):
        raise RuntimeError('Los límites reales no coinciden con el perfil')
    other = 'postgresql' if args.engine == 'mongo' else 'mongodb'
    if execute(['docker', 'compose', '--env-file', '.env', '--env-file', f'config/recursos/{args.profile}.env', '--profile', '*', 'ps', '-q', other]).strip():
        raise RuntimeError('El otro motor también está activo; deténgalo antes de medir')
    connection = connect(args.engine, env)
    if args.engine == 'postgres':
        with connection.cursor() as cur:
            cur.execute('SHOW log_temp_files')
            if cur.fetchone()[0] != '0':
                raise RuntimeError('log_temp_files debe ser 0')
            cur.execute('SELECT count(*) FROM public.cosechas')
            count = cur.fetchone()[0]
    else:
        count = connection['document_benchmark'].cosechas.count_documents({})
    connection.close()
    if count != PROTOCOL['dataset']['orders']:
        raise RuntimeError(f'Conteo de órdenes incorrecto: {count}')
    clock_before = clock_check()
    (directory / 'clock_preflight.json').write_text(json.dumps(clock_before, indent=2), encoding='utf-8')
    if not clock_before['passed']:
        raise RuntimeError('Reloj WSL inestable: la repetición no se inició; consulte clock_preflight.json')
    files = ['benchmark_runner.py', 'protocolo.json', 'agricola/mongo_q1.json', 'agricola/mongo_q2.json', 'agricola/postgres_q1.sql', 'agricola/postgres_q2.sql']
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
    config = {**vars(args), 'source_sha256': hashes, 'orders_preflight': count, 'image_id': inspect['Image'], 'python_version': sys.version}
    (directory / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    print(f'Repetición {args.run_id}: limpieza de caché y preparación de clientes', flush=True)
    execute(['wsl', '-d', 'docker-desktop', '-u', 'root', '--', 'sh', '-c', 'sync; echo 3 > /proc/sys/vm/drop_caches'])
    profiler = prepare_profiler(env) if args.engine == 'mongo' else None
    context = mp.get_context('spawn')
    start_event, ready, start_value = context.Event(), context.Queue(), context.Value('d', 0.0)
    processes = [context.Process(target=worker, args=(i, args, env, start_event, start_value, ready, directory)) for i in range(args.concurrency)]
    try:
        for process in processes:
            process.start()
        clients = [ready.get(timeout=90) for _ in processes]
        if not all(item['ready'] for item in clients):
            raise RuntimeError(f'Fallaron conexiones: {clients}')
        start_value.value = time.monotonic() + 3
        start_event.set()
        measurement_start = start_value.value + args.warmup
        measurement_end = measurement_start + args.measurement
        wait_until(measurement_start)
        begin = stats(cid)
        print('Medición iniciada', flush=True)
        wait_until(measurement_end)
        end = stats(cid)
        print('Medición terminada; esperando consultas en curso', flush=True)
        wait_until(measurement_end + args.cooldown)
        join_deadline = time.monotonic() + 330
        for process in processes:
            process.join(max(0, join_deadline - time.monotonic()))
            if process.is_alive():
                raise TimeoutError('Un proceso no terminó dentro del límite')
            if process.exitcode:
                raise RuntimeError(f'Proceso de cliente terminó con {process.exitcode}')
        clock_after = clock_check()
        finish_epoch = time.time()
        events = []
        for i in range(args.concurrency):
            with (directory / f'worker_{i:02d}.jsonl').open(encoding='utf-8') as f:
                events.extend(json.loads(line) for line in f)
        inside = [e for e in events if e['started'] >= measurement_start and e['finished'] <= measurement_end]
        completed = [e for e in events if e['ok'] and measurement_start <= e['finished'] <= measurement_end]
        latencies = [e['latency_ms'] for e in inside if e['ok']]
        errors = [e for e in events if not e['ok'] and (e['started'] < measurement_end and e['finished'] >= measurement_start)]
        crossing = [e for e in events if e['started'] < measurement_end and e['finished'] > measurement_end]
        measure_epoch = begin['at_epoch'] - (begin['at_monotonic'] - measurement_start)
        end_epoch = end['at_epoch'] - (end['at_monotonic'] - measurement_end)
        selector = '{id=~".*' + cid + '.*"}'
        metrics = {}
        telemetry_error = None
        coverage = 0
        try:
            for name, query in [('rss', 'container_memory_rss' + selector), ('cpu', 'container_cpu_usage_seconds_total' + selector), ('up', 'up{job="cadvisor"}'), ('node_up', 'up{job="node-exporter"}'), ('host_swap_free', 'node_memory_SwapFree_bytes'), ('host_swap_out', 'node_vmstat_pswpout'), ('host_disk_read', 'node_disk_read_bytes_total'), ('host_disk_written', 'node_disk_written_bytes_total')]:
                metrics[name] = prometheus(env, query, measure_epoch, end_epoch)
            if any(not metrics[k] or not metrics[k][0]['values'] for k in metrics):
                raise RuntimeError('Faltan muestras de telemetría')
            values = metrics['rss'][0]['values']
            coverage = min(1.0, len(values) / args.measurement)
            for name in ('rss', 'cpu', 'up', 'node_up'):
                for series in metrics[name]:
                    samples = series['values']
                    stamps = [float(v[0]) for v in samples]
                    gaps = [b-a for a, b in zip(stamps, stamps[1:])]
                    if not stamps or len(stamps) / args.measurement < 0.9 or (gaps and max(gaps) > PROTOCOL['max_telemetry_gap_seconds']) or stamps[0] > measure_epoch + 2.5 or stamps[-1] < end_epoch - 2.5:
                        raise RuntimeError(f'Cobertura insuficiente o huecos en {name}: {len(stamps)} muestras')
                    if name in ('up', 'node_up') and any(float(v[1]) != 1 for v in samples):
                        raise RuntimeError(f'Recolector inactivo: {name}')
            rss = max(float(v[1]) for v in values) / 1048576
        except Exception as exc:
            telemetry_error, rss = str(exc), ''
        if not clock_after['passed']:
            telemetry_error = (telemetry_error + '; ' if telemetry_error else '') + 'Reloj WSL inestable al terminar'
        try:
            overlapping = [e for e in events if e['started'] < measurement_end and e['finished'] >= measurement_start]
            spill, spill_detail = get_spill(args, env, directory, overlapping, measure_epoch, finish_epoch, profiler)
            profiler = None
        except Exception as exc:
            spill, spill_detail = None, {'error': str(exc)}
        oom = end['memory_events'].get('oom_kill', 0) > begin['memory_events'].get('oom_kill', 0)
        invalid = bool(errors or telemetry_error or spill is None or not latencies)
        status = 'oom' if oom else 'error' if invalid else 'spill' if spill else 'ok'
        row = {'timestamp_epoch': round(measure_epoch, 3), 'engine': 'mongodb' if args.engine == 'mongo' else 'postgresql', 'profile': PROFILE[args.profile], 'query_id': args.query, 'concurrency': args.concurrency, 'run_number': args.run_number, 'throughput_qps': round(len(completed)/args.measurement, 6), 'latency_p50_ms': percentile(latencies, .50), 'latency_p95_ms': percentile(latencies, .95), 'latency_p99_ms': percentile(latencies, .99), 'cpu_throttled_seconds': round((end['cpu']['throttled_usec'] - begin['cpu']['throttled_usec'])/1e6, 6), 'max_rss_mb': round(rss, 3) if rss != '' else '', 'disk_spill': '' if spill is None else str(spill).lower(), 'status': status}
        detail = {'row': row, 'phase_seconds': {'warmup': args.warmup, 'measurement': args.measurement, 'cooldown': args.cooldown}, 'full_protocol': [args.warmup, args.measurement, args.cooldown] == [60, 300, 60], 'clients': clients, 'successful_completions_in_window': len(completed), 'latency_samples_fully_inside_window': len(latencies), 'queries_crossing_window_end': len(crossing), 'errors': errors, 'cgroup_start': begin, 'cgroup_end': end, 'cpu_usage_seconds': (end['cpu']['usage_usec'] - begin['cpu']['usage_usec'])/1e6, 'sample_coverage': coverage, 'telemetry_error': telemetry_error, 'spill': spill_detail, 'clock_preflight': clock_before, 'clock_postflight': clock_after, 'method_notes': ['QPS: éxitos terminados en ventana; percentiles: operaciones iniciadas y terminadas en ventana, nearest-rank.', 'Consultas que cruzan el cierre se conservan en eventos crudos, excluidas de percentiles.', 'Muestreo cgroup usa docker exec y añade una pequeña sobrecarga al contenedor.']}
        (directory / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
        (directory / 'detail.json').write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding='utf-8')
        with (directory / 'measurement.csv').open('x', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=PROTOCOL['csv_columns'])
            writer.writeheader()
            writer.writerow(row)
        print(json.dumps({'run_id': args.run_id, 'status': status, 'qps': row['throughput_qps'], 'latency_samples': len(latencies), 'coverage': coverage, 'spill': spill}, ensure_ascii=False), flush=True)
        return 0 if status in ('ok', 'spill') else 2
    except Exception as exc:
        # Un aborto nunca se presenta como ventana terminada; conserva una fila
        # con campos desconocidos vacíos y evidencia del estado del contenedor.
        try:
            state = json.loads(execute(['docker', 'inspect', cid]))[0]['State']
            oom = bool(state.get('OOMKilled'))
        except Exception:
            state, oom = {}, False
        row = {key: '' for key in PROTOCOL['csv_columns']}
        row.update({'engine': 'mongodb' if args.engine == 'mongo' else 'postgresql', 'profile': PROFILE[args.profile], 'query_id': args.query, 'concurrency': args.concurrency, 'run_number': args.run_number, 'status': 'oom' if oom else 'error'})
        detail = {'row': row, 'full_protocol': False, 'aborted': True, 'telemetry_error': f'{type(exc).__name__}: {exc}', 'container_state': state}
        if not (directory / 'detail.json').exists():
            (directory / 'detail.json').write_text(json.dumps(detail, indent=2, ensure_ascii=False), encoding='utf-8')
        if not (directory / 'measurement.csv').exists():
            with (directory / 'measurement.csv').open('x', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=PROTOCOL['csv_columns'])
                writer.writeheader()
                writer.writerow(row)
        raise
    finally:
        if profiler:
            try:
                profiler[0]['document_benchmark'].command('profile', 0)
                profiler[0].close()
            except Exception as exc:
                print(f'No se pudo restaurar profiler: {exc}', file=sys.stderr)
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)


if __name__ == '__main__':
    mp.freeze_support()
    try:
        with experiment_lock():
            result = main()
        sys.exit(result)
    except Exception as exc:
        print(f'Error de runner: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)
