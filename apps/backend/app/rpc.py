import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError

from app import config, database, projects, settings
from app.errors import UserError

log = logging.getLogger("rpc")
_write_lock = threading.Lock()


def _secrets_load(keys: dict) -> dict:
    # Sent by Electron main only (the renderer can't reach "secrets.*"); kept in memory, never logged or stored here.
    config.SECRETS.clear()
    config.SECRETS.update({k: v for k, v in keys.items() if isinstance(v, str) and v})
    config.load_dotenv()  # dev .env only fills keys the app doesn't have
    return {"loaded": sorted(config.SECRETS)}


METHODS = {
    "app.info": lambda: {"data_dir": str(config.DATA_DIR), "version": config.VERSION},
    "secrets.load": _secrets_load,
    "settings.get": settings.get,
    "settings.update": settings.update,
    "projects.create": projects.create,
    "projects.list": projects.list_,
    "projects.get": projects.get,
    "projects.delete": projects.delete,
}


def send(obj: dict) -> None:
    line = json.dumps(obj, ensure_ascii=False)
    with _write_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def emit(event: str, data: dict | None = None) -> None:
    send({"event": event, "data": data or {}})


def handle(msg: dict) -> dict:
    """Run one request and return the response object. Never raises."""
    rid = msg.get("id")
    fn = METHODS.get(msg.get("method"))
    if fn is None:
        return {"id": rid, "error": {"message": "Unknown backend method.", "detail": str(msg.get("method"))}}
    try:
        return {"id": rid, "result": fn(**(msg.get("params") or {}))}
    except UserError as e:
        return {"id": rid, "error": {"message": str(e), "detail": e.detail}}
    except ValidationError as e:
        return {"id": rid, "error": {"message": "Some values are not valid.", "detail": e.json()}}
    except Exception as e:
        log.exception("method %s failed", msg.get("method"))
        return {"id": rid, "error": {"message": "Something went wrong in the backend.", "detail": repr(e)}}


def serve() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format='{"ts":"%(asctime)s","level":"%(levelname)s","component":"%(name)s","message":"%(message)s"}')
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    database.migrate()
    # ponytail: fixed pool; long jobs (Phase 6+) will need their own queue with cancel + progress events.
    pool = ThreadPoolExecutor(max_workers=4)
    emit("backend.ready", {"data_dir": str(config.DATA_DIR)})
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log.error("bad request line")
            continue
        pool.submit(lambda m=msg: send(handle(m)))
    pool.shutdown(wait=True)
