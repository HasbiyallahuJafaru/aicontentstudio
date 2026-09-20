"""Connecting the user's Buffer account: OAuth 2 Authorization Code + PKCE against auth.buffer.com, with a
public client (Buffer issues no secret for PKCE apps — the user registers their own OAuth app in Buffer and
pastes its client id into Settings). The browser returns to a loopback listener this module runs on
127.0.0.1:8787; Buffer's refresh tokens are single-use and rotated on every refresh, so the stored one is
replaced atomically or the connection breaks."""
import base64
import hashlib
import os
import secrets
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import ssl

from app import settings
from app.errors import UserError
from app.publish import store

AUTH = os.environ.get("ACS_BUFFER_AUTH_URL", "https://auth.buffer.com")  # env: tests/fakes
PORT = int(os.environ.get("ACS_BUFFER_PORT", "8787"))
REDIRECT = f"http://127.0.0.1:{PORT}/callback"
SCOPE = "account:read posts:write offline_access"
STATE_TTL = timedelta(minutes=10)
SOON = timedelta(minutes=10)  # refresh when the access token is this close to expiry (they last an hour)

_listener: "HTTPServer | None" = None


class _Catch(BaseHTTPRequestHandler):
    server_version = "ACS/0.1"

    def do_GET(self):  # noqa: N802 - stdlib handler name
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path != "/callback" or "code" not in query or "state" not in query:
                raise UserError("The connect reply was missing its code. Start again.")
            _exchange(query["state"][0], query["code"][0])
            message = "Buffer connected — you can close this tab and go back to the app."
        except UserError as e:
            message = str(e)
            self.send_response(400)
        else:
            self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<p style='font:16px systemic'>{message}</p>".encode())
        threading.Thread(target=_stop, daemon=True).start()

    def log_message(self, *args):  # quiet: the browser's request isn't worth a backend log line
        pass


def client_id() -> str:
    if cid := settings.get()["buffer_client_id"].strip():
        return cid
    raise UserError("Buffer isn't set up yet. Create an OAuth app at developers.buffer.com (a public, PKCE app), "
                    "add http://127.0.0.1:8787/callback as a redirect URL, and paste its client id in Settings.")


def _stop() -> None:
    global _listener
    if _listener:
        server, _listener = _listener, None
        server.shutdown()


def connect_url() -> str:
    """The authorize URL to open in the browser; also starts the loopback catcher for the reply."""
    global _listener
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(24)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    store.save(f"oauth:{state}", {"verifier": verifier,
                                  "made": datetime.now(timezone.utc).isoformat()})
    if _listener is None:
        try:
            _listener = HTTPServer(("127.0.0.1", PORT), _Catch)
        except OSError:
            raise UserError(f"Port {PORT} is busy, so Buffer's reply can't be received. "
                            "Close whatever uses it and connect again.")
        threading.Thread(target=_listener.serve_forever, daemon=True).start()
    query = urllib.parse.urlencode({"client_id": client_id(), "redirect_uri": REDIRECT, "response_type": "code",
                                    "scope": SCOPE, "state": state, "code_challenge": challenge,
                                    "code_challenge_method": "S256", "prompt": "consent"})
    return f"{AUTH}/auth?{query}"


def _fresh(state: dict) -> bool:
    made = datetime.fromisoformat(state["made"])
    return datetime.now(timezone.utc) - made < STATE_TTL


def _exchange(state: str, code: str) -> None:
    """Turn the browser's code into stored tokens. One-time: the pending state is consumed either way."""
    pending = store.load(f"oauth:{state}")
    store.delete(f"oauth:{state}")
    if not pending or not _fresh(pending):
        raise UserError("This connection attempt has expired. Start again.")
    tokens = _token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
                             "client_id": client_id(), "code_verifier": pending["verifier"]})
    account = {"access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token", ""),
               "expires_at": (datetime.now(timezone.utc) +
                              timedelta(seconds=tokens.get("expires_in", 3600))).isoformat()}
    store.save("buffer", account)


def _token_request(form: dict) -> dict:
    form = {k: v for k, v in form.items() if v}  # a public client sends no client_secret at all
    try:
        r = httpx.post(f"{AUTH}/token", data=form, timeout=30,
                       verify=ssl.create_default_context())
    except httpx.HTTPError as e:
        raise UserError("Couldn't reach Buffer. Try again in a minute.", repr(e)) from e
    if r.status_code in (400, 401):
        raise UserError("Buffer didn't accept the connection. Connect the account again.", r.text[:300])
    if not r.is_success:
        raise UserError("Couldn't reach Buffer. Try again in a minute.", f"HTTP {r.status_code}")
    return r.json()


def token() -> str:
    """The working access token, refreshed (and the single-use refresh token rotated) when close to expiry.
    A failed refresh removes the connection — reconnecting is the only fix."""
    account = store.load("buffer")
    if account is None:
        raise UserError("Buffer isn't connected yet. Connect it in Settings, Publishing.")
    if datetime.fromisoformat(account["expires_at"]) > datetime.now(timezone.utc) + SOON:
        return account["access_token"]
    try:
        tokens = _token_request({"grant_type": "refresh_token", "refresh_token": account["refresh_token"],
                                 "client_id": client_id()})
    except UserError as e:
        store.delete("buffer")
        raise UserError("Buffer disconnected this app. Connect it again to keep publishing.", e.detail) from e
    account = {"access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token", ""),
               "expires_at": (datetime.now(timezone.utc) +
                              timedelta(seconds=tokens.get("expires_in", 3600))).isoformat()}
    store.save("buffer", account)
    return account["access_token"]


def connection() -> dict | None:
    account = store.load("buffer")
    return {"connected": account is not None} if account else {"connected": False}


def disconnect() -> None:
    store.delete("buffer")
