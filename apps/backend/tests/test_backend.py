"""Run from apps/backend:  python -m unittest"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp()
os.environ["ACS_DATA_DIR"] = TMP

from app import config, database, rpc  # noqa: E402

BRIEF = {"topic": "discipline", "tone": "cinematic", "quantity": 6, "platforms": ["tiktok", "instagram_reels"]}


def call(method, **params):
    return rpc.handle({"id": 1, "method": method, "params": params})


class Backend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()
        database.migrate()  # idempotent

    def test_project_roundtrip(self):
        p = call("projects.create", brief=BRIEF)["result"]
        self.assertEqual((p["name"], p["status"], p["brief"]["format"]), ("Discipline", "draft", "automatic"))
        self.assertIn(p["id"], [x["id"] for x in call("projects.list")["result"]])
        self.assertEqual(call("projects.delete", id=p["id"])["result"], {"deleted": 1})
        self.assertEqual(call("projects.get", id=p["id"])["error"]["message"], "This project no longer exists.")

    def test_invalid_brief_rejected(self):
        for bad in ({**BRIEF, "quantity": 0}, {**BRIEF, "platforms": []}, {**BRIEF, "tone": "neon"}):
            self.assertEqual(call("projects.create", brief=bad)["error"]["message"], "Some values are not valid.")

    def test_settings(self):
        self.assertEqual(call("settings.get")["result"]["default_quantity"], 6)
        self.assertEqual(call("settings.update", default_quantity=3)["result"]["default_quantity"], 3)
        self.assertIn("error", call("settings.update", ai_temperature=5))
        self.assertEqual(call("settings.get")["result"]["default_quantity"], 3)

    def test_secrets_in_memory_only(self):
        self.assertEqual(call("secrets.load", keys={"PEXELS_API_KEY": "abc", "X": ""})["result"], {"loaded": ["PEXELS_API_KEY"]})
        self.assertEqual(config.SECRETS["PEXELS_API_KEY"], "abc")
        self.assertNotIn("abc", Path(config.DB_PATH).read_bytes().decode("latin-1"))

    def test_unknown_method(self):
        self.assertIn("error", call("nope"))

    def test_stdio_process(self):
        """The real process: ready event, then a response per request line."""
        main = Path(__file__).parents[1] / "main.py"
        out = subprocess.run([sys.executable, str(main)], input='{"id":7,"method":"app.info"}\n',
                             capture_output=True, text=True, encoding="utf-8", timeout=30,
                             env={**os.environ, "ACS_DATA_DIR": TMP}).stdout.splitlines()
        self.assertEqual(json.loads(out[0])["event"], "backend.ready")
        self.assertEqual(json.loads(out[1])["result"]["data_dir"], TMP)


if __name__ == "__main__":
    unittest.main()
