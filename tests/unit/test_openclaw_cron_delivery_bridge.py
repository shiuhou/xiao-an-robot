import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from tools import openclaw_cron_delivery_bridge as bridge


class OpenClawCronDeliveryBridgeTests(unittest.TestCase):
    def test_parse_standard_summary_payload(self):
        payload = bridge.reminder_payload_from_summary(
            json.dumps(
                {
                    "type": "reminder.due",
                    "display_text": "提醒：该检查 Dashboard 了。",
                    "spoken_text": "该检查 Dashboard 啦。",
                    "metadata": {"mode": "speaking"},
                },
                ensure_ascii=False,
            )
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["type"], "reminder.due")
        self.assertEqual(payload["display_text"], "提醒：该检查 Dashboard 了。")

    def test_missing_type_is_filled_for_reminder_display_text(self):
        payload = bridge.reminder_payload_from_summary(
            json.dumps(
                {
                    "display_text": "提醒：该检查 cron delivery bridge 了。",
                    "spoken_text": "该检查 cron delivery bridge 啦。",
                },
                ensure_ascii=False,
            )
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["type"], "reminder.due")

    def test_metadata_source_is_set_to_bridge(self):
        payload = bridge.reminder_payload_from_summary(
            json.dumps(
                {
                    "type": "reminder.due",
                    "display_text": "提醒：测试。",
                    "metadata": {"source": "openclaw-cron"},
                },
                ensure_ascii=False,
            )
        )

        self.assertEqual(payload["metadata"]["source"], bridge.BRIDGE_SOURCE)

    def test_non_reminder_summary_is_skipped(self):
        self.assertIsNone(
            bridge.reminder_payload_from_summary(
                json.dumps({"display_text": "普通状态更新"}, ensure_ascii=False)
            )
        )
        self.assertIsNone(bridge.reminder_payload_from_summary("提醒：纯文本不是 JSON"))

    def test_already_delivered_run_is_not_reposted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sqlite_path = tmp_path / "openclaw.sqlite"
            state_file = tmp_path / "state.json"
            run = self._insert_reminder_run(sqlite_path, run_id="run-already")
            state = {"delivered": {}}
            bridge.mark_delivered(
                state,
                run,
                {"display_text": "提醒：已投递。"},
                delivered_at="2026-07-06T00:00:00",
            )
            bridge.save_delivery_state(state_file, state)

            original = bridge.post_notify
            try:
                calls = []
                bridge.post_notify = lambda url, payload: calls.append(payload) or True

                delivered = bridge.deliver_runs_once(
                    sqlite_path=sqlite_path,
                    notify_url="http://127.0.0.1:8787/api/openclaw/notify",
                    state_file=state_file,
                    agent_id="xiaoan-runtime",
                    lookback_seconds=None,
                )
            finally:
                bridge.post_notify = original

            self.assertEqual(delivered, 0)
            self.assertEqual(calls, [])

    def test_deliver_posts_standard_payload_and_records_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sqlite_path = tmp_path / "openclaw.sqlite"
            state_file = tmp_path / "state.json"
            self._insert_reminder_run(sqlite_path, run_id="run-one")

            original = bridge.post_notify
            calls = []
            try:
                bridge.post_notify = lambda url, payload: calls.append((url, payload)) or True

                delivered = bridge.deliver_runs_once(
                    sqlite_path=sqlite_path,
                    notify_url="http://127.0.0.1:8787/api/openclaw/notify",
                    state_file=state_file,
                    agent_id="xiaoan-runtime",
                    lookback_seconds=None,
                )
            finally:
                bridge.post_notify = original

            self.assertEqual(delivered, 1)
            self.assertEqual(len(calls), 1)
            url, payload = calls[0]
            self.assertEqual(url, "http://127.0.0.1:8787/api/openclaw/notify")
            self.assertEqual(payload["type"], "reminder.due")
            self.assertEqual(payload["metadata"]["source"], bridge.BRIDGE_SOURCE)
            self.assertEqual(payload["metadata"]["openclaw_cron"]["job_id"], "job-one")

            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertIn("run-one", state["delivered"])
            self.assertEqual(
                state["delivered"]["run-one"]["display_text"], "提醒：该检查 bridge 了。"
            )

    def test_missing_sqlite_and_schema_mismatch_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            missing = tmp_path / "missing.sqlite"
            self.assertEqual(
                bridge.fetch_completed_cron_runs(missing, "xiaoan-runtime"), []
            )

            bad_schema = tmp_path / "bad.sqlite"
            conn = sqlite3.connect(bad_schema)
            conn.execute("CREATE TABLE something_else (id TEXT)")
            conn.commit()
            conn.close()

            self.assertEqual(
                bridge.fetch_completed_cron_runs(bad_schema, "xiaoan-runtime"), []
            )

    def _insert_reminder_run(self, sqlite_path: Path, run_id: str) -> bridge.CronRun:
        conn = sqlite3.connect(sqlite_path)
        conn.execute(
            """
            CREATE TABLE cron_run_logs (
              job_id TEXT NOT NULL,
              seq INTEGER NOT NULL,
              ts INTEGER NOT NULL,
              status TEXT,
              summary TEXT,
              run_id TEXT,
              run_at_ms INTEGER,
              session_key TEXT,
              entry_json TEXT
            )
            """
        )
        now_ms = int(time.time() * 1000)
        summary = json.dumps(
            {
                "type": "reminder.due",
                "display_text": "提醒：该检查 bridge 了。",
                "spoken_text": "该检查 bridge 啦。",
            },
            ensure_ascii=False,
        )
        conn.execute(
            """
            INSERT INTO cron_run_logs (
              job_id, seq, ts, status, summary, run_id, run_at_ms, session_key, entry_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "job-one",
                1,
                now_ms,
                "ok",
                summary,
                run_id,
                now_ms,
                f"agent:xiaoan-runtime:cron:job-one:run:{run_id}",
                "{}",
            ),
        )
        conn.commit()
        conn.close()
        return bridge.CronRun(
            job_id="job-one",
            seq=1,
            ts=now_ms,
            status="ok",
            summary=summary,
            run_id=run_id,
            run_at_ms=now_ms,
            session_key=f"agent:xiaoan-runtime:cron:job-one:run:{run_id}",
            entry_json="{}",
        )


if __name__ == "__main__":
    unittest.main()
