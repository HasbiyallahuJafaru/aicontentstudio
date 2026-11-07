"""Clear all content: projects and their files go, keys and settings stay, never mid-job."""
import os
import tempfile
import unittest

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from app import config, database, projects, settings, storage  # noqa: E402
from app.database import connect  # noqa: E402
from app.errors import UserError  # noqa: E402


class Clear(unittest.TestCase):
    def setUp(self):
        database.migrate()

    def test_wipes_projects_and_media_but_keeps_settings(self):
        settings.update(motion_graphics=False)
        projects.create({"topic": "discipline", "tone": "hope", "quantity": 1, "platforms": ["tiktok"]})
        render = config.MEDIA_DIR / "renders" / "x" / "001-video.mp4"
        render.parent.mkdir(parents=True, exist_ok=True)
        render.write_bytes(b"\0" * 5000)
        before = storage.usage()
        self.assertGreaterEqual(before["bytes"], 5000)
        self.assertGreaterEqual(before["projects"], 1)

        self.assertGreaterEqual(storage.clear()["freed"], 5000)
        self.assertEqual(storage.usage(), {"bytes": 0, "projects": 0})
        self.assertFalse(render.exists())
        self.assertTrue(config.MEDIA_DIR.is_dir(), "the media folder is recreated empty")
        self.assertFalse(settings.get()["motion_graphics"], "settings survive")
        settings.update(motion_graphics=True)

    def test_refuses_while_a_job_runs(self):
        p = projects.create({"topic": "discipline", "tone": "hope", "quantity": 1, "platforms": ["tiktok"]})
        with connect() as conn:
            conn.execute("INSERT INTO generation_jobs (id, project_id, kind, status) VALUES ('busy', ?, 'render', 'running')",
                         (p["id"],))
        try:
            with self.assertRaisesRegex(UserError, "still running"):
                storage.clear()
        finally:
            with connect() as conn:
                conn.execute("DELETE FROM generation_jobs WHERE id = 'busy'")
