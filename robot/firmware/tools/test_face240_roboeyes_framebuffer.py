from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "face240_roboeyes_demo_main.cpp"
PIO = ROOT / "platformio.ini"


def main() -> None:
    source = SRC.read_text(encoding="utf-8")
    platformio = PIO.read_text(encoding="utf-8")

    required_source = [
        "frameBuffer",
        "pushFrameBuffer",
        "pushFrameRegion",
        "pushRoboEyesFrame",
        "renderRoboEyesFrame",
        "updateRoboEyesTargets",
        "drawRoboEye",
    ]
    missing = [token for token in required_source if token not in source]
    assert not missing, f"missing framebuffer RoboEyes symbols: {missing}"

    forbidden_source = [
        "static void drawFace()",
        "if (now - lastFrameMs < 40)",
        "inCozmoEye",
    ]
    present = [token for token in forbidden_source if token in source]
    assert not present, f"old slow/cozmo render path still present: {present}"

    assert "[env:face240_roboeyes]" in platformio
    assert "+<face240_roboeyes_demo_main.cpp>" in platformio


if __name__ == "__main__":
    main()
