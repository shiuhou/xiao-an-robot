"""Skeleton tests for the WebSocket /control channel.

The real integration test should start the base_station WebSocket server in a
controlled test process, connect a mock robot, and assert that hello, welcome,
heartbeat, and command messages are exchanged correctly.
"""

from __future__ import annotations

import unittest


class WebSocketControlChannelTest(unittest.TestCase):
    def test_integration_test_plan_is_documented(self) -> None:
        steps = [
            "start base_station.ws_server.server on a free port",
            "connect tests/mocks/mock_robot.py to /control",
            "send device.hello and expect system.welcome",
            "send device.heartbeat at the configured interval",
            "log robot-facing commands such as motion.execute",
        ]
        self.assertIn("send device.hello and expect system.welcome", steps)


if __name__ == "__main__":
    unittest.main()

