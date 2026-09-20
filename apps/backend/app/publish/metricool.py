"""Metricool through their MCP server (https://ai.metricool.com/mcp): this backend acts as a minimal MCP
client over the streamable-HTTP transport — initialize handshake, tools/list, tools/call — authenticated with
the account's API key (Metricool, Account Settings > API) via the X-Mc-Auth header, the same header n8n uses.
# ponytail: only the three calls we need; SSE replies are parsed but the GET event stream (server-initiated
# messages) is never read — nothing we call needs it."""
import json
import os
import ssl

import httpx

from app import config
from app.errors import UserError

URL = os.environ.get("ACS_METRICOOL_URL", "https://ai.metricool.com/mcp")  # env: tests/fakes
PROTOCOL = "2025-06-18"


def _key() -> str:
    key = config.SECRETS.get("METRICOOL_API_KEY")
    if not key:
        raise UserError("Add your Metricool API key in Settings to publish through Metricool.")
    return key


def _post(payload: dict, extra: dict | None = None) -> tuple[dict, dict]:
    """One JSON-RPC exchange; returns (response headers, parsed reply). Servers may answer JSON or SSE."""
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "X-Mc-Auth": _key()} | (extra or {})
    try:
        r = httpx.post(URL, json=payload, headers=headers, timeout=60, verify=ssl.create_default_context())
    except httpx.HTTPError as e:
        raise UserError("Couldn't reach Metricool. Try again in a minute.", repr(e)) from e
    if r.status_code in (401, 403):
        raise UserError("Metricool didn't accept the API key. Check it in Metricool, Account Settings > API.")
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


def status() -> dict:
    """Connection check: a successful tools/list is the whole handshake."""
    return {"connected": True, "server": "Metricool MCP",
            "tools": [t["name"] for t in tools()]}
