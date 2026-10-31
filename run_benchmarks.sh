#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if command -v wslpath >/dev/null 2>&1 && [ -x "$PROJECT_DIR/Otros/venv/Scripts/python.exe" ]; then
  SCRIPT_WIN="$(wslpath -w "$PROJECT_DIR/scripts/ejecutar_matriz.py")"
  exec "$PROJECT_DIR/Otros/venv/Scripts/python.exe" "$SCRIPT_WIN" "$@"
fi
echo 'Se requiere WSL y el entorno Otros/venv para la automatización Windows.' >&2
exit 1
