"""Writes protocol lines to stdout (responses and pushed events). Thread-safe."""
import json
import sys
import threading

_lock = threading.Lock()


def send(obj: dict) -> None:
    line = json.dumps(obj, ensure_ascii=False)
    with _lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def emit(event: str, data: dict | None = None) -> None:
    send({"event": event, "data": data or {}})
