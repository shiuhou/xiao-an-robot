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

    def test_options(self) -> None:
        response = self.router.route("OPTIONS", "/api/health")

        self.assertEqual(response.status, 200)
        self.assertTrue(response.body["data"]["cors"])

    def test_unknown_path_returns_json_error(self) -> None:
        response = self.router.route("POST", "/api/unknown", body_json={})

        self.assertEqual(response.status, 404)
        self.assertFalse(response.body["ok"])
        self.assertEqual(response.body["error"]["code"], "not_found")

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
