"""Prueba de integracion de fase 1. Solo usa la biblioteca estandar de Python."""
import argparse
import datetime as dt
import json
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args):
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(f"Fallo {args[0]} (codigo {result.returncode}): {result.stderr[-4000:]}")
    return result.stdout.strip()


def read_env():
    return dict(line.split("=", 1) for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines() if line and not line.startswith("#") and "=" in line)


def fetch(url):
    with urllib.request.urlopen(url, timeout=8) as response:
        return json.load(response)


def eventually(fn, seconds=75):
    end = time.monotonic() + seconds
    error = None
    while time.monotonic() < end:
        try:
            return fn()
        except (AssertionError, OSError, ValueError, KeyError, RuntimeError) as exc:
            error = exc
            time.sleep(1)
    raise RuntimeError(f"No se cumplio la condicion: {error}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["mongo", "postgres"], required=True)
    parser.add_argument("--profile", choices=["A", "B", "C"], required=True)
    parser.add_argument("--restart", action="store_true", help="Comprobar persistencia tras reiniciar el motor")
    args = parser.parse_args()
    env = read_env()
    base = ["docker", "compose", "--env-file", ".env", "--env-file", f"config/recursos/{args.profile}.env", "--profile", args.engine]
    service = "mongodb" if args.engine == "mongo" else "postgresql"
    other = "postgresql" if args.engine == "mongo" else "mongodb"
    evidence = {"started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "engine": service, "profile": args.profile, "passed": False}
    out = ROOT / "Otros" / "fase1" / f"verify_{args.engine}_{args.profile}.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    def compose(*items):
        return run(base + list(items))

    def execdb(*items):
        return compose("exec", "-T", service, *items)

    def mongo(js):
        return execdb("mongosh", "--quiet", "--eval", "const a=db.getSiblingDB('admin');if(!a.auth(process.env.MONGO_INITDB_ROOT_USERNAME,process.env.MONGO_INITDB_ROOT_PASSWORD))quit(1);const p=db.getSiblingDB('document_benchmark');" + js)

    def postgres(sql):
        return execdb("sh", "-c", 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -At -c "$1"', "phase1", sql)

    try:
        run(["docker", "compose", "--env-file", ".env", "--env-file", f"config/recursos/{args.profile}.env", "--profile", "*", "stop", other])
        compose("up", "-d", "--wait", "--wait-timeout", "180")
        cid = compose("ps", "-q", service)
        inspect = json.loads(run(["docker", "inspect", cid]))[0]
        cpu, mib = {"A": (4, 4096), "B": (2, 2048), "C": (1, 1024)}[args.profile]
        assert inspect["HostConfig"]["NanoCpus"] == cpu * 1_000_000_000
        assert inspect["HostConfig"]["Memory"] == mib * 1048576
        assert inspect["HostConfig"]["MemorySwap"] == mib * 1048576
        assert inspect["HostConfig"]["RestartPolicy"]["Name"] == "no"
        raw = execdb("sh", "-c", "cat /sys/fs/cgroup/cpu.max; cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/memory.swap.max; cat /sys/fs/cgroup/cpu.stat; cat /sys/fs/cgroup/memory.events")
        lines = raw.splitlines()
        assert lines[0] == f"{cpu * 100000} 100000", raw
        assert int(lines[1]) == mib * 1048576 and lines[2] == "0", raw
        evidence["limits"] = {"cpus": cpu, "memory_mib": mib, "swap_bytes": 0, "cgroups": raw}
        evidence["image_id"] = inspect["Image"]
        evidence["container_id"] = cid
        evidence["mounts"] = [{"type": m["Type"], "destination": m["Destination"], "name": m.get("Name")} for m in inspect["Mounts"]]
        token = str(uuid.uuid4())
        if args.engine == "mongo":
            evidence["engine_version"] = mongo("print(a.version())")
            mongo(f"p.getCollection('_phase1_probe').insertOne({{_id:'{token}',value:42}})")
        else:
            evidence["engine_version"] = postgres("SHOW server_version;")
            postgres("CREATE SCHEMA IF NOT EXISTS _phase1; CREATE TABLE IF NOT EXISTS _phase1.probes (id text PRIMARY KEY, value integer);")
            postgres(f"INSERT INTO _phase1.probes VALUES ('{token}',42);")
        if args.restart:
            compose("restart", service)

        def verify_data():
            if args.engine == "mongo":
                assert mongo(f"const r=p.getCollection('_phase1_probe').findOne({{_id:'{token}'}});print(r?r.value:'missing')") == "42"
            else:
                assert postgres(f"SELECT value FROM _phase1.probes WHERE id='{token}';") == "42"
            return True

        evidence["persistence_after_restart"] = eventually(verify_data) if args.restart else None
        if not args.restart:
            verify_data()
        if args.engine == "mongo":
            mongo(f"p.getCollection('_phase1_probe').deleteOne({{_id:'{token}'}})")
        else:
            postgres(f"DELETE FROM _phase1.probes WHERE id='{token}';")

        url = f"http://127.0.0.1:{env.get('PROMETHEUS_PORT', '9090')}"

        def targets():
            data = fetch(url + "/api/v1/targets")["data"]["activeTargets"]
            assert len(data) == 3 and all(t["health"] == "up" for t in data), [(t["labels"], t["health"], t["lastError"]) for t in data]
            return [{"job": t["labels"]["job"], "health": t["health"], "scrape_interval": t["scrapeInterval"]} for t in data]

        evidence["targets"] = eventually(targets)

        def metric(name, selector=""):
            data = fetch(url + "/api/v1/query?" + urllib.parse.urlencode({"query": name + selector}))
            assert data["status"] == "success"
            result = data["data"]["result"]
            assert result, f"Sin muestras: {name}{selector}"
            return result

        # Identificar por ID evita confundir contenedores antiguos de otro perfil.
        selector = '{id=~".*' + cid + '.*"}'
        evidence["metrics"] = {}
        for name in ("container_cpu_usage_seconds_total", "container_cpu_cfs_throttled_seconds_total", "container_memory_rss", "container_last_seen"):
            evidence["metrics"][name] = eventually(lambda n=name: metric(n, selector))
        for name in ("node_memory_MemAvailable_bytes", "node_vmstat_pswpin", "node_vmstat_pswpout", "node_disk_read_bytes_total"):
            evidence["metrics"][name] = eventually(lambda n=name: metric(n))
        evidence["passed"] = True
        print(f"PASS {service}/{args.profile}: limites, conexion, datos y telemetria" + (", persistencia" if args.restart else ""))
    except Exception as exc:
        evidence["error"] = str(exc)
        raise
    finally:
        evidence["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
