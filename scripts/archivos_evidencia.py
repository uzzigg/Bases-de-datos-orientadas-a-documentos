"""Publica evidencia completa sin sobrescribir archivos anteriores."""
import json
import os
import tempfile
from pathlib import Path


def publicar_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.evidencia-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows rechaza renombrar sobre un destino existente. En POSIX se
        # usa un enlace para conservar esa garantía sin carrera de existencia.
        if os.name == 'nt':
            os.rename(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def publicar_json(path, data):
    publicar_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
