"""Unit tests for the screen-usage-summary cache endpoints."""

from __future__ import annotations

import unittest

from base_station.api.router import ApiRouter


class FakeRuntime:
    def __init__(self) -> None:
        self.ingested: list[dict] = []
        self.latest: dict = {"summary": None}

    def ingest_screen_usage_summary(self, payload: dict, session_id: str = "default") -> dict:
        self.ingested.append({"payload": payload, "session_id": session_id})
        self.latest = {"summary": payload, "event_id": 1,
                       "timestamp_ms": payload.get("generated_at_ms")}
        return {"event_id": 1}

    def latest_screen_usage_summary(self) -> dict:
        return self.latest


class ScreenUsageSummaryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()
        self.router = ApiRouter(self.runtime)

    def test_post_then_get_latest(self) -> None:
        payload = {
            "generated_at_ms": 1720000000000,
            "active_seconds": 5400,
            "away_seconds": 600,
            "by_app": [{"app": "Code.exe", "seconds": 3600}],
        }
        post = self.router.route("POST", "/api/screen-usage-summary", body_json=payload)
        self.assertEqual(post.status, 200)
        self.assertEqual(post.body["data"]["event_id"], 1)
        self.assertEqual(self.runtime.ingested[0]["payload"], payload)

        get = self.router.route("GET", "/api/screen-usage-summary")
        self.assertEqual(get.status, 200)
        self.assertEqual(get.body["data"]["summary"]["active_seconds"], 5400)

    def test_post_rejects_non_object_body(self) -> None:
        response = self.router.route("POST", "/api/screen-usage-summary", body_json=[1, 2])
        self.assertEqual(response.status, 400)
        self.assertEqual(response.body["error"]["code"], "invalid_body")

    def test_post_rejects_non_numeric_fields(self) -> None:
        response = self.router.route(
            "POST",
            "/api/screen-usage-summary",
            body_json={"active_seconds": "very long"},
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(response.body["error"]["code"], "invalid_active_seconds")


if __name__ == "__main__":
    unittest.main()
