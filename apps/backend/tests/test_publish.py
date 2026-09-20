"""Milestone 7 Phase C: publishing integrations, end to end against local fakes — a fake Buffer GraphQL API,
a fake auth.buffer.com token endpoint, a fake S3 host, and a fake Metricool MCP server. No network. The
Buffer OAuth test drives the real loopback listener on 127.0.0.1:8787."""
import hashlib
import hmac
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

CAPTURED = {"buffer": [], "host": [], "mcp": []}


class FakeRPC(BaseHTTPRequestHandler):
    """Shared plumbing: POST JSON-RPC-ish bodies routed to a per-server callback; PUT recorded as an upload."""
    protocol_version = "HTTP/1.1"  # keep-alive: httpx pools connections and dies on HTTP/1.0 closes

    def _reply(self, status, extra, reply):
        body = json.dumps(reply).encode() if reply is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if "json" in (self.headers.get("Content-Type") or ""):
            body = json.loads(raw or b"{}")
        else:  # OAuth token endpoints post form-encoded
            body = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
        reply, status, extra = self.respond(body)
        self._reply(status, extra, reply)

    def do_PUT(self):  # noqa: N802 - the media host upload
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        CAPTURED["host"].append({"path": self.path, "auth": self.headers.get("Authorization", ""),
                                 "amz_date": self.headers.get("x-amz-date", "")})
        self._reply(200, None, None)

    def respond(self, body):  # pragma: no cover - replaced per server
        return {"error": "no handler"}, 500, None

    def log_message(self, *args):
        pass


def _server(handler):
    class Routed(FakeRPC):
        pass
    Routed.respond = staticmethod(handler)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Routed)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def buffer_api(body):
    query = body.get("query", "")
    CAPTURED["buffer"].append(body)
    if "organizations" in query:
        return {"data": {"account": {"organizations": [{"id": "org1"}]}}}, 200, None
    if "channels(input" in query:
        return {"data": {"channels": [
            {"id": "ch-yt", "service": "youtube", "type": "channel", "name": "ch",
             "displayName": "My channel", "isDisconnected": False, "isLocked": False},
            {"id": "ch-ig", "service": "instagram", "type": "profile", "name": "ig",
             "displayName": "ig", "isDisconnected": False, "isLocked": False},
        ]}}, 200, None
    if "createPost" in query:
        post = {"id": "buf1", "status": "scheduled", "dueAt": body["variables"]["input"].get("dueAt"),
                "sentAt": None, "externalLink": "https://buffer.example/buf1", "error": None}
        return {"data": {"createPost": {"post": post}}}, 200, None
    if "deletePost" in query:
        return {"data": {"deletePost": {"id": "buf1"}}}, 200, None
    return {"data": {"post": {"id": "buf1", "status": "sent", "dueAt": None,
                              "sentAt": "2026-09-21T09:00:00Z", "externalLink": "https://buffer.example/buf1",
                              "error": None}}}, 200, None


def buffer_auth(body):
    return {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600}, 200, None


def host_api(body):
    return (None, 200, None)


def mcp_api(body):
    method = body.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": 0, "result": {"protocolVersion": "2025-06-18",
                "serverInfo": {"name": "fake-metricool", "version": "1"}}}, 200, {"Mcp-Session-Id": "sess-1"}
    if method == "notifications/initialized":
        return None, 202, None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": 1, "result": {"tools": [
            {"name": "schedule_post", "description": "Schedule a post",
             "inputSchema": {"type": "object"}}]}}, 200, {"Mcp-Session-Id": "sess-1"}
    if method == "tools/call":
        CAPTURED["mcp"].append(body)
        return {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": "posted ok"}]}}, 200, \
            {"Mcp-Session-Id": "sess-1"}
    return {"jsonrpc": "2.0", "id": body.get("id"), "error": {"message": "unknown"}}, 200, None


buffer_srv, BUFFER_URL = _server(buffer_api)
auth_srv, AUTH_URL = _server(buffer_auth)
host_srv, HOST_URL = _server(host_api)
mcp_srv, MCP_URL = _server(mcp_api)

os.environ["ACS_BUFFER_URL"] = BUFFER_URL
os.environ["ACS_BUFFER_AUTH_URL"] = AUTH_URL
os.environ["ACS_METRICOOL_URL"] = MCP_URL

from app import config, database, projects, settings  # noqa: E402
from app.database import connect  # noqa: E402
from app.errors import UserError  # noqa: E402
from app.publish import buffer as buffer_pub  # noqa: E402
from app.publish import host, metricool, oauth, store  # noqa: E402

buffer_pub.API = BUFFER_URL
oauth.AUTH = AUTH_URL
metricool.URL = MCP_URL


def setUpModule():
    database.migrate()


def make_clip_project(approved=True, video=b"videobytes"):
    src = config.MEDIA_DIR / "fixtures" / "pub-src.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"sourcebytes")
    p = projects.create({"kind": "clip", "source": str(src)})
    out = config.MEDIA_DIR / "clips" / p["id"] / "clip01.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(video)
    posts = {k: f"copy for {k}" for k in ["tiktok", "instagram", "youtube", "linkedin", "facebook", "x"]}
    with connect() as conn:
        conn.execute("INSERT INTO clips (id, project_id, idx, start_at, end_at, score, reason, hook, title, "
                     "description, hashtags, posts, status, video_path, cover_path) "
                     "VALUES ('clip1', ?, 1, 0, 10, 90, 'why', 'hook', 'My clip', 'desc', '[]', ?, ?, ?, ?)",
                     (p["id"], json.dumps(posts), "approved" if approved else "ready",
                      "clips/" + p["id"] + "/clip01.mp4", "clips/" + p["id"] + "/clip01.jpg"))
    return p


class BufferOAuth(unittest.TestCase):
    def test_full_loopback_connect_and_replay_is_refused(self):
        settings.update(buffer_client_id="test-client")
        url = oauth.connect_url()
        self.assertTrue(url.startswith(oauth.AUTH + "/auth?"))
        self.assertIn("code_challenge", url)
        state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
        import httpx
        reply = httpx.get(f"http://127.0.0.1:{oauth.PORT}/callback", params={"code": "abc", "state": state},
                          timeout=10)
        self.assertIn("connected", reply.text)
        self.assertTrue(oauth.connection()["connected"])
        self.assertEqual(oauth.token(), "at-1")
        self.assertIsNone(store.load(f"oauth:{state}"))  # the state was consumed: a replayed callback fails

    def test_disconnect_removes_the_connection(self):
        store.save("buffer", {"access_token": "x", "refresh_token": "r",
                              "expires_at": datetime.now(timezone.utc).isoformat()})
        oauth.disconnect()
        self.assertFalse(oauth.connection()["connected"])


class HostUpload(unittest.TestCase):
    def test_upload_puts_and_returns_public_url(self):
        settings.update(publish_host_endpoint=HOST_URL, publish_host_bucket="bkt",
                        publish_host_public_url="https://cdn.example/bkt", publish_host_region="auto")
        store.save("publish_host", {"access_key_id": "AKIA-TEST", "secret_access_key": "secret"})
        out = host.upload(config.MEDIA_DIR / "fixtures" / "pub-src.mp4", "abc123.mp4")
        self.assertEqual(out, "https://cdn.example/bkt/abc123.mp4")
        self.assertTrue(CAPTURED["host"])
        self.assertIn("/bkt/abc123.mp4", CAPTURED["host"][-1]["path"])
        self.assertIn("AWS4-HMAC-SHA256 Credential=AKIA-TEST/", CAPTURED["host"][-1]["auth"])

    def test_signature_matches_an_independent_sigv4(self):
        payload = b"hello"
        now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        amz_date, datestamp = "20260920T120000Z", "20260920"
        payload_hash = hashlib.sha256(payload).hexdigest()
        canonical = "\n".join(["PUT", "/bkt/k.mp4", "", "host:127.0.0.1",
                               f"x-amz-content-sha256:{payload_hash}", f"x-amz-date:{amz_date}",
                               "", "host;x-amz-content-sha256;x-amz-date", payload_hash])
        scope = f"{datestamp}/auto/s3/aws4_request"
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                             hashlib.sha256(canonical.encode()).hexdigest()])
        key = hmac.new(hmac.new(hmac.new(hmac.new(b"AWS4secret", b"20260920", hashlib.sha256).digest(),
                                         b"auto", hashlib.sha256).digest(),
                                b"s3", hashlib.sha256).digest(),
                       b"aws4_request", hashlib.sha256).digest()
        expected = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
        with mock.patch.object(host, "datetime") as dt:
            dt.now.return_value = now
            dt.timezone = timezone
            headers = host._sigv4_headers("PUT", "/bkt/k.mp4", "http://127.0.0.1", payload, "AK", "secret", "auto")
        self.assertIn(f"Signature={expected}", headers["Authorization"])


class BufferPublish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()
        settings.update(buffer_client_id="test-client", publish_host_endpoint=HOST_URL,
                        publish_host_bucket="bkt", publish_host_public_url="https://cdn.example/bkt")
        store.save("buffer", {"access_token": "at-1", "refresh_token": "rt",
                              "expires_at": "2099-01-01T00:00:00+00:00"})
        store.save("publish_host", {"access_key_id": "AKIA-TEST", "secret_access_key": "secret"})
        cls.project = make_clip_project()

    def test_channels_filters_unusable(self):
        found = buffer_pub.channels()
        self.assertEqual([c["id"] for c in found if c["usable"]], ["ch-yt"])
        self.assertEqual(found[1]["usable"], False)  # personal instagram profile: Buffer only reminds

    def test_post_input_maps_the_network_copy(self):
        clip = {"title": "t", "posts": {"youtube": "yt post", "x": "x post", "tiktok": "tt post"}}
        yt = buffer_pub.post_input(clip, {"id": "ch-yt", "service": "youtube"}, "https://v", None)
        self.assertEqual(yt["text"], "yt post")
        self.assertEqual(yt["mode"], "shareNow")
        self.assertEqual(yt["metadata"]["youtube"]["title"], "t")
        tw = buffer_pub.post_input(clip, {"id": "c", "service": "twitter"}, "https://v", None)
        self.assertEqual(tw["text"], "x post")
        scheduled = buffer_pub.post_input(clip, {"id": "c", "service": "tiktok"}, "https://v",
                                          datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(scheduled["mode"], "customScheduled")
        self.assertIn("thumbnailOffset", scheduled["assets"][0]["video"]["metadata"])

    def test_publish_now_end_to_end(self):
        rows = buffer_pub.publish(self.project["id"], 1, ["ch-yt"])
        self.assertEqual(rows[0]["status"], "scheduled")
        self.assertEqual(rows[0]["external_id"], "buf1")
        created = CAPTURED["buffer"][-1]["variables"]["input"]
        self.assertEqual(created["text"], "copy for youtube")
        self.assertEqual(created["channelId"], "ch-yt")
        self.assertEqual(created["assets"][0]["video"]["url"],
                         f"https://cdn.example/bkt/{rows[0]['id']}.mp4")
        # a second submit for the same channel is refused
        with self.assertRaisesRegex(UserError, "already scheduled"):
            buffer_pub.publish(self.project["id"], 1, ["ch-yt"])
        # status refresh: Buffer says the post went out (backdate the once-a-minute check gate)
        with connect() as conn:
            conn.execute("UPDATE publications SET checked_at = '2026-01-01T00:00:00Z'")
        rows = buffer_pub.publications(self.project["id"])
        self.assertEqual(rows[0]["status"], "sent")
        # unscheduling a sent post is refused: delete it on the network itself
        with self.assertRaisesRegex(UserError, "already gone out"):
            buffer_pub.remove(rows[0]["id"])
        # a failed attempt clears without calling Buffer
        with connect() as conn:
            conn.execute("INSERT INTO publications (id, project_id, clip_idx, provider, channel_id, service, "
                         "channel_name, status, error) VALUES ('err1', ?, 1, 'buffer', 'ch-yt', 'youtube', "
                         "'My channel', 'error', 'boom')", (self.project["id"],))
        self.assertTrue(buffer_pub.remove("err1")["removed"])
        self.assertEqual([r["id"] for r in buffer_pub.publications(self.project["id"])], [rows[0]["id"]])

    def test_publish_requires_approval(self):
        with connect() as conn:
            conn.execute("UPDATE clips SET status = 'ready' WHERE id = 'clip1'")
        with self.assertRaisesRegex(UserError, "Approve this clip"):
            buffer_pub.publish(self.project["id"], 1, ["ch-yt"])
        with connect() as conn:
            conn.execute("UPDATE clips SET status = 'approved' WHERE id = 'clip1'")

    def test_publish_without_host_is_human(self):
        with mock.patch.object(host, "configured", lambda: False):
            with self.assertRaisesRegex(UserError, "public"):
                buffer_pub.publish(self.project["id"], 1, ["ch-yt"])


class Calendar(unittest.TestCase):
    def test_slots_follow_days_times_and_zone(self):
        found = buffer_pub.slots([1, 3], ["09:00", "18:00"], datetime(2026, 9, 21).date(),
                                 datetime(2026, 9, 21, tzinfo=timezone.utc),
                                 datetime(2026, 9, 26, tzinfo=timezone.utc), "Europe/London")
        due = [d.isoformat() for d in found]
        self.assertIn("2026-09-21T08:00:00+00:00", due)  # Monday 09:00 London (BST) = 08:00 UTC
        self.assertIn("2026-09-23T17:00:00+00:00", due)  # Wednesday, second time
        self.assertFalse(any(d.startswith("2026-09-22") for d in due))  # Tuesday isn't chosen


class MetricoolMCP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config.SECRETS["METRICOOL_API_KEY"] = "mc-test-key"

    @classmethod
    def tearDownClass(cls):
        config.SECRETS.pop("METRICOOL_API_KEY", None)

    def test_needs_key_is_human(self):
        config.SECRETS.pop("METRICOOL_API_KEY")
        with self.assertRaisesRegex(UserError, "Metricool API key"):
            metricool.status()
        config.SECRETS["METRICOOL_API_KEY"] = "mc-test-key"

    def test_handshake_tools_and_call(self):
        status = metricool.status()
        self.assertTrue(status["connected"])
        self.assertEqual(status["tools"], ["schedule_post"])
        result = metricool.call_tool("schedule_post", {"text": "hello"})
        self.assertEqual(result, {"text": "posted ok", "is_error": False})
        self.assertEqual(CAPTURED["mcp"][-1]["params"]["arguments"]["text"], "hello")

    def test_bad_key_is_human(self):
        class Fake401:
            status_code = 401
            is_success = False
            headers = {}
            content = b"{}"
            text = ""

        with mock.patch.object(metricool.httpx, "post", lambda url, **kw: Fake401()):
            with self.assertRaisesRegex(UserError, "API key"):
                metricool.status()


if __name__ == "__main__":
    unittest.main()
