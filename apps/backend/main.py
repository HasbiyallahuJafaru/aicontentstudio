"""Backend entry point. Electron spawns this and talks to it over stdin/stdout, one JSON object per line.

Request:  {"id": 1, "method": "projects.create", "params": {...}}
Response: {"id": 1, "result": ...}  or  {"id": 1, "error": {"message": "...", "detail": "..."}}
Event:    {"event": "backend.ready", "data": {...}}   (no id; pushed any time)

stdout carries only protocol lines; logs go to stderr.
"""
from app.rpc import serve

if __name__ == "__main__":
    serve()
