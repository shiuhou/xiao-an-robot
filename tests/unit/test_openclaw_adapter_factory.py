"""Unit tests for OpenClaw adapter factory."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from agent.core.brain import XiaoAnBrain
from agent.core.http_openclaw_adapter import HttpOpenClawAdapter
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawDecision
from agent.core.openclaw_adapter_factory import build_openclaw_adapter_from_env


class FakeGateway:
    async def send_expression(self, expression: str, duration_ms: int = 3000, loop: bool = False) -> dict:
        return {"type": "agent.ack", "payload": {"ok": True}}

    async def send_motion(self, action: str, params: dict | None = None, timeout_ms: int = 5000) -> dict:
        return {"type": "agent.ack", "payload": {"ok": True}}

    async def send_tts(self, text: str) -> dict:
        return {"type": "agent.ack", "payload": {"ok": True}}


class FakeMemory:
    def insert_emotion(
        self,
        source: str,
        emotion_tag: str,
        confidence: float,
        fatigue_score: float = 0.0,
        timestamp: int | None = None,
    ) -> int:
        return 1

    def get_recent_summary(self, seconds: int = 300, now_ms: int | None = None) -> dict:
        return {
            "count": 0,
            "avg_fatigue_score": 0.0,
            "max_confidence": 0.0,
            "top_emotion": None,
            "emotions_count": {},
        }

    def close(self) -> None:
        pass


class OpenClawAdapterFactoryTest(unittest.TestCase):
    def test_default_backend_returns_fake_adapter(self) -> None:
        adapter = build_openclaw_adapter_from_env({})

        self.assertIsInstance(adapter, FakeOpenClawAdapter)

    def test_fake_backend_returns_fake_adapter(self) -> None:
        adapter = build_openclaw_adapter_from_env({"XIAO_AN_OPENCLAW_BACKEND": "fake"})

        self.assertIsInstance(adapter, FakeOpenClawAdapter)

    def test_fake_backend_is_case_and_space_insensitive(self) -> None:
        adapter = build_openclaw_adapter_from_env({"XIAO_AN_OPENCLAW_BACKEND": " FAKE "})

        self.assertIsInstance(adapter, FakeOpenClawAdapter)

    def test_http_backend_returns_http_adapter(self) -> None:
        adapter = build_openclaw_adapter_from_env({"XIAO_AN_OPENCLAW_BACKEND": "http"})

        self.assertIsInstance(adapter, HttpOpenClawAdapter)
        self.assertEqual(adapter.url, "http://127.0.0.1:8766/events")
        self.assertEqual(adapter.timeout_sec, 5.0)

    def test_http_backend_reads_url_endpoint_and_timeout(self) -> None:
        adapter = build_openclaw_adapter_from_env({
            "XIAO_AN_OPENCLAW_BACKEND": "http",
            "XIAO_AN_OPENCLAW_URL": "http://openclaw.local:9000/",
            "XIAO_AN_OPENCLAW_ENDPOINT": "api/events",
            "XIAO_AN_OPENCLAW_TIMEOUT_SEC": "2.5",
        })

        self.assertIsInstance(adapter, HttpOpenClawAdapter)
        self.assertEqual(adapter.url, "http://openclaw.local:9000/api/events")
        self.assertEqual(adapter.timeout_sec, 2.5)

    def test_http_backend_invalid_timeout_uses_default(self) -> None:
        adapter = build_openclaw_adapter_from_env({
            "XIAO_AN_OPENCLAW_BACKEND": "http",
            "XIAO_AN_OPENCLAW_TIMEOUT_SEC": "abc",
        })

        self.assertIsInstance(adapter, HttpOpenClawAdapter)
        self.assertEqual(adapter.timeout_sec, 5.0)

    def test_unknown_backend_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "strange"):
            build_openclaw_adapter_from_env({"XIAO_AN_OPENCLAW_BACKEND": "strange"})

    def test_brain_uses_factory_when_adapter_is_not_provided(self) -> None:
        adapter = FakeOpenClawAdapter(decision=OpenClawDecision(handled=False))
        with patch("agent.core.brain.build_openclaw_adapter_from_env", return_value=adapter) as factory:
            brain = XiaoAnBrain(gateway=FakeGateway(), memory=FakeMemory())

        factory.assert_called_once_with()
        self.assertIs(brain.openclaw_adapter, adapter)

    def test_brain_uses_explicit_adapter_without_calling_factory(self) -> None:
        adapter = FakeOpenClawAdapter(decision=OpenClawDecision(handled=False))
        with patch("agent.core.brain.build_openclaw_adapter_from_env") as factory:
            brain = XiaoAnBrain(gateway=FakeGateway(), memory=FakeMemory(), openclaw_adapter=adapter)

        factory.assert_not_called()
        self.assertIs(brain.openclaw_adapter, adapter)


if __name__ == "__main__":
    unittest.main()
