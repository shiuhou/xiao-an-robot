import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import run_e2e_emotion_smoke as smoke


class RunE2EEmotionSmokeTest(unittest.TestCase):
    def test_normal_observe_does_not_trigger(self):
        events, summary = smoke.run_smoke(scenarios=["normal_observe"], backend="fake")

        self.assertEqual(summary["pass_count"], 1)
        self.assertFalse(events[0]["triggered"])
        self.assertFalse(events[0]["action_requested"])
        self.assertEqual(events[0]["result"], "pass")

    def test_fatigue_care_triggers_fake_action(self):
        events, summary = smoke.run_smoke(scenarios=["fatigue_care"], backend="fake")

        self.assertEqual(summary["pass_count"], 1)
        self.assertTrue(events[0]["triggered"])
        self.assertTrue(events[0]["action_requested"])
        self.assertTrue(events[0]["fake_backend_used"])
        self.assertEqual(events[0]["result"], "pass")

    def test_low_quality_guard_does_not_trigger(self):
        events, summary = smoke.run_smoke(scenarios=["low_quality_guard"], backend="fake")

        self.assertEqual(summary["pass_count"], 1)
        self.assertFalse(events[0]["triggered"])
        self.assertFalse(events[0]["action_requested"])
        self.assertIn("low_quality", events[0]["reason"])

    def test_cooldown_guard_second_sample_is_suppressed(self):
        events, summary = smoke.run_smoke(scenarios=["cooldown_guard"], backend="fake")

        self.assertEqual(summary["pass_count"], 1)
        self.assertTrue(events[0]["triggered"])
        self.assertFalse(events[1]["triggered"])
        self.assertTrue(events[1]["cooldown_active"])
        self.assertTrue(summary["cooldown_guard_passed"])

    def test_vlm_override_guard_does_not_trigger_and_reports_no_override(self):
        events, summary = smoke.run_smoke(scenarios=["vlm_override_guard"], backend="fake")

        self.assertEqual(summary["pass_count"], 1)
        self.assertFalse(events[0]["triggered"])
        self.assertFalse(events[0]["vlm_override"])
        self.assertEqual(summary["vlm_override_count"], 0)

    def test_output_files_have_expected_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report_assets"

            smoke.run_smoke(out_root=out, backend="fake", scenarios=["normal_observe"])

            event_path = out / "logs/e2e_smoke_events.jsonl"
            summary_path = out / "logs/e2e_smoke_summary.json"
            event = json.loads(event_path.read_text(encoding="utf-8").splitlines()[0])
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

            expected_event_fields = {
                "timestamp",
                "scenario",
                "input_sample",
                "brain_event_type",
                "decision_or_intervention",
                "action_requested",
                "fake_backend_used",
                "triggered",
                "cooldown_active",
                "vlm_override",
                "result",
                "reason",
            }
            expected_summary_fields = {
                "total_scenarios",
                "pass_count",
                "fail_count",
                "fake_backend_used",
                "real_openclaw_used",
                "vlm_override_count",
                "cooldown_guard_passed",
                "fatigue_scale_contract",
                "notes",
            }
            self.assertTrue(expected_event_fields.issubset(event.keys()))
            self.assertTrue(expected_summary_fields.issubset(summary.keys()))

    def test_cli_runs_and_generates_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report_assets"
            repo_root = Path(__file__).resolve().parents[2]

            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/run_e2e_emotion_smoke.py",
                    "--out",
                    str(out),
                    "--backend",
                    "fake",
                    "--all",
                ],
                cwd=repo_root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((out / "logs/e2e_smoke_events.jsonl").exists())
            self.assertTrue((out / "logs/e2e_smoke_summary.json").exists())
            self.assertTrue((out / "tables/table_e2e_smoke_checklist.md").exists())
            self.assertTrue((out / "tables/table_report_evidence_index.md").exists())
            self.assertTrue((out / "evidence_chain.md").exists())
            self.assertTrue((out / "demo_runbook.md").exists())
            self.assertTrue((out / "figures/fig_e2e_event_flow.png").exists())


if __name__ == "__main__":
    unittest.main()
