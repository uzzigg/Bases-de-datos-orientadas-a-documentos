"""Consolida las seis verificaciones de infraestructura; no son benchmarks."""
import datetime as dt
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
checks = []
for engine in ("mongo", "postgres"):
    for profile in ("A", "B", "C"):
        path = root / "Otros" / "fase1" / f"verify_{engine}_{profile}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data["passed"] or data["persistence_after_restart"] is not True:
            raise RuntimeError(f"Verificacion incompleta: {engine}/{profile}")
        if any(t["health"] != "up" or t["scrape_interval"] != "1s" for t in data["targets"]):
            raise RuntimeError(f"Targets invalidos: {engine}/{profile}")
        checks.append({key: data[key] for key in ("engine", "profile", "engine_version", "image_id", "started_at_utc", "finished_at_utc", "persistence_after_restart", "passed", "targets")})
        checks[-1]["limits"] = {key: data["limits"][key] for key in ("cpus", "memory_mib", "swap_bytes")}
        checks[-1]["verified_metrics"] = sorted(data["metrics"])

summary = {
    "scope": "Phase 1 infrastructure integration; not workload benchmark results",
    "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "checks_passed": len(checks),
    "checks": checks,
    "sampling_verification": json.loads((root / "Otros" / "fase1" / "muestreo.json").read_text(encoding="utf-8")),
    "initial_sampling_observation": json.loads((root / "Otros" / "fase1" / "muestreo_inicial.json").read_text(encoding="utf-8")) if (root / "Otros" / "fase1" / "muestreo_inicial.json").exists() else None,
    "adaptations": ["Windows PostgreSQL port 55432", "Read-only host root mount without rslave on Docker Desktop", "Container swap disabled by equal memory and memory+swap limits"],
    "pending": ["Dataset generation and loading", "Q1/Q2 correctness", "Spill detection with workload evidence", "Full pilot and 162 benchmark runs"],
}
if not summary["sampling_verification"]["passed"]:
    raise RuntimeError("Muestreo no aprobado")
output = root / "resultados" / "verificacion_fase1.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Resumen generado: {len(checks)} verificaciones satisfactorias")
