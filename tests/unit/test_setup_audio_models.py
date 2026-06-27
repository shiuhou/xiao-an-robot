"""Unit tests for tools/setup_audio_models.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import setup_audio_models


class SetupAudioModelsTest(unittest.TestCase):
    def test_check_missing_directory_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing-sensevoice"

            with patch.dict(setup_audio_models.AUDIO_MODELS, {"sensevoice_small": fake_spec(missing)}, clear=True):
                exit_code = setup_audio_models.main(["--only", "sensevoice_small", "--check"])

        self.assertEqual(exit_code, 1)

    def test_check_empty_directory_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "sensevoice-small"
            target.mkdir()

            with patch.dict(setup_audio_models.AUDIO_MODELS, {"sensevoice_small": fake_spec(target)}, clear=True):
                exit_code = setup_audio_models.main(["--only", "sensevoice_small", "--check"])

        self.assertEqual(exit_code, 1)

    def test_check_non_empty_fake_directory_passes_basic_local_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "sensevoice-small"
            target.mkdir()
            target.joinpath("placeholder.txt").write_text("not a real model", encoding="utf-8")

            with patch.dict(setup_audio_models.AUDIO_MODELS, {"sensevoice_small": fake_spec(target)}, clear=True):
                exit_code = setup_audio_models.main(["--only", "sensevoice_small", "--check"])

        self.assertEqual(exit_code, 0)


def fake_spec(target: Path) -> dict:
    return {
        "repo_id": "FunAudioLLM/SenseVoiceSmall",
        "target_dir": target,
        "repo_type": "model",
        "public": True,
        "key_files": ("config.yaml", "model.pt", "configuration.json"),
    }


if __name__ == "__main__":
    unittest.main()
