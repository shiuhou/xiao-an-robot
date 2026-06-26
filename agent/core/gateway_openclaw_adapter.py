"""WebSocket OpenClaw Gateway adapter for Xiao An runtime events."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from agent.core.openclaw_adapter import OpenClawDecision, OpenClawEvent
from agent.core.xiaoan_tool_manifest import tool_manifest


DEFAULT_OPENCLAW_GATEWAY_URL = "ws://127.0.0.1:18789"
DEFAULT_OPENCLAW_AGENT = "xiaoan-runtime"
DEFAULT_OPENCLAW_GATEWAY_TIMEOUT_SEC = 5.0


class GatewayOpenClawAdapter:
    """Synchronous adapter for OpenClaw Gateway WebSocket requests."""

    def __init__(
        self,
        gateway_url: str = DEFAULT_OPENCLAW_GATEWAY_URL,
        agent: str = DEFAULT_OPENCLAW_AGENT,
        timeout_sec: float = DEFAULT_OPENCLAW_GATEWAY_TIMEOUT_SEC,
    ) -> None:
        self.gateway_url = str(gateway_url)
        self.agent = str(agent or DEFAULT_OPENCLAW_AGENT)
        self.timeout_sec = float(timeout_sec)

    def handle_event(self, event: OpenClawEvent) -> OpenClawDecision:
        try:
            response = self._run_sync(self._send_event(event))
            return self._decision_from_response(response)
        except Exception as exc:
            return OpenClawDecision(
                handled=False,
                raw={
                    "backend": "gateway",
                    "error": str(exc),
                    "gateway_url": self.gateway_url,
                    "agent": self.agent,
                },
            )

    def build_request(self, event: OpenClawEvent) -> dict[str, Any]:
        return {
            "schema": "xiaoan.openclaw.bridge.v1",
            "type": "xiaoan.event",
            "agent": self.agent,
            "event": event.to_dict(),
            "tools": tool_manifest(),
        }

    async def _send_event(self, event: OpenClawEvent) -> dict[str, Any]:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("websockets package is required for gateway backend") from exc

        request = self.build_request(event)
        async with websockets.connect(
            self.gateway_url,
            open_timeout=self.timeout_sec,
        ) as websocket:
            await asyncio.wait_for(
                websocket.send(json.dumps(request, ensure_ascii=False)),
                timeout=self.timeout_sec,
            )
            raw_response = await asyncio.wait_for(
                websocket.recv(),
                timeout=self.timeout_sec,
            )

        if isinstance(raw_response, bytes):
            raw_response = raw_response.decode("utf-8")
        parsed = json.loads(raw_response)
        if not isinstance(parsed, dict):
            raise ValueError("OpenClaw Gateway response must be a JSON object")
        return parsed

    @classmethod
    def _decision_from_response(cls, response: dict[str, Any]) -> OpenClawDecision:
        payload = cls._decision_payload(response)
        decision = OpenClawDecision.from_dict(payload)
        if decision.raw is None:
            decision.raw = response
        else:
            decision.raw = {
                **decision.raw,
                "gateway_response": response,
            }
        return decision

    @staticmethod
    def _decision_payload(response: dict[str, Any]) -> dict[str, Any]:
        for key in ("decision", "result", "response"):
            value = response.get(key)
            if isinstance(value, dict):
                return value

        payload = response.get("payload")
        if isinstance(payload, dict):
            for key in ("decision", "result", "response"):
                value = payload.get(key)
                if isinstance(value, dict):
                    return value
            if any(key in payload for key in ("handled", "reply_text", "tool_calls")):
                return payload

        if any(key in response for key in ("handled", "reply_text", "tool_calls")):
            return response

        return {
            "handled": False,
            "raw": response,
        }

    @staticmethod
    def _run_sync(awaitable):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)

        result: list[Any] = []
        errors: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(awaitable))
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()
        if errors:
            raise errors[0]
        return result[0] if result else None
