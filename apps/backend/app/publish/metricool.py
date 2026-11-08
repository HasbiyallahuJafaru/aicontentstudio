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


# --- publishing a clip ------------------------------------------------------------------------------------------
# Metricool's network name -> which of the clip's written posts it gets (the same copy Buffer uses)
NETWORKS = {"tiktok": "tiktok", "instagram": "instagram", "youtube": "youtube", "linkedin": "linkedin",
            "facebook": "facebook", "twitter": "x"}
LABELS = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube", "linkedin": "LinkedIn",
          "facebook": "Facebook", "twitter": "X"}
POST_LEAD = timedelta(minutes=5)  # "post now" = a few minutes out; Metricool refuses dates in the past
NO_NETWORKS = ("Your Metricool brand has no social networks connected yet. Connect one in Metricool "
               "(Brands, then Connections) and try again.")


def _tool_json(name: str, arguments: dict | None = None):
    result = call_tool(name, arguments)
    if result["is_error"]:
        if "network connected" in result["text"]:
            raise UserError(NO_NETWORKS, result["text"][:500])
        raise UserError(f"Metricool: {result['text'][:300]}", result["text"][:500])
    try:
        return json.loads(result["text"])
    except ValueError:
        return result["text"]


def brands() -> list[dict]:
    """The account's brands: id, name, time zone, and which of our networks look connected. `networks` is None
    when the reply doesn't say; the UI then offers every network and Metricool names any unconnected one.
    # ponytail: the reply's shape was only seen in its no-networks error form, so field names are read
    # defensively; check them against a brand with networks connected."""
    data = _tool_json("getBrandSettings")
    if isinstance(data, dict):
        items = data.get("brands") or data.get("data") or [data]
    else:
        items = data if isinstance(data, list) else []
    found = []
    for b in items:
        if not isinstance(b, dict) or not (bid := b.get("blogId") or b.get("id")):
            continue
        listed = b.get("networks") or b.get("connectedNetworks") or []
        connected = [n for n in NETWORKS if b.get(n) or b.get(f"{n}Account") or n in listed]
        found.append({"id": str(bid), "name": b.get("label") or b.get("name") or f"Brand {bid}",
                      "timezone": b.get("timezone") or "UTC", "networks": connected or None})
    if not found:
        raise UserError("Metricool didn't list any brands for this account.", str(data)[:500])
    return found


def _info(clip: dict, network: str, video_url: str, local: datetime, tz: str) -> dict:
    extra = {"youtubeData": {"title": clip["title"][:100], "type": "short", "privacy": "public",
                             "madeForKids": False},
             "instagramData": {"type": "REEL", "showReelOnFeed": True}, "facebookData": {"type": "REEL"}}
    return {"autoPublish": True, "draft": False, "descendants": [], "firstCommentText": "",
            "hasNotReadNotes": False, "media": [video_url], "mediaAltText": [],
            "providers": [{"network": network}], "shortener": False, "smartLinkData": {"ids": []},
            "text": clip["posts"][NETWORKS[network]],
            "publicationDate": {"dateTime": local.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": tz},
            f"{network}Data": extra.get(f"{network}Data", {})}


def publish(project_id: str, clip_idx: int, blog_id: str, networks: list[str], due_at: str | None = None) -> list[dict]:
    """Schedules an approved clip on Metricool, one post per network so each gets its own written copy. The video
    goes up once to the media host, because Metricool fetches media from a public link. Returns one publication
    per network, including any Metricool refused (status "error" with its reason)."""
    import re
    import uuid
    from zoneinfo import ZoneInfo

    from app import config
    from app.publish import buffer, host

    if not networks or any(n not in NETWORKS for n in networks):
        raise UserError("Choose at least one network to post to.")
    now = datetime.now(timezone.utc)
    try:
        when = datetime.fromisoformat(due_at) if due_at else now + POST_LEAD
    except ValueError:
        when = None
    if when is None or when.tzinfo is None:
        raise UserError("That time couldn't be read. Pick it again.", due_at or "")
    if when < now:
        raise UserError("That time has already passed. Pick a time in the future.")
    if not host.configured():
        raise UserError("Metricool fetches the video from a public link, so it needs a media host. Add an "
                        "S3-compatible bucket (Cloudflare R2 works) under Settings, Publishing.")
    brand = next((b for b in brands() if b["id"] == str(blog_id)), None)
    if brand is None:
        raise UserError("That Metricool brand isn't available any more. Reload and choose again.")
    clip = buffer._clip(project_id, clip_idx)
    if taken := buffer._taken(project_id, clip_idx, [f"metricool:{n}" for n in networks]):
        raise UserError(f"This clip is already scheduled on {', '.join(taken)}.")
    local = when.astimezone(ZoneInfo(brand["timezone"]))
    video_url = host.upload(config.MEDIA_DIR / clip["video_path"], f"{uuid.uuid4().hex[:12]}.mp4")
    rows = []
    for n in networks:
        channel = {"id": f"metricool:{n}", "service": NETWORKS[n], "displayName": f"Metricool {LABELS[n]}"}
        pub_id = uuid.uuid4().hex[:12]
        args = {"blogId": brand["id"], "date": local.isoformat(),
                "info": json.dumps(_info(clip, n, video_url, local, brand["timezone"]))}
        try:
            result = call_tool("createScheduledPost", args)
        except UserError as e:  # connection trouble: the remaining networks would fail the same way
            buffer._save(pub_id, project_id, clip_idx, channel, when, error=str(e), provider="metricool")
            raise
        link = re.search(r"https://[^\s\"']*metricool\.com[^\s\"',)]*", result["text"])
        post = None if result["is_error"] else {
            "id": f"{brand['id']}:{n}", "status": "scheduled", "dueAt": when.isoformat(), "sentAt": None,
            "externalLink": link.group(0) if link else None, "error": None}
        rows.append(buffer._save(pub_id, project_id, clip_idx, channel, when, post=post,
                                 error=result["text"][:300] if result["is_error"] else None, provider="metricool"))
    return rows
