"""Static architecture checks for the mergetesting firmware slice."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
MERGETEST_SRC = ROOT / "robot" / "mergetesting" / "src"


class MergetestingLayeringTest(unittest.TestCase):
    def test_main_is_thin_app_entrypoint(self) -> None:
        main_cpp = (MERGETEST_SRC / "main.cpp").read_text(encoding="utf-8")

        self.assertIn('#include "app/mergetesting_app.h"', main_cpp)
        self.assertIn("MergetestingApp app;", main_cpp)
        self.assertNotIn("void handleMotionExecute", main_cpp)
        self.assertNotIn("CamStream cam;", main_cpp)
        self.assertNotIn("MotorController motor;", main_cpp)

    def test_phase_one_services_exist(self) -> None:
        expected_files = [
            "app/mergetesting_app.h",
            "app/mergetesting_app.cpp",
            "services/robot_state.h",
            "services/robot_state.cpp",
            "services/status_service.h",
            "services/status_service.cpp",
            "services/motion_service.h",
            "services/motion_service.cpp",
            "services/command_router.h",
            "services/command_router.cpp",
        ]

        for rel_path in expected_files:
            with self.subTest(rel_path=rel_path):
                self.assertTrue((MERGETEST_SRC / rel_path).is_file())

    def test_heartbeat_uses_robot_busy_state_provider(self) -> None:
        ws_header = (MERGETEST_SRC / "ws_client.h").read_text(encoding="utf-8")
        ws_cpp = (MERGETEST_SRC / "ws_client.cpp").read_text(encoding="utf-8")

        self.assertIn("setBusyProvider", ws_header)
        self.assertIn("_busyProvider", ws_cpp)
        self.assertNotIn("sendHeartbeat(false);", ws_cpp)

    def test_control_reconnect_resends_hello_and_caps_backoff(self) -> None:
        ws_header = (MERGETEST_SRC / "ws_client.h").read_text(encoding="utf-8")
        ws_cpp = (MERGETEST_SRC / "ws_client.cpp").read_text(encoding="utf-8")

        self.assertIn("static constexpr uint32_t RETRY_MAX_MS = 30000;", ws_header)
        self.assertIn("_retryMs = min(_retryMs * 2, RETRY_MAX_MS);", ws_cpp)
        self.assertIn("_retryMs = RETRY_MIN_MS;", ws_cpp)
        self.assertIn("sendHello();", ws_cpp)

    def test_unknown_control_type_is_logged_and_ignored(self) -> None:
        router_cpp = (MERGETEST_SRC / "services" / "command_router.cpp").read_text(
            encoding="utf-8"
        )
        unsupported_body = router_cpp.split("void CommandRouter::handleUnsupported", 1)[1]

        self.assertIn("LOGW(\"Router\"", unsupported_body)
        self.assertNotIn("_status.ack", unsupported_body)
        self.assertNotIn("_status.error", unsupported_body)

    def test_phase_one_has_ota_upload_target(self) -> None:
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )

        self.assertIn("[env:mergetesting_display_only_ota]", platformio)
        self.assertIn("extends = env:mergetesting_display_only", platformio)
        self.assertIn("-DENABLE_ARDUINO_OTA=1", platformio)

    def test_control_only_ota_recovers_without_display_camera_or_mic(self) -> None:
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )

        self.assertIn("[env:mergetesting_control_base]", platformio)
        base_body = platformio.split("[env:mergetesting_control_base]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("-DENABLE_ARDUINO_OTA=1", base_body)
        self.assertIn("-DMERGETEST_ENABLE_DISPLAY=0", base_body)
        self.assertIn("-DMERGETEST_ENABLE_CAMERA=0", base_body)
        self.assertIn("-DMERGETEST_ENABLE_MIC=0", base_body)
        self.assertNotIn("-DMERGETEST_ENABLE_MOTOR=", base_body)
        self.assertNotIn("-DMERGETEST_ENABLE_SPEAKER=", base_body)

        self.assertIn("[env:mergetesting_control_ping]", platformio)
        ping_body = platformio.split("[env:mergetesting_control_ping]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_control_base", ping_body)
        self.assertIn("-DMERGETEST_ENABLE_MOTOR=0", ping_body)
        self.assertIn("-DMERGETEST_ENABLE_SPEAKER=0", ping_body)

        self.assertIn("[env:mergetesting_control_ping_ota]", platformio)
        ping_ota_body = platformio.split("[env:mergetesting_control_ping_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_control_ping", ping_ota_body)
        self.assertIn("upload_protocol = espota", ping_ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", ping_ota_body)

        self.assertIn("[env:mergetesting_motor_only]", platformio)
        motor_body = platformio.split("[env:mergetesting_motor_only]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_control_base", motor_body)
        self.assertIn("-DMERGETEST_ENABLE_MOTOR=1", motor_body)
        self.assertIn("-DMERGETEST_ENABLE_SPEAKER=0", motor_body)
        self.assertNotIn("-DMERGETEST_ENABLE_MOTOR=0", motor_body)

        self.assertIn("[env:mergetesting_motor_only_ota]", platformio)
        motor_ota_body = platformio.split("[env:mergetesting_motor_only_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_motor_only", motor_ota_body)
        self.assertIn("upload_protocol = espota", motor_ota_body)

        self.assertIn("[env:mergetesting_speaker_only]", platformio)
        speaker_body = platformio.split("[env:mergetesting_speaker_only]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_control_base", speaker_body)
        self.assertIn("-DMERGETEST_ENABLE_MOTOR=0", speaker_body)
        self.assertIn("-DMERGETEST_ENABLE_SPEAKER=1", speaker_body)
        self.assertNotIn("-DMERGETEST_ENABLE_SPEAKER=0", speaker_body)

        self.assertIn("[env:mergetesting_speaker_only_ota]", platformio)
        speaker_ota_body = platformio.split("[env:mergetesting_speaker_only_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_speaker_only", speaker_ota_body)
        self.assertIn("upload_protocol = espota", speaker_ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", speaker_ota_body)
        self.assertIn("--host_ip=192.168.137.1", speaker_ota_body)
        self.assertIn("[env:mergetesting_speaker_drain_only_ota]", platformio)
        self.assertIn("-DMERGETEST_SPEAKER_PCM_DRAIN_ONLY=1", platformio)

        self.assertIn("[env:mergetesting_speaker_altpins_only]", platformio)
        altpins_body = platformio.split("[env:mergetesting_speaker_altpins_only]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_speaker_only", altpins_body)
        self.assertIn("-DMERGETEST_SPEAKER_BCLK=39", altpins_body)
        self.assertIn("-DMERGETEST_SPEAKER_LRC=40", altpins_body)
        self.assertIn("-DMERGETEST_SPEAKER_DIN=41", altpins_body)
        self.assertIn("[env:mergetesting_speaker_altpins_only_ota]", platformio)
        altpins_ota_body = platformio.split("[env:mergetesting_speaker_altpins_only_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_speaker_altpins_only", altpins_ota_body)
        self.assertIn("upload_protocol = espota", altpins_ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", altpins_ota_body)
        self.assertIn("--host_ip=192.168.137.1", altpins_ota_body)
        self.assertIn("[env:mergetesting_speaker_altpins_phrase_only]", platformio)
        altpins_phrase_body = platformio.split("[env:mergetesting_speaker_altpins_phrase_only]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_speaker_altpins_only", altpins_phrase_body)
        self.assertIn("-DMERGETEST_SPEAKER_TTS_EMBEDDED_PHRASE=1", altpins_phrase_body)
        self.assertIn("-DEMBEDDED_TTS_GAIN=16", altpins_phrase_body)
        self.assertIn("[env:mergetesting_speaker_altpins_phrase_only_ota]", platformio)
        altpins_phrase_ota_body = platformio.split("[env:mergetesting_speaker_altpins_phrase_only_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_speaker_altpins_phrase_only", altpins_phrase_ota_body)
        self.assertIn("upload_protocol = espota", altpins_phrase_ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", altpins_phrase_ota_body)
        self.assertIn("--host_ip=192.168.137.1", altpins_phrase_ota_body)

        self.assertIn("[env:mergetesting_speaker_shared_clock_only]", platformio)
        shared_clock_body = platformio.split("[env:mergetesting_speaker_shared_clock_only]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_speaker_only", shared_clock_body)
        self.assertIn("-DMERGETEST_SPEAKER_BCLK=39", shared_clock_body)
        self.assertIn("-DMERGETEST_SPEAKER_LRC=40", shared_clock_body)
        self.assertIn("-DMERGETEST_SPEAKER_DIN=47", shared_clock_body)
        self.assertIn("[env:mergetesting_speaker_shared_clock_only_ota]", platformio)
        shared_clock_ota_body = platformio.split("[env:mergetesting_speaker_shared_clock_only_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_speaker_shared_clock_only", shared_clock_ota_body)
        self.assertIn("upload_protocol = espota", shared_clock_ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", shared_clock_ota_body)
        self.assertIn("--host_ip=192.168.137.1", shared_clock_ota_body)
        self.assertIn("[env:mergetesting_speaker_shared_clock_phrase_only]", platformio)
        shared_clock_phrase_body = platformio.split("[env:mergetesting_speaker_shared_clock_phrase_only]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_speaker_shared_clock_only", shared_clock_phrase_body)
        self.assertIn("-DMERGETEST_SPEAKER_TTS_EMBEDDED_PHRASE=1", shared_clock_phrase_body)
        self.assertIn("-DEMBEDDED_TTS_GAIN=16", shared_clock_phrase_body)
        self.assertIn("[env:mergetesting_speaker_shared_clock_phrase_only_ota]", platformio)
        shared_clock_phrase_ota_body = platformio.split("[env:mergetesting_speaker_shared_clock_phrase_only_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_speaker_shared_clock_phrase_only", shared_clock_phrase_ota_body)
        self.assertIn("upload_protocol = espota", shared_clock_phrase_ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", shared_clock_phrase_ota_body)
        self.assertIn("--host_ip=192.168.137.1", shared_clock_phrase_ota_body)

        face240_ota_body = platformio.split("[env:mergetesting_face240_only_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_face240_only", face240_ota_body)
        self.assertIn("upload_protocol = espota", face240_ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", face240_ota_body)
        self.assertIn("--host_ip=192.168.137.1", face240_ota_body)

        self.assertIn("[env:mergetesting_control_only]", platformio)
        self.assertIn("[env:mergetesting_control_only_ota]", platformio)

        control_body = platformio.split("[env:mergetesting_control_only]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_control_base", control_body)
        self.assertIn("-DMERGETEST_ENABLE_MOTOR=1", control_body)
        self.assertIn("-DMERGETEST_ENABLE_SPEAKER=1", control_body)
        self.assertNotIn("-DMERGETEST_ENABLE_MOTOR=0", control_body)
        self.assertNotIn("-DMERGETEST_ENABLE_SPEAKER=0", control_body)

        ota_body = platformio.split("[env:mergetesting_control_only_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_control_only", ota_body)
        self.assertIn("upload_protocol = espota", ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", ota_body)

    def test_mic_only_env_is_split_and_has_ota_upload_target(self) -> None:
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )

        self.assertIn("[env:mergetesting_mic_only]", platformio)
        mic_body = platformio.split("[env:mergetesting_mic_only]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting", mic_body)
        self.assertIn("-DMERGETEST_ENABLE_DISPLAY=0", mic_body)
        self.assertIn("-DMERGETEST_ENABLE_CAMERA=0", mic_body)
        self.assertIn("-DMERGETEST_ENABLE_MOTOR=0", mic_body)
        self.assertIn("-DMERGETEST_ENABLE_SPEAKER=0", mic_body)
        self.assertIn("-DMERGETEST_ENABLE_MIC=1", mic_body)
        self.assertIn("-DENABLE_ARDUINO_OTA=1", mic_body)

        self.assertIn("[env:mergetesting_mic_only_ota]", platformio)
        mic_ota_body = platformio.split("[env:mergetesting_mic_only_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_mic_only", mic_ota_body)
        self.assertIn("upload_protocol = espota", mic_ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", mic_ota_body)

    def test_audio_shared_i2s_diag_env_is_half_duplex_and_pin_safe(self) -> None:
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )
        diag_source_path = MERGETEST_SRC / "audio_shared_i2s_diag_main.cpp"
        self.assertTrue(
            diag_source_path.exists(),
            "missing audio_shared_i2s_diag_main.cpp",
        )
        diag_cpp = diag_source_path.read_text(encoding="utf-8")

        self.assertIn("[env:mergetesting_audio_shared_i2s_diag]", platformio)
        diag_body = platformio.split("[env:mergetesting_audio_shared_i2s_diag]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("-DMERGETEST_AUDIO_SHARED_I2S_DIAG=1", diag_body)
        self.assertIn("-DMERGETEST_ENABLE_DISPLAY=0", diag_body)
        self.assertIn("-DMERGETEST_ENABLE_CAMERA=0", diag_body)
        self.assertIn("-DMERGETEST_ENABLE_MOTOR=0", diag_body)
        self.assertIn("-DMERGETEST_ENABLE_SPEAKER=0", diag_body)
        self.assertIn("-DMERGETEST_ENABLE_MIC=0", diag_body)
        self.assertIn("-DMERGETEST_ENABLE_SERIAL_MOCK_ASR=0", diag_body)
        self.assertIn("-DI2S_SHARED_BCLK=39", diag_body)
        self.assertIn("-DI2S_SHARED_WS=40", diag_body)
        self.assertIn("-DI2S_MIC_SD=41", diag_body)
        self.assertIn("-DI2S_SPK_DIN=47", diag_body)
        self.assertIn("-DEMBEDDED_TTS_GAIN=20", diag_body)
        self.assertIn("-DAUDIO_DIAG_LOG_UART0=1", diag_body)
        self.assertIn("-DAUDIO_DIAG_UART0_RX=44", diag_body)
        self.assertIn("-DAUDIO_DIAG_UART0_TX=43", diag_body)
        self.assertIn("-<*>", diag_body)
        self.assertIn("+<audio_shared_i2s_diag_main.cpp>", diag_body)
        self.assertNotIn("+<*>", diag_body)
        self.assertNotIn("-DI2S_SHARED_BCLK=35", diag_body)
        self.assertNotIn("-DI2S_SHARED_BCLK=36", diag_body)
        self.assertNotIn("-DI2S_SHARED_BCLK=37", diag_body)
        self.assertNotIn("-DI2S_SHARED_WS=35", diag_body)
        self.assertNotIn("-DI2S_SHARED_WS=36", diag_body)
        self.assertNotIn("-DI2S_SHARED_WS=37", diag_body)
        self.assertNotIn("-DI2S_MIC_SD=35", diag_body)
        self.assertNotIn("-DI2S_MIC_SD=36", diag_body)
        self.assertNotIn("-DI2S_MIC_SD=37", diag_body)
        self.assertNotIn("-DI2S_SPK_DIN=35", diag_body)
        self.assertNotIn("-DI2S_SPK_DIN=36", diag_body)
        self.assertNotIn("-DI2S_SPK_DIN=37", diag_body)

        self.assertIn("#define I2S_SHARED_BCLK 39", diag_cpp)
        self.assertIn("#define I2S_SHARED_WS 40", diag_cpp)
        self.assertIn("#define I2S_MIC_SD 41", diag_cpp)
        self.assertIn("#define I2S_SPK_DIN 47", diag_cpp)
        self.assertIn("#define AUDIO_DIAG_LOG_SERIAL Serial0", diag_cpp)
        self.assertIn("AUDIO_DIAG_LOG_SERIAL.begin(115200, SERIAL_8N1, AUDIO_DIAG_UART0_RX, AUDIO_DIAG_UART0_TX)", diag_cpp)
        self.assertNotIn("Serial.begin(115200)", diag_cpp)
        self.assertIn("I2S_MODE_MASTER | I2S_MODE_RX", diag_cpp)
        self.assertIn("I2S_MODE_MASTER | I2S_MODE_TX", diag_cpp)
        self.assertNotIn("I2S_MODE_RX | I2S_MODE_TX", diag_cpp)
        self.assertIn("i2s_driver_uninstall", diag_cpp)
        self.assertIn("digitalWrite(I2S_SPK_DIN, LOW)", diag_cpp)
        self.assertIn('"[AudioDiag] mode=LISTEN start"', diag_cpp)
        self.assertIn('"[AudioDiag] i2s_rx_init ok"', diag_cpp)
        self.assertIn('"[AudioDiag] rms=', diag_cpp)
        self.assertIn("voice_detected", diag_cpp)
        self.assertIn('"[AudioDiag] i2s_rx_stop ok"', diag_cpp)
        self.assertIn('"[AudioDiag] mode=SPEAK start"', diag_cpp)
        self.assertIn('"[AudioDiag] i2s_tx_init ok"', diag_cpp)
        self.assertIn("OUTPUT_PROBE_AMPLITUDE = 30000", diag_cpp)
        self.assertIn("OUTPUT_PROBE_FREQUENCY_HZ = 1000", diag_cpp)
        self.assertIn("playOutputProbeTone", diag_cpp)
        self.assertIn('"[AudioDiag] output_probe_tone frequency_hz=%u amplitude=%d duration_ms=%u', diag_cpp)
        self.assertIn("pcm_samples", diag_cpp)
        self.assertIn("gain", diag_cpp)
        self.assertIn("bytes_written", diag_cpp)
        self.assertIn('"[AudioDiag] playback_done ok"', diag_cpp)
        self.assertIn('"[AudioDiag] i2s_tx_stop ok"', diag_cpp)
        self.assertIn("free_heap", diag_cpp)
        self.assertIn("free_psram", diag_cpp)
        self.assertIn("stack_high_water_mark", diag_cpp)
        self.assertIn("i2s_read return code", diag_cpp)
        self.assertIn("i2s_write return code", diag_cpp)
        self.assertIn("LISTEN_MS = 2000", diag_cpp)
        self.assertIn("SWITCH_TEST_CYCLES = 5", diag_cpp)
        self.assertIn("STABILITY_TEST_MS = 180000", diag_cpp)
        self.assertIn("runListenSpeakCycle", diag_cpp)
        self.assertIn("#if MERGETEST_AUDIO_SHARED_I2S_DIAG", diag_cpp)
        self.assertIn("MIC_RX_I2S_PORT = I2S_NUM_0", diag_cpp)
        self.assertIn("SPEAKER_TX_I2S_PORT = I2S_NUM_1", diag_cpp)
        self.assertIn("#define EMBEDDED_TTS_GAIN 20", diag_cpp)
        self.assertNotIn("AUDIO_I2S_PORT = I2S_NUM_0", diag_cpp)

    def test_full_face240_env_combines_verified_hardware_paths_with_ota(self) -> None:
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )

        self.assertIn("[env:mergetesting_full_face240]", platformio)
        full_body = platformio.split("[env:mergetesting_full_face240]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting", full_body)
        self.assertIn("-DMERGETEST_ENABLE_DISPLAY=1", full_body)
        self.assertIn("-DMERGETEST_DISPLAY_FACE240=1", full_body)
        self.assertIn("-DMERGETEST_ENABLE_CAMERA=1", full_body)
        self.assertIn("-DMERGETEST_CAMERA_USE_VGA=0", full_body)
        self.assertIn("-DMERGETEST_ENABLE_MOTOR=1", full_body)
        self.assertIn("-DMERGETEST_ENABLE_SPEAKER=1", full_body)
        self.assertIn("-DMERGETEST_ENABLE_MIC=1", full_body)
        self.assertIn("-DMERGETEST_SPEAKER_BCLK=39", full_body)
        self.assertIn("-DMERGETEST_SPEAKER_LRC=40", full_body)
        self.assertIn("-DMERGETEST_SPEAKER_DIN=47", full_body)

        self.assertIn("[env:mergetesting_full_face240_ota]", platformio)
        ota_body = platformio.split("[env:mergetesting_full_face240_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_full_face240", ota_body)
        self.assertIn("upload_protocol = espota", ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", ota_body)
        self.assertIn("--host_ip=192.168.137.1", ota_body)
        self.assertIn("-DENABLE_ARDUINO_OTA=1", ota_body)

    def test_care_demo_face240_env_excludes_media_streams(self) -> None:
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )

        self.assertIn("[env:mergetesting_care_demo_face240]", platformio)
        care_body = platformio.split("[env:mergetesting_care_demo_face240]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("-DMERGETEST_ENABLE_DISPLAY=1", care_body)
        self.assertIn("-DMERGETEST_DISPLAY_FACE240=1", care_body)
        self.assertIn("-DMERGETEST_ENABLE_CAMERA=0", care_body)
        self.assertIn("-DMERGETEST_ENABLE_MOTOR=1", care_body)
        self.assertIn("-DMERGETEST_ENABLE_SPEAKER=1", care_body)
        self.assertIn("-DMERGETEST_ENABLE_MIC=0", care_body)

        self.assertIn("[env:mergetesting_care_demo_face240_ota]", platformio)
        care_ota_body = platformio.split("[env:mergetesting_care_demo_face240_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_care_demo_face240", care_ota_body)
        self.assertIn("upload_protocol = espota", care_ota_body)
        self.assertIn("--host_ip=192.168.137.1", care_ota_body)
        self.assertIn("-DENABLE_ARDUINO_OTA=1", care_ota_body)

    def test_ws_optional_media_channels_follow_compile_flags(self) -> None:
        ws_cpp = (MERGETEST_SRC / "ws_client.cpp").read_text(encoding="utf-8")
        connect_all = ws_cpp.split("void WSClient::_connectAll()", 1)[1].split(
            "void WSClient::loop()", 1
        )[0]
        loop_body = ws_cpp.split("void WSClient::loop()", 1)[1].split(
            "void WSClient::setVideoFps", 1
        )[0]

        self.assertIn("#if MERGETEST_ENABLE_CAMERA", connect_all)
        self.assertIn("#if MERGETEST_ENABLE_MIC", connect_all)
        self.assertIn("#if MERGETEST_ENABLE_CAMERA", loop_body)
        self.assertIn("#if MERGETEST_ENABLE_MIC", loop_body)

    def test_websocket_tcp_timeout_stays_below_task_watchdog_window(self) -> None:
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )

        self.assertIn("-DWEBSOCKETS_TCP_TIMEOUT=1000", platformio)

    def test_main_loop_yields_to_avoid_task_watchdog_resets(self) -> None:
        app_cpp = (MERGETEST_SRC / "app" / "mergetesting_app.cpp").read_text(
            encoding="utf-8"
        )
        loop_body = app_cpp.split("void MergetestingApp::loop()", 1)[1]

        self.assertRegex(loop_body, r"\b(delay|yield)\(")

    def test_control_only_can_disable_idle_wdt_for_blocking_ws_bringup(self) -> None:
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )
        app_cpp = (MERGETEST_SRC / "app" / "mergetesting_app.cpp").read_text(
            encoding="utf-8"
        )

        control_body = platformio.split("[env:mergetesting_control_only]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("-DMERGETEST_DISABLE_IDLE_WDT=1", control_body)
        self.assertIn("#if MERGETEST_DISABLE_IDLE_WDT", app_cpp)
        self.assertIn("disableCore0WDT();", app_cpp)

    def test_motion_service_is_non_blocking_and_tick_driven(self) -> None:
        motion_header = (MERGETEST_SRC / "services" / "motion_service.h").read_text(
            encoding="utf-8"
        )
        motion_cpp = (MERGETEST_SRC / "services" / "motion_service.cpp").read_text(
            encoding="utf-8"
        )
        app_cpp = (MERGETEST_SRC / "app" / "mergetesting_app.cpp").read_text(
            encoding="utf-8"
        )
        ws_cpp = (MERGETEST_SRC / "ws_client.cpp").read_text(encoding="utf-8")

        self.assertIn("void loop();", motion_header)
        self.assertIn("_motion.loop();", app_cpp)
        self.assertNotIn("delay(", motion_cpp)
        self.assertNotIn("_motor.execute(", motion_cpp)
        self.assertIn('return clampDuration(timeoutMs, timeoutMs);', motion_cpp)
        self.assertIn("no distance => run for timeout_ms", motion_cpp)
        self.assertIn("durationOverrideFromPayload", motion_cpp)
        self.assertIn('params["duration_ms"]', motion_cpp)
        self.assertIn('payload["action_id"]', ws_cpp)

    def test_local_sound_reports_unsupported_sound(self) -> None:
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")
        play_local_body = speaker_cpp.split("bool speaker_play_local", 1)[1].split(
            "bool speaker_play_tts_mock", 1
        )[0]

        self.assertIn('LOGW("Speaker"', play_local_body)
        self.assertIn("return false;", play_local_body)
        self.assertNotIn("playTone(660, 200)", play_local_body)

    def test_audio_router_unknown_sound_acks_error_and_reports_error(self) -> None:
        router_cpp = (MERGETEST_SRC / "services" / "command_router.cpp").read_text(
            encoding="utf-8"
        )
        local_body = router_cpp.split("void CommandRouter::handleAudioPlayLocal", 1)[1].split(
            "void CommandRouter::handleAudioPlayTts", 1
        )[0]

        self.assertIn("isSupportedLocalSound", router_cpp)
        self.assertIn("_status.error", local_body)
        self.assertIn("unsupported local sound", local_body)
        self.assertIn("ErrorCode::AUDIO_UNSUPPORTED", local_body)
        self.assertIn('_status.ack(MsgType::AUDIO_PLAY_LOCAL, "error", "unsupported_sound")', local_body)
        self.assertIn("speaker_init_fail", local_body)

    def test_audio_router_tts_failure_reports_error_and_reports_accepted_ack(self) -> None:
        router_cpp = (MERGETEST_SRC / "services" / "command_router.cpp").read_text(
            encoding="utf-8"
        )
        tts_body = router_cpp.split("void CommandRouter::handleAudioPlayTts", 1)[1].split(
            "void CommandRouter::handleUnsupported", 1
        )[0]

        self.assertIn('LOGI("Router", "audio.play_tts mock tone', tts_body)
        self.assertIn('_status.ack(MsgType::AUDIO_PLAY_TTS, "accepted", "queued")', tts_body)
        self.assertIn("_status.error", tts_body)
        self.assertIn("speaker not ready", tts_body)
        self.assertIn("ErrorCode::AUDIO_UNSUPPORTED", tts_body)

    def test_speaker_defaults_match_max98357a_wiring(self) -> None:
        pins = (MERGETEST_SRC / "hardware_pins.h").read_text(encoding="utf-8")
        config = (MERGETEST_SRC / "config.h").read_text(encoding="utf-8")

        self.assertIn("#define SPEAKER_I2S_BCLK 39", pins)
        self.assertIn("#define SPEAKER_I2S_LRC 40", pins)
        self.assertIn("#define SPEAKER_I2S_DIN 47", pins)
        self.assertIn("#define MERGETEST_SPEAKER_BCLK 39", config)
        self.assertIn("#define MERGETEST_SPEAKER_LRC 40", config)
        self.assertIn("#define MERGETEST_SPEAKER_DIN 47", config)

    def test_speaker_local_sounds_map_to_distinct_chimes_and_tts_mock_tone(self) -> None:
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")
        play_local_body = speaker_cpp.split("bool speaker_play_local", 1)[1].split(
            "bool speaker_play_tts_mock", 1
        )[0]
        blocking_body = speaker_cpp.split("bool playLocalBlocking", 1)[1].split(
            "TtsBlockingResult playTtsBlocking", 1
        )[0]
        tts_blocking_body = speaker_cpp.split("TtsBlockingResult playTtsBlocking", 1)[1].split(
            "void speakerTask", 1
        )[0]

        self.assertIn("bool playCareChime()", speaker_cpp)
        self.assertIn("bool playAlarmBeeps()", speaker_cpp)
        self.assertIn("bool playWakeChime()", speaker_cpp)
        self.assertIn("return startPlaybackTask(sound);", play_local_body)
        self.assertIn("ok = ensureSpeakerReady() && playCareChime();", blocking_body)
        self.assertIn("ok = ensureSpeakerReady() && playAlarmBeeps();", blocking_body)
        self.assertIn("ok = ensureSpeakerReady() && playWakeChime();", blocking_body)
        self.assertIn("return false;", play_local_body)
        self.assertGreaterEqual(tts_blocking_body.count("playTone("), 3)
        self.assertIn("preview=%s", tts_blocking_body)

    def test_speaker_local_playback_runs_off_control_loop(self) -> None:
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")

        self.assertIn("void speakerTask(void*", speaker_cpp)
        self.assertIn("xTaskCreate", speaker_cpp)
        self.assertIn("gPlaying", speaker_cpp)
        self.assertIn("vTaskDelay(pdMS_TO_TICKS(100));", speaker_cpp)
        self.assertIn("SPEAKER_AMPLITUDE = 2400", speaker_cpp)
        self.assertIn("startPlaybackTask", speaker_cpp)
        self.assertIn("return startPlaybackTask(sound);", speaker_cpp)

    def test_speaker_tts_mock_runs_off_control_loop(self) -> None:
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")
        tts_body = speaker_cpp.split("bool speaker_play_tts_mock", 1)[1].split(
            "void speaker_stop", 1
        )[0]

        self.assertIn("TtsBlockingResult playTtsBlocking", speaker_cpp)
        self.assertIn("startTtsTask", speaker_cpp)
        self.assertIn("return startTtsTask(textPreview);", tts_body)
        self.assertNotIn("playTone(", tts_body)

    def test_serial_mock_can_trigger_tts_for_usb_speaker_debug(self) -> None:
        app_cpp = (MERGETEST_SRC / "app" / "mergetesting_app.cpp").read_text(
            encoding="utf-8"
        )
        serial_body = app_cpp.split("void MergetestingApp::pollSerialMockAsr", 1)[1].split(
            "void MergetestingApp::updateTransportState", 1
        )[0]

        self.assertIn('line == "tts"', serial_body)
        self.assertIn('line.startsWith("tts ")', serial_body)
        self.assertIn("speaker_play_tts_mock", serial_body)
        self.assertIn('"serial test tts"', serial_body)

    def test_speaker_only_can_play_embedded_sentence_for_tts(self) -> None:
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")
        embedded_header = (MERGETEST_SRC / "embedded_tts_phrase.h").read_text(
            encoding="utf-8"
        )

        speaker_body = platformio.split("[env:mergetesting_speaker_phrase_only]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_speaker_only", speaker_body)
        self.assertIn("-DMERGETEST_SPEAKER_TTS_EMBEDDED_PHRASE=1", speaker_body)
        self.assertIn("-DEMBEDDED_TTS_GAIN=16", speaker_body)
        self.assertIn("[env:mergetesting_speaker_phrase_only_ota]", platformio)
        self.assertIn('#include "embedded_tts_phrase.h"', speaker_cpp)
        self.assertIn("EmbeddedTtsPhrase::PCM", speaker_cpp)
        self.assertIn("writeMonoPcmS16Le(", speaker_cpp)
        self.assertIn("EMBEDDED_TTS_GAIN", speaker_cpp)
        self.assertIn("scalePcmSample", speaker_cpp)
        self.assertIn("INT16_MAX", speaker_cpp)
        self.assertIn("INT16_MIN", speaker_cpp)
        self.assertIn('TEXT = "I can speak now."', embedded_header)
        self.assertIn("PCM_LEN = ", embedded_header)

    def test_speaker_tts_reports_playback_done_after_async_completion(self) -> None:
        protocol = (MERGETEST_SRC / "protocol.h").read_text(encoding="utf-8")
        speaker_header = (MERGETEST_SRC / "speaker.h").read_text(encoding="utf-8")
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")
        router_cpp = (MERGETEST_SRC / "services" / "command_router.cpp").read_text(
            encoding="utf-8"
        )
        status_header = (MERGETEST_SRC / "services" / "status_service.h").read_text(
            encoding="utf-8"
        )
        ws_header = (MERGETEST_SRC / "ws_client.h").read_text(encoding="utf-8")
        ws_cpp = (MERGETEST_SRC / "ws_client.cpp").read_text(encoding="utf-8")

        self.assertIn('AUDIO_PLAYBACK_DONE', protocol)
        self.assertIn('"audio.playback_done"', protocol)
        self.assertIn("struct SpeakerPlaybackResult", speaker_header)
        self.assertIn("speaker_take_tts_playback_result", speaker_header)
        self.assertIn("storeTtsPlaybackResult", speaker_cpp)
        self.assertIn("bytesWritten", speaker_cpp)
        self.assertIn("durationMs", speaker_cpp)
        self.assertIn("speaker_take_tts_playback_result", router_cpp)
        self.assertIn("audioPlaybackDone", router_cpp)
        self.assertIn('"accepted"', router_cpp)
        self.assertIn("void audioPlaybackDone", status_header)
        self.assertIn("sendAudioPlaybackDone", ws_header)
        self.assertIn("sendAudioPlaybackDone", ws_cpp)

    def test_speaker_accepts_pcm_chunks_from_control_binary_frames(self) -> None:
        speaker_header = (MERGETEST_SRC / "speaker.h").read_text(encoding="utf-8")
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")
        ws_cpp = (MERGETEST_SRC / "ws_client.cpp").read_text(encoding="utf-8")
        router_cpp = (MERGETEST_SRC / "services" / "command_router.cpp").read_text(
            encoding="utf-8"
        )

        self.assertIn("speaker_begin_pcm_stream", speaker_header)
        self.assertIn("speaker_write_pcm_chunk", speaker_header)
        self.assertIn("speaker_end_pcm_stream", speaker_header)
        self.assertIn("bool speaker_write_pcm_chunk(const uint8_t* pcm, size_t len)", speaker_cpp)
        self.assertIn("speaker_write_pcm_chunk(payload, length)", ws_cpp)
        self.assertIn("case WStype_BIN:", ws_cpp)
        self.assertIn("audio_format", router_cpp)
        self.assertIn("pcm_stream", router_cpp)
        self.assertIn('_status.ack(MsgType::AUDIO_PLAY_TTS, "accepted", "pcm_stream")', router_cpp)

    def test_speaker_pcm_stream_is_played_incrementally_from_chunks(self) -> None:
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")
        write_body = speaker_cpp.split("bool speaker_write_pcm_chunk", 1)[1].split(
            "void speaker_end_pcm_stream", 1
        )[0]
        end_body = speaker_cpp.split("void speaker_end_pcm_stream", 1)[1].split(
            "void speaker_stop", 1
        )[0]

        self.assertIn("resetPcmBuffer", speaker_cpp)
        self.assertIn("enqueuePcmChunk(pcm, len)", write_body)
        self.assertIn("xQueueSend", speaker_cpp)
        self.assertIn("void pcmStreamTask(void* arg)", speaker_cpp)
        self.assertIn("writeMonoPcmS16Le(job.data", speaker_cpp)
        self.assertIn("finishPcmPlayback();", end_body)
        self.assertNotIn("appendPcmBuffer(pcm, len)", write_body)
        self.assertNotIn("xTaskCreate", end_body)
        self.assertNotIn("speaker_begin_pcm_stream", write_body)
        self.assertNotIn("void pcmPlaybackTask(void* arg)", speaker_cpp)

    def test_speaker_pcm_playback_skips_leading_silence_before_i2s_write(self) -> None:
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")
        pcm_body = speaker_cpp.split("bool writeMonoPcmS16Le", 1)[1].split(
            "void resetPcmBuffer", 1
        )[0]

        self.assertIn("countLeadingQuietPcmFrames", speaker_cpp)
        self.assertIn("PCM_LEADING_TRIM_THRESHOLD", speaker_cpp)
        self.assertIn("size_t offset = countLeadingQuietPcmFrames(pcm, frames);", pcm_body)
        self.assertIn("pcm mono skipped leading quiet frames", pcm_body)

    def test_pcm_stream_keeps_i2s_driver_installed_after_stream(self) -> None:
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")
        task_body = speaker_cpp.split("void pcmStreamTask", 1)[1].split(
            "void speakerTask", 1
        )[0]
        end_body = speaker_cpp.split("void speaker_end_pcm_stream", 1)[1].split(
            "void speaker_stop", 1
        )[0]
        finish_body = speaker_cpp.split("void finishPcmPlayback", 1)[1].split(
            "void pcmStreamTask", 1
        )[0]

        self.assertIn("finishPcmPlayback", speaker_cpp)
        self.assertIn("finishPcmPlayback();", task_body)
        self.assertIn("i2s_zero_dma_buffer(SPEAKER_I2S_PORT)", finish_body)
        self.assertNotIn("releaseSpeakerI2S();", end_body)

    def test_tts_pcm_stream_starts_from_app_loop_not_websocket_callback(self) -> None:
        app_cpp = (MERGETEST_SRC / "app" / "mergetesting_app.cpp").read_text(
            encoding="utf-8"
        )
        router_header = (MERGETEST_SRC / "services" / "command_router.h").read_text(
            encoding="utf-8"
        )
        router_cpp = (MERGETEST_SRC / "services" / "command_router.cpp").read_text(
            encoding="utf-8"
        )
        tts_body = router_cpp.split("void CommandRouter::handleAudioPlayTts", 1)[1].split(
            "void CommandRouter::startPendingPcmStream", 1
        )[0]

        self.assertIn("_router.loop();", app_cpp)
        self.assertIn("void loop();", router_header)
        self.assertIn("PendingPcmStream", router_header)
        self.assertIn("void CommandRouter::startPendingPcmStream", router_cpp)
        self.assertIn("void CommandRouter::finishPendingPcmStream", router_cpp)
        self.assertIn("PendingPcmStreamEnd", router_header)
        self.assertNotIn("speaker_begin_pcm_stream", tts_body)

    def test_speaker_i2s_writes_use_timeout_and_yield(self) -> None:
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")

        self.assertNotIn("portMAX_DELAY", speaker_cpp)
        self.assertIn("SPEAKER_WRITE_TIMEOUT_TICKS", speaker_cpp)
        self.assertIn("PCM_WRITE_TIMEOUT_TICKS", speaker_cpp)
        self.assertIn("PCM_PLAYBACK_FRAMES_PER_BUFFER = 128", speaker_cpp)
        self.assertIn("PCM_WRITE_TIMEOUT_TICKS = pdMS_TO_TICKS(20)", speaker_cpp)
        self.assertIn("pdMS_TO_TICKS", speaker_cpp)
        self.assertIn("vTaskDelay(1);", speaker_cpp)
        self.assertIn("writeFramesWithTimeout", speaker_cpp)
        self.assertIn("writeFramesWithTimeout(stereoBuffer, chunk, timeoutTicks)", speaker_cpp)
        self.assertNotIn("esp_task_wdt_reset();", speaker_cpp)
        self.assertIn("ESP_OK", speaker_cpp)
        self.assertIn("bool playTone", speaker_cpp)
        self.assertNotIn("pcm playback progress", speaker_cpp)

    def test_speaker_i2s_is_lazy_and_released_between_playbacks(self) -> None:
        app_cpp = (MERGETEST_SRC / "app" / "mergetesting_app.cpp").read_text(
            encoding="utf-8"
        )
        speaker_cpp = (MERGETEST_SRC / "speaker.cpp").read_text(encoding="utf-8")
        setup_body = app_cpp.split("void MergetestingApp::setup()", 1)[1].split(
            "void MergetestingApp::loop()", 1
        )[0]

        self.assertNotIn("speaker_init();", setup_body)
        self.assertIn("ensureSpeakerReady", speaker_cpp)
        self.assertIn("releaseSpeakerI2S", speaker_cpp)
        self.assertIn("i2s_driver_uninstall(SPEAKER_I2S_PORT)", speaker_cpp)
        self.assertIn("releaseSpeakerI2S();", speaker_cpp)

    def test_display_expression_rejects_unknown_expression(self) -> None:
        router_cpp = (MERGETEST_SRC / "services" / "command_router.cpp").read_text(
            encoding="utf-8"
        )
        display_body = router_cpp.split("void CommandRouter::handleDisplayExpression", 1)[1].split(
            "void CommandRouter::handleAudioPlayLocal", 1
        )[0]

        self.assertIn("isSupportedExpression", router_cpp)
        self.assertIn("_status.error", display_body)
        self.assertIn('_status.ack(MsgType::DISPLAY_EXPRESSION, "error"', display_body)

        unsupported_branch = display_body.split("if (!isSupportedExpression(expr))", 1)[1].split(
            "return;", 1
        )[0]
        self.assertNotIn("display_emotion", unsupported_branch)
        self.assertNotIn("_state.setExpression", unsupported_branch)
        self.assertNotIn("_status.sendCurrent", unsupported_branch)

    def test_face240_mergetesting_tracks_roboeyes_source_but_keeps_control_wrapper(self) -> None:
        face_cpp = (MERGETEST_SRC / "face240_display.cpp").read_text(encoding="utf-8")

        self.assertIn("Full-screen face layout (~1.12x, centered on 320x240)", face_cpp)
        self.assertIn("static constexpr int16_t FACE_CY = 118", face_cpp)
        self.assertIn("static constexpr int16_t EYE_CX_L = 84", face_cpp)
        self.assertIn("static constexpr int16_t EYE_CX_R = 236", face_cpp)
        self.assertIn("MOUTH_BOWL", face_cpp)
        self.assertIn("fillBottomSemicircle", face_cpp)
        self.assertIn("applyExprIdle", face_cpp)
        self.assertIn("static bool autoCarousel = false", face_cpp)

        self.assertIn("static FaceExpression protocolToFace", face_cpp)
        self.assertIn("void face240_init()", face_cpp)
        self.assertIn("void face240_emotion", face_cpp)
        self.assertIn("void face240_tick()", face_cpp)
        self.assertNotIn("void setup()", face_cpp)
        self.assertNotIn("void loop()", face_cpp)
        self.assertIn("if (TFT_BL >= 0)", face_cpp)

    def test_face240_boot_frame_uses_default_expression(self) -> None:
        face_cpp = (MERGETEST_SRC / "face240_display.cpp").read_text(encoding="utf-8")

        self.assertIn("static FaceExpression expression = FACE_HAPPY;", face_cpp)
        self.assertIn("copyPoseImmediate(poseForExpression(expression));", face_cpp)
        self.assertIn("renderRoboEyesFrame(now);", face_cpp)
        self.assertIn("pushRoboEyesFrame();", face_cpp)
        self.assertNotIn("copyPoseImmediate(poseForExpression(FACE_CONTENT));", face_cpp)

    def test_audio_commands_ack_status_and_report_errors(self) -> None:
        router_cpp = (MERGETEST_SRC / "services" / "command_router.cpp").read_text(
            encoding="utf-8"
        )
        local_body = router_cpp.split("void CommandRouter::handleAudioPlayLocal", 1)[1].split(
            "void CommandRouter::handleAudioPlayTts", 1
        )[0]
        tts_body = router_cpp.split("void CommandRouter::handleAudioPlayTts", 1)[1].split(
            "void CommandRouter::handleUnsupported", 1
        )[0]

        self.assertIn("_status.sendCurrent();", local_body)
        self.assertIn('_status.ack(MsgType::AUDIO_PLAY_LOCAL, "ok"', local_body)
        self.assertIn("_status.error", local_body)
        self.assertIn('_status.ack(MsgType::AUDIO_PLAY_LOCAL, "error"', local_body)

        self.assertIn("_status.sendCurrent();", tts_body)
        self.assertIn('_status.ack(MsgType::AUDIO_PLAY_TTS, "accepted"', tts_body)
        self.assertIn("_status.error", tts_body)
        self.assertIn('_status.ack(MsgType::AUDIO_PLAY_TTS, "error"', tts_body)

    def test_camera_smoke_path_uses_qvga_jpeg_meta_binary_and_fallback(self) -> None:
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )
        cam_cpp = (MERGETEST_SRC / "cam_stream.cpp").read_text(encoding="utf-8")
        ws_cpp = (MERGETEST_SRC / "ws_client.cpp").read_text(encoding="utf-8")

        cam_env = platformio.split("[env:mergetesting_cam_only]", 1)[1].split(
            "[env:mergetesting_cam_only_ota]", 1
        )[0]
        self.assertIn("-DMERGETEST_CAMERA_USE_VGA=0", cam_env)
        self.assertIn("FRAMESIZE_QVGA", cam_cpp)
        self.assertIn("fb->format != PIXFORMAT_JPEG", cam_cpp)
        self.assertIn("ws.sendVideoFrameMeta", cam_cpp)
        self.assertIn("ws.sendVideoBinary", cam_cpp)
        self.assertIn("ws.sendVideoFrameBase64", cam_cpp)
        self.assertIn("_video.sendBIN(header, sizeof(header));", ws_cpp)
        self.assertIn("_video.sendBIN(jpeg, len);", ws_cpp)

    def test_mic_stream_uses_inmp441_pins_and_only_reads_when_audio_connected(self) -> None:
        pins = (MERGETEST_SRC / "hardware_pins.h").read_text(encoding="utf-8")
        mic_cpp = (MERGETEST_SRC / "mic_stream.cpp").read_text(encoding="utf-8")
        ws_cpp = (MERGETEST_SRC / "ws_client.cpp").read_text(encoding="utf-8")
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )

        self.assertIn("#define MIC_I2S_BCLK 39", pins)
        self.assertIn("#define MIC_I2S_WS 40", pins)
        self.assertIn("#define MIC_I2S_DIN 41", pins)
        self.assertIn("MERGETEST_MIC_CHANNEL_FORMAT", mic_cpp)
        self.assertIn("MERGETEST_MIC_SHIFT_BITS", mic_cpp)
        self.assertIn("MERGETEST_MIC_SEND_INTERVAL_MS", mic_cpp)
        self.assertIn("raw >> MERGETEST_MIC_SHIFT_BITS", mic_cpp)
        self.assertIn("if (!_active || !ws.isAudioConnected())", mic_cpp)
        self.assertIn("i2s_read", mic_cpp)
        self.assertIn("ws.sendAudioChunkMeta(_chunkId);", mic_cpp)
        self.assertIn("ws.sendAudioBinary", mic_cpp)
        self.assertIn("payload[\"format\"] = \"pcm_s16le\";", ws_cpp)
        self.assertIn("_audio.sendBIN(pcm, len);", ws_cpp)

        self.assertIn("[env:mergetesting_mic_only_shift16]", platformio)
        shift16_body = platformio.split("[env:mergetesting_mic_only_shift16]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_mic_only", shift16_body)
        self.assertIn("-DMERGETEST_MIC_SHIFT_BITS=16", shift16_body)

        self.assertIn("[env:mergetesting_mic_only_shift16_asr]", platformio)
        asr_body = platformio.split("[env:mergetesting_mic_only_shift16_asr]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_mic_only_shift16", asr_body)
        self.assertIn("-DMERGETEST_MIC_SEND_INTERVAL_MS=20", asr_body)

        self.assertIn("[env:mergetesting_mic_only_shift18_asr]", platformio)
        shift18_asr_body = platformio.split("[env:mergetesting_mic_only_shift18_asr]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_mic_only", shift18_asr_body)
        self.assertIn("-DMERGETEST_MIC_SHIFT_BITS=18", shift18_asr_body)
        self.assertIn("-DMERGETEST_MIC_SEND_INTERVAL_MS=20", shift18_asr_body)

        self.assertIn("[env:mergetesting_mic_only_shift18_asr_ota]", platformio)
        shift18_asr_ota_body = platformio.split("[env:mergetesting_mic_only_shift18_asr_ota]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_mic_only_shift18_asr", shift18_asr_ota_body)
        self.assertIn("upload_protocol = espota", shift18_asr_ota_body)
        self.assertIn("upload_port = xiao-an-esp32.local", shift18_asr_ota_body)
        self.assertIn("--host_ip=192.168.137.1", shift18_asr_ota_body)

        self.assertIn("[env:mergetesting_mic_only_right_shift16]", platformio)
        right_shift16_body = platformio.split("[env:mergetesting_mic_only_right_shift16]", 1)[1].split(
            "[env:", 1
        )[0]
        self.assertIn("extends = env:mergetesting_mic_only_shift16", right_shift16_body)
        self.assertIn("-DMERGETEST_MIC_CHANNEL_FORMAT=I2S_CHANNEL_FMT_ONLY_RIGHT", right_shift16_body)

    def test_motion_service_rejects_when_motor_disabled(self) -> None:
        motion_cpp = (MERGETEST_SRC / "services" / "motion_service.cpp").read_text(
            encoding="utf-8"
        )

        self.assertIn("#if !MERGETEST_ENABLE_MOTOR", motion_cpp)
        self.assertIn('"motor_disabled"', motion_cpp)
        self.assertIn("MOTOR_MIN_BENCH_DUTY", motion_cpp)

    def test_motor_pwm_uses_valid_esp32s3_ledc_channels(self) -> None:
        motor_cpp = (MERGETEST_SRC / "motor_ctrl.cpp").read_text(encoding="utf-8")
        camera_config = (MERGETEST_SRC / "camera_ov2640_config.h").read_text(
            encoding="utf-8"
        )

        self.assertIn("#define MERGETEST_MOTOR_CH_L_IN1 0", motor_cpp)
        self.assertIn("#define MERGETEST_MOTOR_CH_L_IN2 1", motor_cpp)
        self.assertIn("#define MERGETEST_MOTOR_CH_R_IN1 2", motor_cpp)
        self.assertIn("#define MERGETEST_MOTOR_CH_R_IN2 3", motor_cpp)
        self.assertIn("MERGETEST_MOTOR_CH_L_IN1", motor_cpp)
        self.assertIn("Invalid channels make ledcSetup() return 0 Hz", motor_cpp)
        self.assertIn("away from OV2640 XCLK on LEDC_CHANNEL_7", motor_cpp)
        self.assertIn("config->ledc_channel = LEDC_CHANNEL_7", camera_config)
        self.assertNotIn("MOTOR_CH_R_IN2 = 7", motor_cpp)
        self.assertIn("Re-init after camera", (MERGETEST_SRC / "app" / "mergetesting_app.cpp").read_text(encoding="utf-8"))

        pins = (MERGETEST_SRC / "hardware_pins.h").read_text(encoding="utf-8")
        platformio = (ROOT / "robot" / "mergetesting" / "platformio.ini").read_text(
            encoding="utf-8"
        )
        motor_only_body = platformio.split("[env:mergetesting_motor_only]", 1)[1].split(
            "[env:", 1
        )[0]

        self.assertIn("#define PIN_MOTOR_L_IN1 1", pins)
        self.assertIn("#define PIN_MOTOR_L_IN2 2", pins)
        self.assertIn("#define PIN_MOTOR_R_IN1 3", pins)
        self.assertIn("#define PIN_MOTOR_R_IN2 48", pins)
        self.assertIn("-DTFT_BL=-1", platformio)
        self.assertIn("-DMERGETEST_MOTOR_CH_L_IN1=4", motor_only_body)
        self.assertIn("-DMERGETEST_MOTOR_CH_L_IN2=5", motor_only_body)
        self.assertIn("-DMERGETEST_MOTOR_CH_R_IN1=6", motor_only_body)
        self.assertIn("-DMERGETEST_MOTOR_CH_R_IN2=7", motor_only_body)


if __name__ == "__main__":
    unittest.main()
