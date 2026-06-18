"""PC-side QR visual servo controller for Xiao-An.

The ESP32 firmware for this script is `serialqrservo`.

Flow:
    PC sends F over USB serial.
    ESP32 returns XAN1 + uint32 JPEG length + JPEG bytes.
    OpenCV finds the QR code, computes dx/dy/area, then sends:
        a = short left pulse
        d = short right pulse
        w = short forward pulse, optional distance control
        s = short backward pulse, optional distance control
        x = stop
"""

from __future__ import annotations

import argparse
import struct
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
    import serial
except ImportError as exc:  # pragma: no cover - environment dependent
    raise SystemExit("pyserial is required: pip install pyserial") from exc


MAGIC = b"XAN1"
FRAME_REQUEST = b"F"
MAX_JPEG_BYTES = 250_000


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
    parser = argparse.ArgumentParser(description="QR visual servo over ESP32 USB serial.")
    parser.add_argument("--port", required=True, help="Serial port, for example COM19.")
    parser.add_argument("--baud", type=int, default=2_000_000, help="Serial baud rate.")
    parser.add_argument("--deadband", type=float, default=30.0, help="Horizontal center deadband in pixels.")
    parser.add_argument("--settle-ms", type=int, default=100, help="Pause after each motor command.")
    parser.add_argument("--target-area", type=float, default=0.0, help="Enable distance control when > 0.")
    parser.add_argument("--area-tolerance", type=float, default=1200.0, help="Area tolerance for distance control.")
    parser.add_argument("--print-every", type=int, default=1, help="Print every N frames.")
    parser.add_argument("--no-window", action="store_true", help="Do not show OpenCV preview window.")
    return parser.parse_args()


def read_exact(ser: serial.Serial, size: int) -> bytes:
    data = bytearray()
    deadline = time.monotonic() + 2.0
    while len(data) < size:
        chunk = ser.read(size - len(data))
        if chunk:
            data.extend(chunk)
            continue
        if time.monotonic() > deadline:
            raise TimeoutError(f"serial timeout while reading {size} bytes")
    return bytes(data)


def wait_for_magic(ser: serial.Serial) -> None:
    window = bytearray()
    deadline = time.monotonic() + 2.0
    while True:
        b = ser.read(1)
        if b:
            window += b
            if len(window) > len(MAGIC):
                del window[0]
            if bytes(window) == MAGIC:
                return
            continue
        if time.monotonic() > deadline:
            raise TimeoutError("serial timeout waiting for XAN1 frame magic")


def request_frame(ser: serial.Serial) -> np.ndarray:
    ser.write(FRAME_REQUEST)
    wait_for_magic(ser)
    (jpg_len,) = struct.unpack("<I", read_exact(ser, 4))
    if jpg_len <= 0 or jpg_len > MAX_JPEG_BYTES:
        raise ValueError(f"invalid JPEG length: {jpg_len}")

    jpg = read_exact(ser, jpg_len)
    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("OpenCV failed to decode JPEG frame")
    return frame


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

    if args.target_area > 0:
        if target.area < args.target_area - args.area_tolerance:
            return "w"
        if target.area > args.target_area + args.area_tolerance:
            return "s"

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

    with serial.Serial(args.port, args.baud, timeout=0.05, write_timeout=0.5) as ser:
        ser.dtr = False
        ser.rts = False
        time.sleep(1.2)
        ser.reset_input_buffer()
        ser.write(b"x")

        print(f"[PC] QR visual servo on {args.port} @ {args.baud}")
        print("[PC] Press q in the OpenCV window to stop and quit.")

        try:
            while True:
                frame = request_frame(ser)
                target = detect_qr(detector, frame)
                command = choose_command(target, args)
                ser.write(command.encode("ascii"))
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
                    cv2.imshow("Xiao-An QR Visual Servo", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                time.sleep(max(0, args.settle_ms) / 1000.0)
        finally:
            ser.write(b"x")
            if not args.no_window:
                cv2.destroyAllWindows()
            print("[PC] sent stop")

    return 0


if __name__ == "__main__":
    sys.exit(main())
