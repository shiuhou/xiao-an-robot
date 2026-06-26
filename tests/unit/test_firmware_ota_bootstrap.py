from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
FIRMWARE_ROOT = REPO_ROOT / "robot" / "firmware"
SRC_ROOT = FIRMWARE_ROOT / "src"


class FirmwareOtaBootstrapConfigTest(unittest.TestCase):
    def test_ota_bootstrap_sources_and_env_are_wired(self):
        for filename in (
            "ota_bootstrap_main.cpp",
            "ota_update.cpp",
            "ota_update.h",
        ):
            self.assertTrue((SRC_ROOT / filename).is_file(), filename)

        feature_flags = (SRC_ROOT / "feature_flags.h").read_text(encoding="utf-8")
        self.assertIn("#ifndef ENABLE_ARDUINO_OTA", feature_flags)
        self.assertIn("#define ENABLE_ARDUINO_OTA 0", feature_flags)

        platformio = (FIRMWARE_ROOT / "platformio.ini").read_text(encoding="utf-8")
        self.assertIn("[env:ota_bootstrap]", platformio)
        self.assertIn("-DENABLE_ARDUINO_OTA=1", platformio)
        self.assertIn("+<ota_bootstrap_main.cpp>", platformio)
        self.assertIn("+<ota_update.cpp>", platformio)
        self.assertIn("+<motor_ctrl.cpp>", platformio)
        self.assertIn("-<ota_bootstrap_main.cpp>", platformio)
        self.assertIn("-<ota_update.cpp>", platformio)
        self.assertIn("upload_protocol = espota", platformio)
        self.assertIn("upload_port = xiao-an-esp32.local", platformio)

    def test_private_wifi_config_is_ignored(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("robot/firmware/src/config.local.h", gitignore)


if __name__ == "__main__":
    unittest.main()
