from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "src" / "face240_raw_design_test.cpp"


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    required_symbols = [
        "struct DirtyRect",
        "MAX_DIRTY_RECTS",
        "drawDirtyFaceFrame",
        "drawRectRegion",
        "markFullFaceRefresh",
    ]
    missing = [symbol for symbol in required_symbols if symbol not in text]
    if missing:
        print("missing dirty-rect symbols:", ", ".join(missing))
        return 1

    forbidden = "setAddressWindow(FACE_X0, FACE_Y0, FACE_X0 + FACE_W - 1, FACE_Y0 + FACE_H - 1)"
    if forbidden in text:
        print("full-face address window still present in the frame render path")
        return 1

    print("face240 raw dirty-rect structure present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
