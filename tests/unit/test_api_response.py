"""Unit tests for local API response envelopes."""

from __future__ import annotations

import json
import unittest

from base_station.api.response import error, success


class ApiResponseTest(unittest.TestCase):
    def test_success_format(self) -> None:
        response = success({"value": 1})

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, {
            "ok": True,
            "data": {"value": 1},
            "error": None,
        })

    def test_error_format(self) -> None:
        response = error(
            "invalid_request",
            "Request is invalid",
            status=422,
            details={"field": "name"},
        )

        self.assertEqual(response.status, 422)
        self.assertEqual(response.body["ok"], False)
        self.assertIsNone(response.body["data"])
        self.assertEqual(response.body["error"], {
            "code": "invalid_request",
            "message": "Request is invalid",
            "details": {"field": "name"},
        })

    def test_responses_are_json_serializable(self) -> None:
        for response in (
            success(),
            error("not_found", "Not found", status=404),
        ):
            with self.subTest(status=response.status):
                encoded = json.dumps(response.body)
                self.assertTrue(encoded)


if __name__ == "__main__":
    unittest.main()
