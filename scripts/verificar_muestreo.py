"""Comprueba muestras reales y frescura durante 20 segundos de monitoreo."""
import datetime as dt
import json
import statistics
import sys
import time
import urllib.parse
from pathlib import Path

sys.dont_write_bytecode = True
from verify_stack import fetch, read_env, run

root = Path(__file__).resolve().parents[1]
env = read_env()
api = "http://127.0.0.1:" + env.get("PROMETHEUS_PORT", "9090") + "/api/v1/query?"
base = ["docker", "compose", "--env-file", ".env", "--env-file", "config/recursos/C.env", "--profile", "*"]
cid = run(base + ["ps", "-q", "postgresql"])
if not cid:
    cid = run(base + ["ps", "-q", "mongodb"])
if not cid:
    raise RuntimeError("Se requiere un motor activo")
selector = '{id=~".*' + cid + '.*"}'
end = time.monotonic() + 22
while time.monotonic() < end:
    time.sleep(min(1, max(0, end - time.monotonic())))
query = "container_cpu_usage_seconds_total" + selector + "[20s]"
matrix = fetch(api + urllib.parse.urlencode({"query": query}))["data"]["result"]
if not matrix:
    raise RuntimeError("Sin muestras del contenedor activo")
rows = []
for series in matrix:
    samples = series["values"]
    gaps = [b[0] - a[0] for a, b in zip(samples, samples[1:])]
    rows.append({"samples": len(samples), "median_gap_seconds": statistics.median(gaps) if gaps else None, "max_gap_seconds": max(gaps) if gaps else None})
fresh = fetch(api + urllib.parse.urlencode({"query": "time()-container_last_seen" + selector}))["data"]["result"]
age = max(float(r["value"][1]) for r in fresh) if fresh else None
passed = all(r["samples"] >= 18 and r["max_gap_seconds"] <= 2.5 for r in rows) and age is not None and 0 <= age <= 5
result = {"checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "window_seconds": 20, "series": rows, "last_seen_age_seconds": age, "passed": passed}
path = root / "Otros" / "fase1" / "muestreo.json"
path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
if not passed:
    raise RuntimeError("Cobertura/frescura insuficiente para aceptar monitoreo")
