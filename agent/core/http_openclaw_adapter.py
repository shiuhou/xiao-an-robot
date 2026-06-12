"""HTTP adapter boundary for future OpenClaw runtime calls."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from agent.core.openclaw_adapter import OpenClawDecision, OpenClawEvent


class HttpOpenClawAdapter:
    """Synchronous HTTP adapter for OpenClaw-compatible event endpoints."""

    def __init__(
        self,
        base_url: str,
        endpoint: str = "/events",
        timeout_sec: float = 5.0,
    ) -> None:
        normalized_base_url = base_url.rstrip("/")
        normalized_endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        self.base_url = normalized_base_url
        self.endpoint = normalized_endpoint
        self.timeout_sec = timeout_sec
        self.url = f"{self.base_url}{self.endpoint}"

    def handle_event(self, event: OpenClawEvent) -> OpenClawDecision:
        try:
            body = json.dumps(event.to_dict(), ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(
                self.url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                response_body = response.read().decode("utf-8")
            parsed = json.loads(response_body)
            return OpenClawDecision.from_dict(parsed)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            Exception,
        ) as exc:
            return OpenClawDecision(
                handled=False,
                raw={
                    "backend": "http",
                    "error": str(exc),
                    "url": self.url,
                },
            )
