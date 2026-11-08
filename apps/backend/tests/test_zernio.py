"""Zernio posting against a local fake of its REST API and its presigned media storage. No network."""
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

SEEN = {"requests": [], "uploads": []}
STATE = {"post_status": "pending", "accounts_ok": True}
GOOD_KEY = "sk_" + "a" * 64


class FakeZernio(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _route(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        url = urllib.parse.urlparse(self.path)
        if url.path.startswith("/storage/"):  # the presigned PUT: no auth header, raw bytes
            SEEN["uploads"].append({"path": url.path, "bytes": raw, "auth": self.headers.get("Authorization")})
            return self._send(200)
        body = json.loads(raw) if raw else None
        SEEN["requests"].append({"method": method, "path": url.path, "query": urllib.parse.parse_qs(url.query),
                                 "body": body, "idem": self.headers.get("Idempotency-Key")})
        if self.headers.get("Authorization") != f"Bearer {GOOD_KEY}":
            return self._send(401, {"error": "Invalid API key"})
        path = url.path.removeprefix("/api")
        if path == "/v1/accounts":
            return self._send(200, {"accounts": [
                {"_id": "acc-yt", "platform": "youtube", "displayName": "My Channel", "username": "mychannel"},
                {"_id": "acc-tt", "platform": "tiktok", "displayName": "tt", "username": "tt_user"},
                {"_id": "acc-wa", "platform": "whatsapp", "displayName": "wa"},  # not a network we post to
                {"_id": "acc-ig", "platform": "instagram", "username": "ig", "needsReconnection": True},
            ]})
        if path == "/v1/profiles" and method == "GET":
            return self._send(200, {"profiles": []})
        if path == "/v1/profiles" and method == "POST":
            return self._send(201, {"profile": {"_id": "prof-1", "name": body["name"]}})
        if path.startswith("/v1/connect/"):
            return self._send(200, {"authUrl": f"https://zernio.example/oauth/{path.rsplit('/', 1)[1]}", "state": "s"})
        if path == "/v1/media/presign":
            port = self.server.server_address[1]
            return self._send(200, {"uploadUrl": f"http://127.0.0.1:{port}/storage/{body['filename']}?sig=1",
                                    "publicUrl": f"https://media.zernio.example/{body['filename']}", "expiresIn": 3600})
        if path == "/v1/accounts/acc-tt/tiktok/creator-info":
            return self._send(200, {"privacyLevels": [{"value": "SELF_ONLY", "label": "Only Me"},  # the live shape
                                                      {"value": "PUBLIC_TO_EVERYONE", "label": "Public To Everyone"}]})
        if path == "/v1/posts" and method == "POST":
            if body["platforms"][0]["accountId"] == "acc-bad":
                return self._send(400, {"error": "Video too long for this network"})
            n = len([r for r in SEEN["requests"] if r["path"].endswith("/v1/posts") and r["method"] == "POST"])
            return self._send(201, {"post": {"_id": f"post-{n}", "status": "scheduled"}})
        if path.startswith("/v1/posts/") and method == "GET":
            entry = {"platform": "youtube", "status": STATE["post_status"], "scheduledFor": "2030-01-01T09:00:00Z"}
            if STATE["post_status"] == "published":
                entry |= {"platformPostUrl": "https://youtube.com/shorts/abc", "publishedAt": "2030-01-01T09:00:05Z"}
            return self._send(200, {"post": {"_id": path.rsplit("/", 1)[1], "status": "scheduled", "platforms": [entry]}})
        if path.startswith("/v1/posts/") and method == "DELETE":
            return self._send(200, {"message": "deleted"})
        return self._send(404, {"error": "Not found"})

    def do_GET(self):  # noqa: N802
        self._route("GET")

    def do_POST(self):  # noqa: N802
        self._route("POST")

    def do_PUT(self):  # noqa: N802
        self._route("PUT")

    def do_DELETE(self):  # noqa: N802
        self._route("DELETE")

    def log_message(self, *args):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeZernio)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["ACS_ZERNIO_URL"] = f"http://127.0.0.1:{srv.server_address[1]}/api"

from app import config, database, projects  # noqa: E402
from app.database import connect  # noqa: E402
from app.errors import UserError  # noqa: E402
from app.publish import posts, store, zernio  # noqa: E402

zernio.API = os.environ["ACS_ZERNIO_URL"]


def setUpModule():
    database.migrate()


def clip_project():
    src = config.MEDIA_DIR / "fixtures" / "zernio-src.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"src")
    p = projects.create({"kind": "clip", "source": str(src)})
    out = config.MEDIA_DIR / "clips" / p["id"] / "clip01.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"the-clip-video")
    posts = {k: f"copy for {k}" for k in ["tiktok", "instagram", "youtube", "linkedin", "facebook", "x"]}
    with connect() as conn:
        conn.execute("INSERT INTO clips (id, project_id, idx, start_at, end_at, score, reason, hook, title, "
                     "description, hashtags, posts, status, video_path, cover_path) "
                     "VALUES (?, ?, 1, 0, 10, 90, 'why', 'hook', 'My clip title', 'desc', '[]', ?, 'approved', ?, ?)",
                     (f"zc-{p['id']}", p["id"], json.dumps(posts), f"clips/{p['id']}/clip01.mp4",
                      f"clips/{p['id']}/clip01.jpg"))
    return p


class Setup(unittest.TestCase):
    def setUp(self):
        store.delete("zernio")

    def test_not_set_up_is_human(self):
        self.assertFalse(zernio.connection()["connected"])
        with self.assertRaisesRegex(UserError, "isn't set up yet"):
            zernio.accounts()

    def test_key_is_checked_before_it_is_kept(self):
        with self.assertRaisesRegex(UserError, "starts with sk_"):
            zernio.save_key("hello")
        with self.assertRaisesRegex(UserError, "didn't accept that key"):
            zernio.save_key("sk_" + "b" * 64)
        self.assertFalse(zernio.connection()["connected"])
        self.assertTrue(zernio.save_key(f"  {GOOD_KEY} ")["connected"])
        zernio.disconnect()
        self.assertFalse(zernio.connection()["connected"])

    def test_accounts_keep_our_networks_and_flag_reconnects(self):
        zernio.save_key(GOOD_KEY)
        found = {a["id"]: a for a in zernio.accounts()}
        self.assertEqual(set(found), {"acc-yt", "acc-tt", "acc-ig"})
        self.assertEqual(found["acc-yt"]["label"], "YouTube")
        self.assertTrue(found["acc-ig"]["needs_reconnect"])

    def test_connect_url_makes_a_profile_once(self):
        zernio.save_key(GOOD_KEY)
        self.assertEqual(zernio.connect_url("tiktok"), "https://zernio.example/oauth/tiktok")
        zernio.connect_url("youtube")
        made = [r for r in SEEN["requests"] if r["path"].endswith("/v1/profiles") and r["method"] == "POST"]
        self.assertEqual(len(made), 1)
        self.assertEqual(SEEN["requests"][-1]["query"]["profileId"], ["prof-1"])
        with self.assertRaisesRegex(UserError, "can't be connected"):
            zernio.connect_url("myspace")


class Publish(unittest.TestCase):
    def setUp(self):
        store.delete("zernio")
        zernio.save_key(GOOD_KEY)
        self.project = clip_project()

    def test_uploads_once_and_posts_each_account_with_its_copy(self):
        before = len(SEEN["uploads"])
        when = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
        rows = zernio.publish(self.project["id"], 1, ["acc-yt", "acc-tt"], when.isoformat())
        self.assertEqual(len(SEEN["uploads"]) - before, 1)  # one upload, shared by both posts
        self.assertEqual(SEEN["uploads"][-1]["bytes"], b"the-clip-video")
        self.assertIsNone(SEEN["uploads"][-1]["auth"])  # storage gets no API key
        posts = [r for r in SEEN["requests"] if r["path"].endswith("/v1/posts") and r["method"] == "POST"][-2:]
        yt, tt = posts[0]["body"], posts[1]["body"]
        self.assertEqual(yt["content"], "copy for youtube")
        self.assertEqual(yt["platforms"][0]["platformSpecificData"]["title"], "My clip title")
        self.assertEqual(yt["mediaItems"][0]["url"], "https://media.zernio.example/clip01.mp4")
        self.assertEqual(yt["scheduledFor"], when.isoformat().replace("+00:00", "Z"))
        self.assertEqual(tt["content"], "copy for tiktok")
        self.assertEqual(tt["platforms"][0]["platformSpecificData"]["privacyLevel"], "PUBLIC_TO_EVERYONE")
        self.assertTrue(posts[0]["idem"])
        self.assertEqual([r["status"] for r in rows], ["scheduled", "scheduled"])
        self.assertEqual(rows[0]["channel_name"], "YouTube · My Channel")
        with self.assertRaisesRegex(UserError, "already scheduled"):
            zernio.publish(self.project["id"], 1, ["acc-yt"], when.isoformat())

    def test_status_refresh_and_unschedule(self):
        rows = zernio.publish(self.project["id"], 1, ["acc-yt"])  # post now: a couple of minutes out
        due = datetime.fromisoformat(rows[0]["due_at"])
        self.assertTrue(timedelta(minutes=1) < due - datetime.now(timezone.utc) < timedelta(minutes=3))
        with connect() as conn:  # the time has come and the once-a-minute gate is open
            conn.execute("UPDATE publications SET due_at = '2026-01-01T00:00:00+00:00', "
                         "checked_at = '2026-01-01T00:00:00Z' WHERE id = ?", (rows[0]["id"],))
        STATE["post_status"] = "published"
        try:
            fresh = posts.publications(self.project["id"])[0]
        finally:
            STATE["post_status"] = "pending"
        self.assertEqual(fresh["status"], "sent")
        self.assertEqual(fresh["external_link"], "https://youtube.com/shorts/abc")
        with self.assertRaisesRegex(UserError, "already gone out"):
            posts.remove(fresh["id"])
        # a still-scheduled post is deleted in Zernio and freed for rescheduling
        other = clip_project()
        row = zernio.publish(other["id"], 1, ["acc-tt"])[0]
        self.assertTrue(posts.remove(row["id"])["removed"])
        self.assertEqual(SEEN["requests"][-1]["method"], "DELETE")
        self.assertTrue(SEEN["requests"][-1]["path"].endswith(f"/v1/posts/{row['external_id']}"))

    def test_refusals_are_human(self):
        with self.assertRaisesRegex(UserError, "already passed"):
            zernio.publish(self.project["id"], 1, ["acc-yt"], "2020-01-01T09:00:00+00:00")
        with self.assertRaisesRegex(UserError, "sign in to ig again"):
            zernio.publish(self.project["id"], 1, ["acc-ig"])
        with self.assertRaisesRegex(UserError, "Choose at least one"):
            zernio.publish(self.project["id"], 1, [])

    def test_calendar_spreads_clips_through_zernio(self):
        plan = posts.calendar(self.project["id"], ["acc-yt"], [1, 2, 3, 4, 5, 6, 7], ["09:00"],
                              datetime.now(timezone.utc).date().isoformat(), "UTC")
        self.assertEqual([s["clip_idx"] for s in plan["scheduled"]], [1])
        rows = posts.publications(self.project["id"])
        self.assertEqual([(r["provider"], r["status"]) for r in rows], [("zernio", "scheduled")])


def piece_project(kinds=("image",)):
    """A quote-image (or narrated video) project with one rendered piece."""
    src = config.MEDIA_DIR / "fixtures" / "zernio-src.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"src")
    p = projects.create({"kind": "clip", "source": str(src)})  # the project kind doesn't matter to posting
    pid = f"pc-{p['id']}"
    meta = {"title": "A quiet line", "caption": "Keep going.", "description": "A short reminder.",
            "hashtags": ["#Stoic", "fyp", "#Discipline"], "keywords": ["stoic"], "alt_text": "white text on black"}
    with connect() as conn:
        conn.execute("INSERT INTO content_pieces (id, project_id, idx, status, angle, quote, content) "
                     "VALUES (?, ?, 1, 'ready', 'hope', 'Keep going.', ?)", (pid, p["id"], json.dumps({"metadata": meta})))
        for kind in kinds:
            name = "image_4x5.jpg" if kind == "image" else "video_9x16.mp4"
            out = config.MEDIA_DIR / "renders" / pid / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(f"{kind}-bytes".encode())
            conn.execute("INSERT INTO renders (id, project_id, piece_id, kind, local_path) VALUES (?, ?, ?, ?, ?)",
                         (f"r-{kind}-{pid}", p["id"], pid, kind, f"renders/{pid}/{name}"))
    return p, pid


class PublishPiece(unittest.TestCase):
    def setUp(self):
        store.delete("zernio")
        zernio.save_key(GOOD_KEY)

    def test_image_piece_posts_the_image_with_its_caption(self):
        p, pid = piece_project()
        rows = zernio.publish_piece(pid, ["acc-tt"])
        self.assertEqual(SEEN["uploads"][-1]["bytes"], b"image-bytes")
        presign = [r for r in SEEN["requests"] if r["path"].endswith("/v1/media/presign")][-1]["body"]
        self.assertEqual(presign["contentType"], "image/jpeg")
        body = [r for r in SEEN["requests"] if r["path"].endswith("/v1/posts") and r["method"] == "POST"][-1]["body"]
        self.assertEqual(body["mediaItems"][0]["type"], "image")
        self.assertEqual(body["content"], "Keep going. #Stoic #Discipline")  # reach-bait tags dropped
        self.assertEqual(body["platforms"][0]["platformSpecificData"]["mediaType"], "photo")
        self.assertEqual(rows[0]["piece_id"], pid)
        with self.assertRaisesRegex(UserError, "already scheduled"):
            zernio.publish_piece(pid, ["acc-tt"])
        self.assertEqual([r["piece_id"] for r in posts.publications(p["id"])], [pid])

    def test_youtube_needs_a_video(self):
        _, pid = piece_project()
        with self.assertRaisesRegex(UserError, "YouTube only takes videos"):
            zernio.publish_piece(pid, ["acc-yt"])

    def test_video_piece_posts_the_video_as_a_short(self):
        _, pid = piece_project(kinds=("image", "video"))
        zernio.publish_piece(pid, ["acc-yt"])
        self.assertEqual(SEEN["uploads"][-1]["bytes"], b"video-bytes")
        body = [r for r in SEEN["requests"] if r["path"].endswith("/v1/posts") and r["method"] == "POST"][-1]["body"]
        self.assertIn("#Shorts", body["content"])
        self.assertEqual(body["platforms"][0]["platformSpecificData"]["title"], "A quiet line")

    def test_unrendered_piece_is_refused(self):
        p, pid = piece_project(kinds=())
        with self.assertRaisesRegex(UserError, "Render this piece"):
            zernio.publish_piece(pid, ["acc-tt"])


class Slots(unittest.TestCase):
    def test_slots_follow_days_times_and_zone(self):
        start = datetime(2026, 3, 27, tzinfo=timezone.utc)  # a Friday; London moves to summer time on the 29th
        found = posts.slots([5, 1], ["09:00"], start.date(), start, start + timedelta(days=4), "Europe/London")
        self.assertEqual([f.isoformat() for f in found], ["2026-03-27T09:00:00+00:00", "2026-03-30T08:00:00+00:00"])


if __name__ == "__main__":
    unittest.main()
