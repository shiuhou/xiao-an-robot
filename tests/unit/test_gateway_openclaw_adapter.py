"""Unit tests for the OpenClaw Gateway WebSocket adapter."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import tempfile
import unittest
from pathlib import Path

from agent.core.brain import XiaoAnBrain
from agent.core.gateway_openclaw_adapter import GatewayOpenClawAdapter
from agent.core.memory import XiaoAnMemoryStore
from agent.core.openclaw_adapter import OpenClawEvent


class FakeOpenClawGateway:
    def __init__(self, response: dict):
        self.response = response
        self.requests: list[dict] = []
        self.loop = None
        self.stop_future = None
        self.thread = None
        self.url_queue: queue.Queue[str] = queue.Queue()

    def start(self) -> str:
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self.url_queue.get(timeout=5)

    def stop(self) -> None:
        if self.loop is not None and self.stop_future is not None:
            self.loop.call_soon_threadsafe(self.stop_future.set_result, None)
        if self.thread is not None:
            self.thread.join(timeout=5)

    def _run(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        import websockets

        async def handler(websocket):
            raw = await websocket.recv()
            self.requests.append(json.loads(raw))
            await websocket.send(json.dumps(self.response, ensure_ascii=False))

        self.loop = asyncio.get_running_loop()
        self.stop_future = self.loop.create_future()
        server = await websockets.serve(handler, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        self.url_queue.put(f"ws://{host}:{port}")
        try:
            await self.stop_future
        finally:
            server.close()
            await server.wait_closed()


class GatewayOpenClawAdapterTest(unittest.TestCase):
    def test_gateway_reply_text_response(self) -> None:
        gateway = FakeOpenClawGateway({
            "handled": True,
            "reply_text": "你好，我在。",
        })
        url = gateway.start()
        try:
            adapter = GatewayOpenClawAdapter(
                gateway_url=url,
                agent="xiaoan-runtime",
                timeout_sec=1,
            )
            decision = adapter.handle_event(OpenClawEvent(
                type="frontend.message",
                text="你好小安",
                source="frontend",
            ))
        finally:
            gateway.stop()

        self.assertTrue(decision.handled)
        self.assertEqual(decision.reply_text, "你好，我在。")
        self.assertEqual(gateway.requests[0]["type"], "xiaoan.event")
        self.assertEqual(gateway.requests[0]["agent"], "xiaoan-runtime")
        tool_names = {item["name"] for item in gateway.requests[0]["tools"]}
        self.assertIn("xiaoan.robot.say", tool_names)

    def test_gateway_tool_calls_response(self) -> None:
        gateway = FakeOpenClawGateway({
            "payload": {
                "decision": {
                    "handled": True,
                    "tool_calls": [
                        {
                            "name": "xiaoan.robot.expression",
                            "arguments": {"expression": "happy"},
                        },
                    ],
                },
            },
        })
        url = gateway.start()
        try:
            adapter = GatewayOpenClawAdapter(gateway_url=url, timeout_sec=1)
            decision = adapter.handle_event(OpenClawEvent(type="asr.transcript", text="笑一个"))
        finally:
            gateway.stop()

        self.assertTrue(decision.handled)
        self.assertEqual(decision.tool_calls[0].name, "xiaoan.robot.expression")
        self.assertEqual(decision.tool_calls[0].arguments["expression"], "happy")

    def test_gateway_offline_returns_clear_error_decision(self) -> None:
        adapter = GatewayOpenClawAdapter(
            gateway_url="ws://127.0.0.1:1",
            agent="xiaoan-runtime",
            timeout_sec=0.2,
        )

        decision = adapter.handle_event(OpenClawEvent(type="frontend.message", text="你好"))

        self.assertFalse(decision.handled)
        self.assertEqual(decision.raw["backend"], "gateway")
        self.assertEqual(decision.raw["gateway_url"], "ws://127.0.0.1:1")
        self.assertEqual(decision.raw["agent"], "xiaoan-runtime")
        self.assertIn("error", decision.raw)


class RecordingRobotGateway:
    def __init__(self) -> None:
        self.tts_calls: list[str] = []
        self.expression_calls: list[tuple[str, int, bool]] = []

    async def send_expression(
        self,
        expression: str,
        duration_ms: int = 3000,
        loop: bool = False,
    ) -> dict:
        self.expression_calls.append((expression, duration_ms, loop))
        return {"ok": True, "type": "display.expression"}

    async def send_motion(
        self,
        action: str,
        params: dict | None = None,
        timeout_ms: int = 5000,
    ) -> dict:
        return {"ok": True, "type": "motion.execute", "action": action}

    async def send_tts(self, text: str) -> dict:
        self.tts_calls.append(text)
        return {"ok": True, "type": "audio.play_tts"}


class FakeEmotionMemory:
    def insert_emotion(self, *args, **kwargs) -> int:
        return 1

    def get_recent_summary(self, seconds: int = 300, now_ms=None) -> dict:
        return {"count": 0, "top_emotion": None}

    def close(self) -> None:
        return None


class GatewayBridgeBrainTest(unittest.IsolatedAsyncioTestCase):
    async def test_frontend_reply_text_from_gateway_becomes_robot_speech(self) -> None:
        fake_gateway = FakeOpenClawGateway({
            "handled": True,
            "reply_text": "你好，我是小安。",
        })
        url = fake_gateway.start()
        temp_dir = tempfile.TemporaryDirectory()
        context_memory = XiaoAnMemoryStore(str(Path(temp_dir.name) / "bridge.db"))
        robot_gateway = RecordingRobotGateway()
        brain = XiaoAnBrain(
            gateway=robot_gateway,
            memory=FakeEmotionMemory(),
            context_memory=context_memory,
            openclaw_adapter=GatewayOpenClawAdapter(gateway_url=url, timeout_sec=1),
        )
        try:
            result = await brain.handle_event({
                "type": "frontend.message",
                "payload": {"text": "你好小安", "session_id": "bridge-test"},
            })
        finally:
            brain.close()
            context_memory.close()
            temp_dir.cleanup()
            fake_gateway.stop()

        self.assertTrue(result["handled"])
        self.assertEqual(result["reply_text"], "你好，我是小安。")
        self.assertEqual(robot_gateway.tts_calls, ["你好，我是小安。"])

    async def test_gateway_tool_calls_execute_local_xiaoan_tool(self) -> None:
        fake_gateway = FakeOpenClawGateway({
            "handled": True,
            "tool_calls": [
                {
                    "name": "xiaoan.robot.expression",
                    "arguments": {"expression": "happy"},
                },
            ],
        })
        url = fake_gateway.start()
        temp_dir = tempfile.TemporaryDirectory()
        context_memory = XiaoAnMemoryStore(str(Path(temp_dir.name) / "bridge.db"))
        robot_gateway = RecordingRobotGateway()
        brain = XiaoAnBrain(
            gateway=robot_gateway,
            memory=FakeEmotionMemory(),
            context_memory=context_memory,
            openclaw_adapter=GatewayOpenClawAdapter(gateway_url=url, timeout_sec=1),
        )
        try:
            result = await brain.handle_event({
                "type": "frontend.message",
                "payload": {"text": "开心一点", "session_id": "bridge-test"},
            })
        finally:
            brain.close()
            context_memory.close()
            temp_dir.cleanup()
            fake_gateway.stop()

        self.assertTrue(result["handled"])
        self.assertEqual(result["executed_actions"][0]["name"], "xiaoan.robot.expression")
        self.assertEqual(robot_gateway.expression_calls[0][0], "happy")

    async def test_frontend_gateway_offline_returns_error_without_crashing(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        context_memory = XiaoAnMemoryStore(str(Path(temp_dir.name) / "bridge.db"))
        robot_gateway = RecordingRobotGateway()
        brain = XiaoAnBrain(
            gateway=robot_gateway,
            memory=FakeEmotionMemory(),
            context_memory=context_memory,
            openclaw_adapter=GatewayOpenClawAdapter(
                gateway_url="ws://127.0.0.1:1",
                timeout_sec=0.2,
            ),
        )
        try:
            result = await brain.handle_event({
                "type": "frontend.message",
                "payload": {"text": "你好小安", "session_id": "offline-test"},
            })
        finally:
            brain.close()
            context_memory.close()
            temp_dir.cleanup()

        self.assertFalse(result["handled"])
        self.assertIn("openclaw_error", result)
        self.assertEqual(result["openclaw_raw"]["backend"], "gateway")


if __name__ == "__main__":
    unittest.main()
