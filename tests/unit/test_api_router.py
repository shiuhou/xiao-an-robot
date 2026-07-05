"""Unit tests for the local API router."""

from __future__ import annotations

import unittest

from base_station.api.router import ApiRouter


class FakeRuntime:
    def status(self) -> dict:
        return {
            "service": "xiao-an-local-api",
            "status": "ready",
            "db_path": "temp.db",
        }

    def latest_reply(self) -> dict:
        return {
            "available": True,
            "latest": {
                "display_text": "hello",
            },
        }

    def notify_from_openclaw(self, **kwargs) -> dict:
        return {
            "notification": kwargs,
            "execution_result": {
                "handled": True,
            },
        }


class ApiRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.router = ApiRouter(FakeRuntime())

    def test_health(self) -> None:
        response = self.router.route("GET", "/api/health")

        self.assertEqual(response.status, 200)
        self.assertTrue(response.body["ok"])
        self.assertEqual(response.body["data"]["status"], "ok")

    def test_status(self) -> None:
        response = self.router.route("GET", "/api/status")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["data"]["db_path"], "temp.db")

    def test_latest_reply(self) -> None:
        response = self.router.route("GET", "/api/replies/latest")

        self.assertEqual(response.status, 200)
        self.assertTrue(response.body["data"]["available"])
        self.assertEqual(
            response.body["data"]["latest"]["display_text"],
            "hello",
        )

    def test_status_exposes_openclaw_ownership_boundary(self) -> None:
        class OwnershipRuntime(FakeRuntime):
            def status(self) -> dict:
                data = super().status()
                data.update({
                    "storage_role": "local_event_store",
                    "openclaw_owned_features": [
                        "user_profile",
                        "long_term_memory",
                        "scheduled_reminders",
                        "tasks",
                        "morning_brief",
                        "daily_report",
                        "natural_language_replies",
                        "tool_selection",
                    ],
                    "deprecated_local_features": [
                        {
                            "name": "screen_monitoring",
                            "status": "deprecated",
                        },
                        {
                            "name": "reminders",
                            "status": "legacy_compatibility",
                        },
                    ],
                })
                return data

        router = ApiRouter(OwnershipRuntime())
        response = router.route("GET", "/api/status")
        data = response.body["data"]

        self.assertEqual(response.status, 200)
        self.assertEqual(data["storage_role"], "local_event_store")
        self.assertIn("long_term_memory", data["openclaw_owned_features"])
        self.assertIn("tasks", data["openclaw_owned_features"])
        deprecated = {
            item["name"]: item["status"]
            for item in data["deprecated_local_features"]
        }
        self.assertEqual(deprecated["screen_monitoring"], "deprecated")
        self.assertEqual(deprecated["reminders"], "legacy_compatibility")

    def test_options(self) -> None:
        response = self.router.route("OPTIONS", "/api/health")

        self.assertEqual(response.status, 200)
        self.assertTrue(response.body["data"]["cors"])

    def test_unknown_path_returns_json_error(self) -> None:
        response = self.router.route("POST", "/api/unknown", body_json={})

        self.assertEqual(response.status, 404)
        self.assertFalse(response.body["ok"])
        self.assertEqual(response.body["error"]["code"], "not_found")

    def test_openclaw_notify_routes_valid_payload(self) -> None:
        response = self.router.route(
            "POST",
            "/api/openclaw/notify",
            body_json={
                "type": "generic.notify",
                "display_text": "显示给基站",
                "spoken_text": "播报",
                "suppress_auto_tts": True,
                "metadata": {"source": "test"},
                "session_id": "notify-session",
            },
        )

        self.assertEqual(response.status, 200)
        notification = response.body["data"]["notification"]
        self.assertEqual(notification["notification_type"], "generic.notify")
        self.assertEqual(notification["display_text"], "显示给基站")
        self.assertEqual(notification["spoken_text"], "播报")
        self.assertTrue(notification["suppress_auto_tts"])
        self.assertEqual(notification["session_id"], "notify-session")

    def test_openclaw_notify_requires_type(self) -> None:
        response = self.router.route(
            "POST",
            "/api/openclaw/notify",
            body_json={"display_text": "missing type"},
        )

        self.assertEqual(response.status, 400)
        self.assertFalse(response.body["ok"])
        self.assertEqual(response.body["error"]["code"], "missing_type")

    def test_query_parameter_helpers(self) -> None:
        self.assertEqual(
            self.router._query_limit({"limit": ["invalid"]}, default=20),
            20,
        )
        for value in ("true", "1", "yes"):
            with self.subTest(value=value):
                self.assertTrue(
                    self.router._query_bool(
                        {"enabled": [value]},
                        "enabled",
                    ),
                )
        for value in ("false", "0", "no"):
            with self.subTest(value=value):
                self.assertFalse(
                    self.router._query_bool(
                        {"enabled": [value]},
                        "enabled",
                        default=True,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
