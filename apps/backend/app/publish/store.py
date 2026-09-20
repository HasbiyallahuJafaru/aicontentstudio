"""Credentials the Python side owns: Buffer OAuth tokens, media-hosting keys, pending OAuth states.
Encrypted with Windows DPAPI (per user — the same primitive Electron's safeStorage wraps), base64 in the
credentials table. Off-Windows (dev only) the JSON is stored as-is.
# ponytail: plaintext off-Windows; a packaged non-Windows build needs a real secret store first."""
import base64
import json

from app.database import connect

try:
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _crypt(data: bytes, protect: bool) -> bytes:
        buf = ctypes.create_string_buffer(data, len(data))
        pin = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        pout = _Blob()
        fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
        if not fn(ctypes.byref(pin), None, None, None, None, 0, ctypes.byref(pout)):
            raise OSError("DPAPI call failed")
        try:
            return ctypes.string_at(pout.pbData, pout.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(pout.pbData)
except (AttributeError, ValueError):  # not Windows
    _crypt = None


def save(name: str, data: dict) -> None:
    raw = json.dumps(data).encode()
    blob = base64.b64encode(_crypt(raw, True)).decode() if _crypt else raw.decode()
    with connect() as conn:
        conn.execute("INSERT INTO credentials (name, data) VALUES (?, ?) "
                     "ON CONFLICT (name) DO UPDATE SET data = excluded.data, "
                     "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')", (name, blob))


def load(name: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT data FROM credentials WHERE name = ?", (name,)).fetchone()
    if row is None:
        return None
    raw = _crypt(base64.b64decode(row["data"]), False) if _crypt else row["data"].encode()
    return json.loads(raw)


def delete(name: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM credentials WHERE name = ?", (name,))
