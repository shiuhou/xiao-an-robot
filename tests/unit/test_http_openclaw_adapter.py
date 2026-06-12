"""Unit tests for HttpOpenClawAdapter."""

from __future__ import annotations

import json
import unittest
import urllib.error
from unittest.mock import patch

from agent.core.http_openclaw_adapter import HttpOpenClawAdapter
from agent.core.openclaw_adapter import OpenClawEvent


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class HttpOpenClawAdapterTest(unittest.TestCase):
    def test_url_is_normalized_from_base_url_and_endpoint(self) -> None:
        adapter = HttpOpenClawAdapter(
            base_url="http://127.0.0.1:8766/",
            endpoint="events",
        )

        self.assertEqual(adapter.url, "http://127.0.0.1:8766/events")

    @patch("agent.core.http_openclaw_adapter.urllib.request.urlopen")
    def test_handle_event_sends_post_json_request(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeResponse(b'{"handled": false}')
        adapter = HttpOpenClawAdapter(base_url="http://127.0.0.1:8766")
        event = OpenClawEvent(
            type="frontend.message",
            text="你好",
            source="frontend",
            session_id="session-1",
            context={"payload": {"text": "你好"}},
        )

        adapter.handle_event(event)

        request = mock_urlopen.call_args.args[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["accept"], "application/json")
        self.assertEqual(body, event.to_dict())
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 5.0)

    @patch("agent.core.http_openclaw_adapter.urllib.request.urlopen")
    def test_handle_event_parses_normal_response(self, mock_urlopen) -> None:
        response_body = {
            "handled": True,
            "reply_text": "你好",
            "tool_calls": [
                {"name": "robot.say", "arguments": {"text": "你好"}},
            ],
        }
        mock_urlopen.return_value = FakeResponse(json.dumps(response_body).encode("utf-8"))
        adapter = HttpOpenClawAdapter(base_url="http://127.0.0.1:8766")

        decision = adapter.handle_event(OpenClawEvent(type="frontend.message", text="你好"))

        self.assertTrue(decision.handled)
        self.assertEqual(decision.reply_text, "你好")
        self.assertEqual(decision.tool_calls[0].name, "robot.say")
        self.assertEqual(decision.tool_calls[0].arguments, {"text": "你好"})

    @patch("agent.core.http_openclaw_adapter.urllib.request.urlopen")
    def test_http_error_returns_unhandled_decision(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://127.0.0.1:8766/events",
            code=500,
            msg="server error",
            hdrs=None,
            fp=None,
        )
        adapter = HttpOpenClawAdapter(base_url="http://127.0.0.1:8766")

        decision = adapter.handle_event(OpenClawEvent(type="test.event"))

        self.assertFalse(decision.handled)
        self.assertEqual(decision.raw["backend"], "http")
        self.assertIn("error", decision.raw)
        self.assertEqual(decision.raw["url"], "http://127.0.0.1:8766/events")

    @patch("agent.core.http_openclaw_adapter.urllib.request.urlopen")
    def test_url_error_returns_unhandled_decision(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        adapter = HttpOpenClawAdapter(base_url="http://127.0.0.1:8766")

        decision = adapter.handle_event(OpenClawEvent(type="test.event"))

        self.assertFalse(decision.handled)
        self.assertEqual(decision.raw["backend"], "http")
        self.assertIn("connection refused", decision.raw["error"])
        self.assertEqual(decision.raw["url"], "http://127.0.0.1:8766/events")

    @patch("agent.core.http_openclaw_adapter.urllib.request.urlopen")
    def test_invalid_json_returns_unhandled_decision(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeResponse(b"not json")
        adapter = HttpOpenClawAdapter(base_url="http://127.0.0.1:8766")

        decision = adapter.handle_event(OpenClawEvent(type="test.event"))

        self.assertFalse(decision.handled)
        self.assertEqual(decision.raw["backend"], "http")


if __name__ == "__main__":
    unittest.main()
