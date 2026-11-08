"""Metricool through their MCP server (https://ai.metricool.com/mcp): this backend acts as a minimal MCP
client over the streamable-HTTP transport (initialize handshake, tools/list, tools/call).

Connecting is one button: Metricool's authorization server (discovered 2026-11-08 from
ai.metricool.com/.well-known/oauth-authorization-server) allows dynamic client registration and public PKCE
clients, so the app registers itself once, opens Metricool's consent page in the browser, and the shared
loopback catcher in oauth.py receives the code. No API key, no developer app, works on every Metricool plan.
# ponytail: endpoints are hardcoded from that discovery doc, not fetched each time; read it again if they move.
# ponytail: SSE replies are parsed but the GET event stream (server-initiated messages) is never read."""
import json
import os
import ssl
import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx

from app.errors import UserError
from app.publish import oauth, store

URL = os.environ.get("ACS_METRICOOL_URL", "https://ai.metricool.com/mcp")  # env: tests/fakes
AUTH = os.environ.get("ACS_METRICOOL_AUTH_URL", "https://app.metricool.com/oauth")
RESOURCE = "https://ai.metricool.com/mcp"  # RFC 8707: the token is minted for the MCP server
SCOPE = "mcp:read mcp:write"
PROTOCOL = "2025-06-18"
SOON = timedelta(minutes=5)
RECONNECT = "Metricool signed this app out. Connect it again in Settings, Publishing."


def _http(method: str, url: str, timeout: float = 30, **kw) -> httpx.Response:
    try:
        return httpx.request(method, url, timeout=timeout, verify=ssl.create_default_context(), **kw)
    except httpx.HTTPError as e:
        raise UserError("Couldn't reach Metricool. Try again in a minute.", repr(e)) from e


def _client_id() -> str:
    """This install's OAuth client, registered with Metricool on first connect (RFC 7591) and kept."""
    if client := store.load("metricool_client"):
        return client["client_id"]
    r = _http("POST", f"{AUTH}/register", json={
        "client_name": "AI Content Studio", "redirect_uris": [oauth.REDIRECT], "scope": SCOPE,
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "token_endpoint_auth_method": "none"})
    if not r.is_success or "client_id" not in r.text:
        raise UserError("Metricool wouldn't register this app. Try again in a minute.",
                        f"HTTP {r.status_code}: {r.text[:300]}")
    store.save("metricool_client", {"client_id": r.json()["client_id"]})
    return r.json()["client_id"]


def connect_url() -> str:
    """Metricool's consent page to open in the browser."""
    cid = _client_id()
    state, challenge = oauth.begin("metricool")
    return f"{AUTH}/authorize?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": oauth.REDIRECT, "response_type": "code", "scope": SCOPE,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "resource": RESOURCE})


def _token(form: dict) -> dict:
    r = _http("POST", f"{AUTH}/token", data=form | {"client_id": _client_id(), "resource": RESOURCE})
    if r.status_code in (400, 401):
        if "invalid_client" in r.text:  # Metricool forgot our registration: register afresh next time
            store.delete("metricool_client")
        raise UserError("Metricool didn't accept the connection. Connect it again.", r.text[:300])
    if not r.is_success:
        raise UserError("Metricool had a problem. Try again in a minute.", f"HTTP {r.status_code}")
    return r.json()


def _keep(tokens: dict, refresh: str = "") -> str:
    store.save("metricool", {"access_token": tokens["access_token"],
                             "refresh_token": tokens.get("refresh_token") or refresh,
                             "expires_at": (datetime.now(timezone.utc) +
                                            timedelta(seconds=tokens.get("expires_in", 3600))).isoformat()})
    return tokens["access_token"]


def _exchange(pending: dict, code: str) -> str:
    _keep(_token({"grant_type": "authorization_code", "code": code, "redirect_uri": oauth.REDIRECT,
                  "code_verifier": pending["verifier"]}))
    return "Metricool"


oauth.EXCHANGES["metricool"] = _exchange


def _bearer() -> str:
    """The working access token, refreshed when close to expiry. No refresh possible: reconnect."""
    account = store.load("metricool")
    if account is None:
        raise UserError("Metricool isn't connected yet. Connect it in Settings, Publishing.")
    if datetime.fromisoformat(account["expires_at"]) > datetime.now(timezone.utc) + SOON:
        return account["access_token"]
    try:
        if not account["refresh_token"]:
            raise UserError(RECONNECT)
        return _keep(_token({"grant_type": "refresh_token", "refresh_token": account["refresh_token"]}),
                     account["refresh_token"])
    except UserError as e:
        store.delete("metricool")
        raise UserError(RECONNECT, e.detail) from e


def connection() -> dict:
    return {"connected": store.load("metricool") is not None}


def disconnect() -> None:
    store.delete("metricool")  # the client registration stays: reconnecting reuses it


def _post(payload: dict, extra: dict | None = None) -> tuple[dict, dict]:
    """One JSON-RPC exchange; returns (response headers, parsed reply). Servers may answer JSON or SSE."""
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "Authorization": f"Bearer {_bearer()}"} | (extra or {})
    r = _http("POST", URL, json=payload, headers=headers, timeout=60)
    if r.status_code == 401:  # revoked in Metricool, or expired early
        store.delete("metricool")
        raise UserError(RECONNECT)
    if r.status_code == 403:
        raise UserError("Metricool says this account can't do that. Check your Metricool plan.", r.text[:300])
    if not r.is_success:
        raise UserError("Metricool had a problem. Try again in a minute.", f"HTTP {r.status_code}: {r.text[:300]}")
    if r.status_code == 202 or not r.content:
        return dict(r.headers), {}
    if "text/event-stream" in r.headers.get("content-type", ""):
        for line in reversed(r.text.splitlines()):  # the reply to our request is the last event with data
            if line.startswith("data:"):
                return dict(r.headers), json.loads(line[5:].strip())
        raise UserError("Metricool sent an unreadable reply.", r.text[:300])
    return dict(r.headers), r.json()


def _check(reply: dict) -> dict:
    if not reply:
        return {}
    if "error" in reply:
        raise UserError(f"Metricool: {reply['error'].get('message', 'request failed')}", json.dumps(reply["error"]))
    return reply.get("result") or {}


def _session() -> dict:
    """Initialize the MCP session and return the headers later calls must carry (empty if the server is
    stateless and issued no session id)."""
    headers, result = _post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": PROTOCOL, "capabilities": {},
        "clientInfo": {"name": "AiContentStudio", "version": "0.1.0"}}})
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})  # notification: accepted, no reply
    version = result.get("protocolVersion", PROTOCOL) if result else PROTOCOL
    extra = {"MCP-Protocol-Version": version}
    if sid := headers.get("mcp-session-id"):
        extra["Mcp-Session-Id"] = sid
    return extra


def tools() -> list[dict]:
    reply = _post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, _session())[1]
    return _check(reply).get("tools", [])


def call_tool(name: str, arguments: dict | None = None) -> dict:
    """Run one of Metricool's tools. Returns {'text': ..., 'is_error': bool} with the tool's text content."""
    reply = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments or {}}}, _session())[1]
    result = _check(reply)
    text = "\n".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text")
    return {"text": text, "is_error": bool(result.get("isError"))}
