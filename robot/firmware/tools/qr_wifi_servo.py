"""WiFi QR visual servo controller for Xiao-An.

Mirrors `qr_visual_servo.py`, but fetches JPEG frames from the ESP32 AP:
    http://192.168.4.1/jpg

The ESP32 only serves camera JPEG and motor commands, same split as
`serial_qr_servo_main.cpp` + PC-side OpenCV.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

try:
    import cv2
except ImportError as exc:  # pragma: no cover - environment dependent
    raise SystemExit("opencv-python is required: pip install opencv-python") from exc

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - environment dependent
    raise SystemExit("numpy is required: pip install numpy") from exc

try:
    import requests
except ImportError as exc:  # pragma: no cover - environment dependent
    raise SystemExit("requests is required: pip install requests") from exc


@dataclass
class QrTarget:
    seen: bool
    center_x: float = 0.0
    center_y: float = 0.0
    dx: float = 0.0
    dy: float = 0.0
    area: float = 0.0
    points: np.ndarray | None = None
    data: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QR visual servo over ESP32 WiFi AP.")
    parser.add_argument("--host", default="192.168.4.1", help="ESP32 AP IP.")
    parser.add_argument("--deadband", type=float, default=30.0, help="Horizontal center deadband in pixels.")
    parser.add_argument("--interval-ms", type=int, default=500, help="Frame poll interval.")
    parser.add_argument("--print-every", type=int, default=1, help="Print every N frames.")
    parser.add_argument("--no-window", action="store_true", help="Do not show OpenCV preview window.")
    return parser.parse_args()


def request_frame(host: str) -> np.ndarray:
    response = requests.get(f"http://{host}/jpg", timeout=3)
    response.raise_for_status()
    frame = cv2.imdecode(np.frombuffer(response.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("OpenCV failed to decode JPEG frame")
    return frame


def send_command(host: str, command: str) -> None:
    requests.get(f"http://{host}/cmd", params={"c": command}, timeout=2)


def detect_qr(detector: cv2.QRCodeDetector, frame: np.ndarray) -> QrTarget:
    data, points, _ = detector.detectAndDecode(frame)
    if points is None:
        return QrTarget(seen=False)

    pts = points.reshape(-1, 2).astype(np.float32)
    center_x = float(pts[:, 0].mean())
    center_y = float(pts[:, 1].mean())
    frame_h, frame_w = frame.shape[:2]
    area = float(abs(cv2.contourArea(pts)))

    return QrTarget(
        seen=True,
        center_x=center_x,
        center_y=center_y,
        dx=center_x - frame_w / 2.0,
        dy=center_y - frame_h / 2.0,
        area=area,
        points=pts,
        data=data or "",
    )


def choose_command(target: QrTarget, args: argparse.Namespace) -> str:
    if not target.seen:
        return "x"
    if abs(target.dx) > args.deadband:
        return "d" if target.dx > 0 else "a"
    return "x"


def draw_overlay(frame: np.ndarray, target: QrTarget, command: str, deadband: float) -> None:
    h, w = frame.shape[:2]
    center = (w // 2, h // 2)
    cv2.drawMarker(frame, center, (255, 255, 255), cv2.MARKER_CROSS, 18, 1)
    cv2.line(frame, (int(w / 2 - deadband), 0), (int(w / 2 - deadband), h), (80, 80, 80), 1)
    cv2.line(frame, (int(w / 2 + deadband), 0), (int(w / 2 + deadband), h), (80, 80, 80), 1)

    if target.seen and target.points is not None:
        pts = target.points.astype(int)
        cv2.polylines(frame, [pts], True, (0, 255, 0), 2)
        cv2.circle(frame, (int(target.center_x), int(target.center_y)), 5, (0, 255, 255), -1)
        label = f"dx={target.dx:+.1f} dy={target.dy:+.1f} area={target.area:.0f} cmd={command}"
    else:
        label = "QR not seen cmd=x"

    cv2.putText(frame, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)


def main() -> int:
    args = parse_args()
    detector = cv2.QRCodeDetector()
    frame_count = 0

    print(f"[PC] WiFi QR visual servo on http://{args.host}/jpg")
    print("[PC] Press q in the OpenCV window to stop and quit.")

    try:
        while True:
            frame = request_frame(args.host)
            target = detect_qr(detector, frame)
            command = choose_command(target, args)
            send_command(args.host, command)
            frame_count += 1

            if frame_count % max(1, args.print_every) == 0:
                if target.seen:
                    print(
                        "[PC] QR "
                        f"x={target.center_x:.1f} y={target.center_y:.1f} "
                        f"dx={target.dx:+.1f} dy={target.dy:+.1f} "
                        f"area={target.area:.0f} cmd={command} data={target.data!r}"
                    )
                else:
                    print("[PC] QR not seen cmd=x")

            if not args.no_window:
                draw_overlay(frame, target, command, args.deadband)
                cv2.imshow("Xiao-An WiFi QR Visual Servo", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            time.sleep(max(0, args.interval_ms) / 1000.0)
    finally:
        try:
            send_command(args.host, "x")
        except requests.RequestException:
            pass
        if not args.no_window:
            cv2.destroyAllWindows()
        print("[PC] sent stop")

    return 0


if __name__ == "__main__":
    sys.exit(main())
