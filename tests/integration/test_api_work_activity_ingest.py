"""Integration test for the screen work-activity ingest endpoint (衔接层 phase 2).

Exercises the REAL cross-machine mechanism against a temp DB and a real HTTP
server (the same code that runs on the board): the PC client's bridge output is
POSTed to /api/work-activities, then read back, and confirmed to reach OpenClaw's
injected context (with `note`) at ask-time — while never triggering a reply.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from base_station.api.runtime import ApiRuntime
from base_station.api.server import create_server

# import the PC client's bridge (now a sibling top-level dir in this repo)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PC_ROOT = _REPO_ROOT / "pc_screen_tracker"
if str(_PC_ROOT) not in sys.path:
    sys.path.insert(0, str(_PC_ROOT))

from tracker.bridge import note_to_kwargs           # noqa: E402
from tracker.understander import ActivityNote        # noqa: E402


class WorkActivityIngestIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "ingest.db"
        self.runtime = ApiRuntime(
            db_path=str(db_path),
            robot_ws_url="ws://127.0.0.1:65534/agent",
        )
        self.server = create_server("127.0.0.1", 0, self.runtime)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.runtime.close()
        self.temp_dir.cleanup()

    def get_json(self, path: str, params: dict | None = None) -> tuple[int, dict]:
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def post_json(self, path: str, body: dict) -> tuple[int, dict]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_bridge_output_lands_and_reaches_context(self) -> None:
        note = ActivityNote(
            timestamp_ms=1_720_000_000_000,
            app_name="Code.exe",
            window_title="memory.py - Visual Studio Code",
            activity_type="coding",
            project_id="t_001",                 # must NOT be stored
            project_hint="小安衔接层联调",
            gist="在 VSCode 里实现 work_activities 写入口",
            confidence=0.87,
            duration_seconds=180,
        )
        body = note_to_kwargs(note)   # exact PC-client output feeds the real endpoint

        # 1) POST via the real endpoint
        status, posted = self.post_json("/api/work-activities", body)
        self.assertEqual(status, 200)
        self.assertTrue(posted["ok"])
        self.assertIsNotNone(posted["data"]["work_activity_id"])

        # 2) read it back through the real GET endpoint
        _, work = self.get_json("/api/work-activities", {"limit": 10})
        row = work["data"]["work_activities"][0]
        self.assertEqual(row["app_name"], "Code.exe")
        self.assertEqual(row["source"], "screen")
        self.assertEqual(row["project_hint"], "小安衔接层联调")
        self.assertEqual(row["note"], "在 VSCode 里实现 work_activities 写入口")

        # project_id NULL invariant: the read projection omits project_id by design,
        # so verify the stored row directly (t_001 must not land in the INTEGER col).
        stored = self.runtime.memory_store.query_recent_work_activities(limit=1)[0]
        self.assertIsNone(stored["project_id"])
        self.assertEqual(stored["note"], "在 VSCode 里实现 work_activities 写入口")

        # 3) ask-time: gist reaches OpenClaw's injected context
        _, preview = self.post_json(
            "/api/context/preview",
            {"text": "帮我看看我当前工作的进度"},
        )
        self.assertIn("work", preview["data"]["requested_scopes"])
        acts = preview["data"]["context"]["work"]["recent_activities"]
        self.assertEqual(acts[0]["note"], "在 VSCode 里实现 work_activities 写入口")

        # 4) 不主动介入: ingesting + previewing produced NO robot reply
        _, latest = self.get_json("/api/replies/latest")
        self.assertFalse(latest["data"]["available"])

    def test_missing_app_name_is_rejected(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/work-activities",
            data=json.dumps({"note": "no app"}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("expected HTTP 400")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)
            payload = json.loads(exc.read().decode("utf-8"))
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "missing_app_name")


if __name__ == "__main__":
    unittest.main()
