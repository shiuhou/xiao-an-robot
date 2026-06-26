"""Unit tests for WebSocket server session ownership."""

from __future__ import annotations

import json
import unittest

try:
    import websockets  # noqa: F401
except ImportError:  # pragma: no cover - depends on local dev environment
    websockets = None

if websockets is not None:
    from base_station.ws_server import server as ws_server
else:  # pragma: no cover - import is skipped with the dependency
    ws_server = None


def device_hello(device_id: str) -> str:
    return json.dumps({
        "type": "device.hello",
        "ts": 1714538000000,
        "seq": 1,
        "payload": {
            "device_id": device_id,
            "firmware": "unit-test",
            "battery": 90,
        },
    })


def video_frame_meta(device_id: str = "robot-1") -> str:
    return json.dumps({
        "type": "video.frame_meta",
        "ts": 1714538000001,
        "seq": 2,
        "payload": {
            "device_id": device_id,
            "frame_id": 1,
            "width": 320,
            "height": 240,
        },
    })


class FakeControlWebSocket:
    def __init__(self, messages: list[str]):
        self.messages = messages
        self.sent: list[str] = []

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def send(self, message: str) -> None:
        self.sent.append(message)


class BlockingControlWebSocket(FakeControlWebSocket):
    def __init__(self, messages: list[str]):
        super().__init__(messages)
        self.ready = False
        self.release = False

    async def __anext__(self):
        if self.messages:
            message = self.messages.pop(0)
            self.ready = True
            return message
        while not self.release:
            await ws_server.asyncio.sleep(0)
        raise StopAsyncIteration


class ClosingWebSocket:
    def __init__(self, replacement=None) -> None:
        self.replacement = replacement

    async def send(self, message: str) -> None:
        if self.replacement is not None:
            ws_server.sessions["robot-1"] = {
                "device_id": "robot-1",
                "ws": self.replacement,
                "session_id": "new-session",
                "last_hb": 0,
                "battery": 90,
            }
        raise ws_server.ConnectionClosed(None, None)


@unittest.skipIf(websockets is None, "websockets dependency is not installed")
class WebSocketServerSessionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        ws_server.reset_state_for_tests()

    async def asyncTearDown(self) -> None:
        ws_server.reset_state_for_tests()

    async def test_same_device_id_new_connection_overwrites_old_connection(self) -> None:
        old_ws = BlockingControlWebSocket([device_hello("robot-1")])
        new_ws = BlockingControlWebSocket([device_hello("robot-1")])

        old_task = ws_server.asyncio.create_task(ws_server.handle_control(old_ws))
        while not old_ws.ready:
            await ws_server.asyncio.sleep(0)
        new_task = ws_server.asyncio.create_task(ws_server.handle_control(new_ws))
        while not new_ws.ready:
            await ws_server.asyncio.sleep(0)

        self.assertIs(ws_server.sessions["robot-1"]["ws"], new_ws)

        old_ws.release = True
        new_ws.release = True
        await old_task
        await new_task

    async def test_old_connection_finally_does_not_delete_new_session(self) -> None:
        old_ws = FakeControlWebSocket([device_hello("robot-1")])
        new_ws = FakeControlWebSocket([])

        await ws_server.handle_control(old_ws)
        ws_server.sessions["robot-1"] = {
            "device_id": "robot-1",
            "ws": new_ws,
            "session_id": "new-session",
            "last_hb": 0,
            "battery": 88,
        }

        removed = ws_server.remove_session_if_current("robot-1", old_ws)

        self.assertFalse(removed)
        self.assertIs(ws_server.sessions["robot-1"]["ws"], new_ws)

    async def test_current_connection_finally_removes_session(self) -> None:
        current_ws = FakeControlWebSocket([device_hello("robot-1")])

        await ws_server.handle_control(current_ws)

        self.assertNotIn("robot-1", ws_server.sessions)

    async def test_control_accepts_video_frame_meta_extension_without_warning(self) -> None:
        websocket = FakeControlWebSocket([
            device_hello("robot-1"),
            video_frame_meta("robot-1"),
        ])

        with self.assertNoLogs("ws_server", level="WARNING"):
            await ws_server.handle_control(websocket)

    async def test_send_to_robot_connection_closed_does_not_delete_new_session(self) -> None:
        new_ws = FakeControlWebSocket([])
        old_ws = ClosingWebSocket(replacement=new_ws)
        ws_server.sessions["robot-1"] = {
            "device_id": "robot-1",
            "ws": old_ws,
            "session_id": "old-session",
            "last_hb": 0,
            "battery": 70,
        }

        ok, device_id, error = await ws_server.send_to_robot({"type": "motion.execute"}, device_id="robot-1")

        self.assertFalse(ok)
        self.assertEqual(device_id, "robot-1")
        self.assertIn("closed", error or "")
        self.assertIs(ws_server.sessions["robot-1"]["ws"], new_ws)

    async def test_send_to_robot_connection_closed_removes_current_session(self) -> None:
        current_ws = ClosingWebSocket()
        ws_server.sessions["robot-1"] = {
            "device_id": "robot-1",
            "ws": current_ws,
            "session_id": "current-session",
            "last_hb": 0,
            "battery": 70,
        }

        ok, device_id, error = await ws_server.send_to_robot({"type": "motion.execute"}, device_id="robot-1")

        self.assertFalse(ok)
        self.assertEqual(device_id, "robot-1")
        self.assertIn("closed", error or "")
        self.assertNotIn("robot-1", ws_server.sessions)


if __name__ == "__main__":
    unittest.main()
