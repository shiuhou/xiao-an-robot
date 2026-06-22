"""Smooth WiFi MJPEG preview for Xiao-An motor_cam_wifi_manual.

Uses the same continuous stream path as the browser:
    http://192.168.4.1:81/stream

For QR overlay and coordinates on PC, use:
    python robot/firmware/tools/qr_wifi_servo.py
or the serial tools with serial_qr_servo firmware.
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import cv2
except ImportError as exc:  # pragma: no cover - environment dependent
    raise SystemExit("opencv-python is required: pip install opencv-python") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="View Xiao-An WiFi MJPEG camera stream.")
    parser.add_argument("--host", default="192.168.4.1", help="ESP32 AP IP.")
    parser.add_argument("--path", default="/stream", help="MJPEG path, default /stream on port 81.")
    parser.add_argument("--port", type=int, default=81, help="Stream port.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    url = f"http://{args.host}:{args.port}{args.path}"
    print(f"[PC] Opening {url}")
    print("[PC] Press q in the OpenCV window to quit.")

    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        print("[PC][ERROR] failed to open MJPEG stream")
        print("[PC] Check WiFi XiaoAn-Motor and firmware upload.")
        return 1

    window = "Xiao-An WiFi Camera"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    fps_start = time.monotonic()
    frames = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("[PC][WARN] frame read failed, retrying...")
                cap.release()
                time.sleep(0.3)
                cap = cv2.VideoCapture(url)
                continue

            frames += 1
            h, w = frame.shape[:2]
            if frames % 30 == 0:
                elapsed = max(time.monotonic() - fps_start, 0.001)
                print(f"[PC] stream {w}x{h} avg_fps={frames / elapsed:.1f}")

            cv2.putText(
                frame,
                f"{w}x{h}",
                (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
            )
            cv2.imshow(window, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
