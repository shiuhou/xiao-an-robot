"""WebSocket OpenClaw Gateway adapter for Xiao An runtime events."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from agent.core.openclaw_adapter import OpenClawDecision, OpenClawEvent
from agent.core.xiaoan_tool_manifest import tool_manifest


DEFAULT_OPENCLAW_GATEWAY_URL = "ws://127.0.0.1:18789"
DEFAULT_OPENCLAW_AGENT = "xiaoan-runtime"
DEFAULT_OPENCLAW_GATEWAY_TIMEOUT_SEC = 90.0


class GatewayOpenClawAdapter:
    """Synchronous adapter for OpenClaw Gateway WebSocket requests."""

    def __init__(
        self,
        gateway_url: str = DEFAULT_OPENCLAW_GATEWAY_URL,
        agent: str = DEFAULT_OPENCLAW_AGENT,
        timeout_sec: float = DEFAULT_OPENCLAW_GATEWAY_TIMEOUT_SEC,
        gateway_token: str | None = None,
    ) -> None:
        self.gateway_url = str(gateway_url)
        self.agent = str(agent or DEFAULT_OPENCLAW_AGENT)
        self.timeout_sec = float(timeout_sec)
        self.gateway_token = gateway_token

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
            try:
                first_response = await self._recv_initial_frame(
                    websocket,
                    timeout=min(self.timeout_sec, 1.0),
                )
                if self._is_connect_challenge(first_response):
                    await self._connect_gateway(websocket, first_response)
                    response = await self._request(
                        websocket,
                        "agent",
                        self._agent_params(event, request),
                        expect_final=True,
                    )
                    return response
            except TimeoutError:
                first_response = None

            await self._send_json(websocket, request)
            return await self._recv_json(websocket) if first_response is None else first_response

    async def _recv_initial_frame(self, websocket, timeout: float) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError
            frame = await self._recv_json(websocket, timeout=remaining)
            if self._is_connect_challenge(frame):
                return frame
            if frame.get("type") == "event":
                continue
            return frame

    async def _send_json(self, websocket, payload: dict[str, Any]) -> None:
        await asyncio.wait_for(
            websocket.send(json.dumps(payload, ensure_ascii=False)),
            timeout=self.timeout_sec,
        )

    async def _recv_json(self, websocket, timeout: float | None = None) -> dict[str, Any]:
        raw_response = await asyncio.wait_for(
            websocket.recv(),
            timeout=self.timeout_sec if timeout is None else timeout,
        )
        if isinstance(raw_response, bytes):
            raw_response = raw_response.decode("utf-8")
        parsed = json.loads(raw_response)
        if not isinstance(parsed, dict):
            raise ValueError("OpenClaw Gateway response must be a JSON object")
        return parsed

    async def _connect_gateway(self, websocket, challenge: dict[str, Any]) -> dict[str, Any]:
        payload = challenge.get("payload")
        nonce = payload.get("nonce") if isinstance(payload, dict) else None
        if not isinstance(nonce, str) or not nonce.strip():
            raise ValueError("OpenClaw Gateway connect.challenge missing nonce")

        token = self.gateway_token or os.environ.get("XIAO_AN_OPENCLAW_GATEWAY_TOKEN") or self._config_gateway_token()
        auth = {"token": token} if token else None
        params = {
            "minProtocol": 4,
            "maxProtocol": 4,
            "client": {
                "id": "gateway-client",
                "displayName": "xiao-an-robot",
                "version": "xiao-an-robot",
                "platform": "linux",
                "mode": "backend",
            },
            "caps": [],
            "role": "operator",
            "scopes": ["operator.admin"],
        }
        if auth is not None:
            params["auth"] = auth
        return await self._request(websocket, "connect", params)

    async def _request(
        self,
        websocket,
        method: str,
        params: dict[str, Any],
        expect_final: bool = False,
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        await self._send_json(websocket, {
            "type": "req",
            "id": request_id,
            "method": method,
            "params": params,
        })
        while True:
            frame = await self._recv_json(websocket)
            if frame.get("type") != "res" or frame.get("id") != request_id:
                continue
            if not frame.get("ok", False):
                error = frame.get("error")
                raise RuntimeError(f"OpenClaw Gateway {method} request failed: {error}")
            payload = frame.get("payload")
            if expect_final and isinstance(payload, dict) and payload.get("status") == "accepted":
                continue
            return frame

    def _agent_params(self, event: OpenClawEvent, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "message": json.dumps(request, ensure_ascii=False),
            "agentId": self.agent,
            "sessionKey": self._session_key(event),
            "timeout": max(int(self.timeout_sec), 1),
            "idempotencyKey": str(uuid.uuid4()),
            "cleanupBundleMcpOnRunEnd": True,
        }

    def _session_key(self, event: OpenClawEvent) -> str:
        session_id = event.session_id if isinstance(event.session_id, str) else "default"
        suffix = re.sub(r"[^A-Za-z0-9_.:-]+", "-", session_id).strip("-") or "default"
        return f"agent:{self.agent}:xiao-an-robot-{suffix}"

    @staticmethod
    def _is_connect_challenge(response: dict[str, Any]) -> bool:
        return response.get("type") == "event" and response.get("event") == "connect.challenge"

    @staticmethod
    def _config_gateway_token() -> str | None:
        config_path = Path(os.environ.get("OPENCLAW_CONFIG_PATH", "~/.openclaw/openclaw.json")).expanduser()
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        token = data.get("gateway", {}).get("auth", {}).get("token")
        return token if isinstance(token, str) and token else None

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
        agent_text = GatewayOpenClawAdapter._agent_response_text(response)
        if agent_text:
            parsed_text = GatewayOpenClawAdapter._json_object_from_text(agent_text)
            if parsed_text is not None:
                return parsed_text
            return {
                "handled": True,
                "reply_text": agent_text,
            }

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
    def _agent_response_text(response: dict[str, Any]) -> str:
        payload = response.get("payload")
        if not isinstance(payload, dict):
            return ""

        result = payload.get("result")
        if not isinstance(result, dict):
            return ""

        payloads = result.get("payloads")
        if isinstance(payloads, list):
            texts = [
                item.get("text", "")
                for item in payloads
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
            return "\n".join(text for text in texts if text).strip()

        message = result.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                texts = [
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                ]
                return "\n".join(text for text in texts if text).strip()

        return ""

    @staticmethod
    def _json_object_from_text(text: str) -> dict[str, Any] | None:
        candidates = [text.strip()]
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fenced:
            candidates.insert(0, fenced.group(1).strip())

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

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
