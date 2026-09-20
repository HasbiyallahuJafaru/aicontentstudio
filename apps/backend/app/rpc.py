import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError

from app import assets, clips, config, content, database, export, jobs, projects, queue, renders, settings, tts
from app.publish import buffer as buffer_publish, host as publish_host, metricool
from app.errors import UserError
from app.events import emit, send

log = logging.getLogger("rpc")


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
    "tts.voices": tts.voices,
    "projects.create": projects.create,
    "projects.list": projects.list_,
    "projects.get": projects.get,
    "projects.set_voice": projects.set_voice,
    "projects.delete": projects.delete,
    "pieces.list": content.pieces,
    "pieces.recent": content.recent,
    "pieces.regenerate": content.regenerate,
    "pieces.approve": content.approve,
    "assets.list": assets.list_assets,
    "renders.list": renders.list_,
    "clips.list": clips.list_,
    "clips.review": clips.review,
    "queue.list": queue.list_,
    "exports.list": export.list_,
    "app.stats": content.stats,
    "jobs.start": jobs.start,
    "jobs.cancel": jobs.cancel,
    "jobs.latest": jobs.latest,
    "publish.buffer_connection": buffer_publish.oauth.connection,
    "publish.buffer_connect_url": buffer_publish.oauth.connect_url,
    "publish.buffer_disconnect": buffer_publish.oauth.disconnect,
    "publish.buffer_channels": buffer_publish.channels,
    "publish.buffer_publish": buffer_publish.publish,
    "publish.buffer_calendar": buffer_publish.calendar,
    "publish.publications": buffer_publish.publications,
    "publish.remove": buffer_publish.remove,
    "publish.host_status": publish_host.status,
    "publish.host_save": publish_host.save,
    "publish.metricool_status": metricool.status,
    "publish.metricool_call": metricool.call_tool,
}


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
    jobs.recover()
    # Requests run on 4 threads; generation jobs run on their own threads (jobs.py) and report via events.
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
