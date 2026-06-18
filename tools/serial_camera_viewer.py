#!/usr/bin/env python
"""OpenCV viewer for Xiao-An ESP32 USB serial camera.

Default mode tracks QR codes with OpenCV's QRCodeDetector and overlays:
    - QR bounding polygon
    - center X/Y in image coordinates
    - DX/DY relative to image center

Firmware protocol:
    PC sends: b"F"
    ESP32 sends:
        magic: b"XAN1"
        length: uint32 little-endian
        payload: JPEG bytes
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from dataclasses import dataclass


MAGIC = b"XAN1"
FRAME_REQUEST = b"F"
MAX_FRAME_BYTES = 256 * 1024


def _import_deps():
    try:
        import cv2
        import numpy as np
        import serial
        from serial.tools import list_ports
    except ImportError as exc:
        missing = exc.name or "required package"
        raise SystemExit(
            f"Missing Python package: {missing}\n"
            "Install dependencies with:\n"
            "  python -m pip install pyserial opencv-python numpy\n"
            "Then run this viewer again."
        ) from exc
    return cv2, np, serial, list_ports


@dataclass
class Target:
    points: list[tuple[int, int]]
    center_x: int
    center_y: int
    label: str


@dataclass
class TrackedTarget:
    target: Target
    last_seen_frame: int
    decoded_text: str


def choose_port(list_ports, requested: str | None) -> str:
    if requested:
        return requested

    ports = list(list_ports.comports())
    if not ports:
        raise SystemExit("No serial ports found. Check the ESP32 USB cable.")

    print("Available serial ports:")
    for idx, port in enumerate(ports, start=1):
        print(f"  [{idx}] {port.device}  {port.description}")

    if len(ports) == 1:
        print(f"Using {ports[0].device}")
        return ports[0].device

    while True:
        choice = input("Select index or COM port, e.g. 2 or COM19: ").strip().upper()
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(ports):
                return ports[index - 1].device
            choice = f"COM{choice}"
        for port in ports:
            if port.device.upper() == choice:
                return port.device
        print("Invalid choice.")


def read_exact(ser, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = ser.read(size - len(data))
        if not chunk:
            raise TimeoutError("serial read timeout")
        data.extend(chunk)
    return bytes(data)


def request_frame(ser) -> None:
    ser.write(FRAME_REQUEST)


def read_frame(ser) -> bytes:
    matched = 0
    while matched < len(MAGIC):
        b = ser.read(1)
        if not b:
            raise TimeoutError("waiting for frame magic")
        if b[0] == MAGIC[matched]:
            matched += 1
        else:
            matched = 1 if b[0] == MAGIC[0] else 0

    length = struct.unpack("<I", read_exact(ser, 4))[0]
    if length <= 0 or length > MAX_FRAME_BYTES:
        raise ValueError(f"invalid frame length: {length}")
    return read_exact(ser, length)


def detect_qr(cv2, frame, allow_undecoded: bool = False) -> Target | None:
    detector = detect_qr.detector

    # Single-code path is noticeably faster and more stable than Multi for
    # this test, where we only need one tracking target.
    text, points, _ = detector.detectAndDecode(frame)
    if text and points is not None:
        pts = points.astype(int).reshape(-1, 2)
        center_x = int(pts[:, 0].mean())
        center_y = int(pts[:, 1].mean())
        return Target([(int(x), int(y)) for x, y in pts], center_x, center_y, text[:20])

    if not allow_undecoded:
        return None

    # Fallback: detect one QR without requiring decode success.
    points = detector.detect(frame)
    if isinstance(points, tuple):
        found, pts = points
        if not found:
            return None
        points = pts
    if points is None:
        return None

    pts = points.astype(int).reshape(-1, 2)
    if len(pts) < 4:
        return None
    center_x = int(pts[:, 0].mean())
    center_y = int(pts[:, 1].mean())
    return Target([(int(x), int(y)) for x, y in pts], center_x, center_y, "")


detect_qr.detector = None  # type: ignore[attr-defined]


def detect_red(cv2, frame) -> Target | None:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    import numpy as np

    mask1 = cv2.inRange(hsv, np.array([0, 90, 70]), np.array([10, 255, 255]))
    mask2 = cv2.inRange(hsv, np.array([170, 90, 70]), np.array([180, 255, 255]))
    mask = cv2.bitwise_or(mask1, mask2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    if area < 80:
        return None

    x, y, w, h = cv2.boundingRect(contour)
    if w > 180 or h > 180:
        return None
    center_x = x + w // 2
    center_y = y + h // 2
    return Target([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], center_x, center_y, "")


def draw_overlay(cv2, frame, target: Target | None, mode: str) -> None:
    h, w = frame.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    shadow = (0, 0, 0)
    white = (255, 255, 255)

    if target is None:
        text = f"NO {mode.upper()}"
        cv2.putText(frame, text, (10, 24), font, 0.45, shadow, 3)
        cv2.putText(frame, text, (10, 24), font, 0.45, white, 1)
        return

    pts = target.points
    for i in range(len(pts)):
        cv2.line(frame, pts[i], pts[(i + 1) % len(pts)], (0, 255, 0), 2)

    cx, cy = target.center_x, target.center_y
    dx = cx - w // 2
    dy = cy - h // 2
    cv2.drawMarker(frame, (cx, cy), (255, 255, 255), markerType=cv2.MARKER_CROSS, markerSize=18, thickness=2)
    line1 = f"X:{cx:03d} Y:{cy:03d}"
    line2 = f"DX:{dx:+04d} DY:{dy:+04d}"
    cv2.putText(frame, line1, (10, 22), font, 0.45, shadow, 3)
    cv2.putText(frame, line1, (10, 22), font, 0.45, white, 1)
    cv2.putText(frame, line2, (10, 42), font, 0.45, shadow, 3)
    cv2.putText(frame, line2, (10, 42), font, 0.45, white, 1)
    if target.label:
        label = target.label[:32]
        cv2.putText(frame, label, (10, h - 14), font, 0.45, shadow, 3)
        cv2.putText(frame, label, (10, h - 14), font, 0.45, (0, 255, 0), 1)


def main() -> int:
    cv2, np, serial, list_ports = _import_deps()
    detect_qr.detector = cv2.QRCodeDetector()  # type: ignore[attr-defined]

    parser = argparse.ArgumentParser(description="View Xiao-An USB serial camera stream.")
    parser.add_argument("--port", help="Serial port, for example COM19.")
    parser.add_argument("--baud", type=int, default=2000000)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--startup-delay", type=float, default=2.0)
    parser.add_argument("--mode", choices=["qr", "red", "none"], default="qr")
    parser.add_argument("--detect-every", type=int, default=2, help="Run detector every N frames.")
    parser.add_argument("--hold-frames", type=int, default=8, help="Keep last target visible for this many frames.")
    parser.add_argument("--allow-undecoded-qr", action="store_true", help="Allow QR corner detection without decoded text.")
    parser.add_argument("--reset-on-open", action="store_true", help="Toggle DTR/RTS on serial open.")
    args = parser.parse_args()

    port = choose_port(list_ports, args.port)
    print(f"Opening {port} at {args.baud} baud")
    print("Press q in the image window to quit.")

    frame_count = 0
    total_frames = 0
    fps_start = time.monotonic()
    tracked: TrackedTarget | None = None
    last_status_print = 0.0
    received_any_frame = False

    window_name = "Xiao-An Serial Camera"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    def show_status(text: str) -> None:
        img = np.zeros((360, 640, 3), dtype=np.uint8)
        y = 45
        for line in text.splitlines():
            cv2.putText(img, line, (24, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            y += 34
        cv2.imshow(window_name, img)
        cv2.waitKey(1)

    show_status(f"Opening {port}...\nWaiting for ESP32 camera frames...")

    ser = serial.Serial()
    ser.port = port
    ser.baudrate = args.baud
    ser.timeout = args.timeout
    ser.write_timeout = args.timeout
    ser.dtr = bool(args.reset_on_open)
    ser.rts = False

    try:
        ser.open()
        time.sleep(args.startup_delay)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        request_frame(ser)

        while True:
            try:
                jpg = read_frame(ser)
            except TimeoutError:
                now = time.monotonic()
                if not received_any_frame and now - last_status_print >= 1.0:
                    msg = (
                        "Waiting for frame...\n"
                        "If this stays here:\n"
                        "1. Close serial monitor/viewers\n"
                        "2. Re-upload serialredtracker\n"
                        "3. Check COM port"
                    )
                    print("Waiting for frame from ESP32...")
                    show_status(msg)
                    last_status_print = now
                request_frame(ser)
                continue
            except ValueError as exc:
                print(f"{exc}; resyncing...")
                ser.reset_input_buffer()
                request_frame(ser)
                continue

            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                print("Skipped corrupt JPEG frame")
                request_frame(ser)
                continue

            # Pipeline transport with processing: ask ESP32 for the next frame
            # before running QR decode on the current one.
            request_frame(ser)

            received_any_frame = True
            total_frames += 1
            if args.mode != "none" and (args.detect_every <= 1 or total_frames % args.detect_every == 1):
                if args.mode == "qr":
                    target = detect_qr(cv2, frame, allow_undecoded=args.allow_undecoded_qr)
                else:
                    target = detect_red(cv2, frame)
                if target is not None:
                    if args.mode == "qr" and tracked is not None and tracked.decoded_text:
                        if target.label == tracked.decoded_text:
                            tracked = TrackedTarget(target=target, last_seen_frame=total_frames, decoded_text=target.label)
                    else:
                        tracked = TrackedTarget(target=target, last_seen_frame=total_frames, decoded_text=target.label)

            if args.mode != "none":
                visible_target = None
                if tracked is not None and total_frames - tracked.last_seen_frame <= args.hold_frames:
                    visible_target = tracked.target
                draw_overlay(cv2, frame, visible_target, args.mode)

            frame_count += 1
            elapsed = time.monotonic() - fps_start
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                fps_start = time.monotonic()
                cv2.setWindowTitle(window_name, f"Xiao-An Serial Camera  {fps:.1f} FPS")

            cv2.imshow(window_name, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        if ser.is_open:
            ser.close()

    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
