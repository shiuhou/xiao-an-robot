"""Basic checks for the shared protocol schema and examples.

These tests intentionally avoid third-party dependencies. They do not replace a
full JSON Schema validator, but they catch missing files and obvious message
shape mistakes early.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "shared" / "protocol" / "schema.json"
EXAMPLES_DIR = REPO_ROOT / "shared" / "examples"


class ProtocolSchemaTest(unittest.TestCase):
    def test_schema_declares_required_message_fields(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertEqual(schema.get("type"), "object")
        self.assertEqual(schema.get("required"), ["type", "ts", "seq", "payload"])
        for field_name in ("type", "ts", "seq", "payload"):
            self.assertIn(field_name, schema.get("properties", {}))

    def test_example_messages_have_common_fields(self) -> None:
        example_paths = sorted(EXAMPLES_DIR.glob("*.json"))
        self.assertGreater(len(example_paths), 0, "shared/examples should contain JSON examples")

        for path in example_paths:
            with self.subTest(path=path.name):
                message = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(message.get("type"), str)
                self.assertIsInstance(message.get("ts"), int)
                self.assertIsInstance(message.get("seq"), int)
                self.assertIsInstance(message.get("payload"), dict)


if __name__ == "__main__":
    unittest.main()

