"""Unit tests for the local /video test sender."""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from tools.send_test_video_frame import build_video_packet


class SendTestVideoFrameTest(unittest.TestCase):
    def test_build_video_packet_encodes_jpeg_with_header(self) -> None:
        image = np.zeros((240, 320, 3), dtype=np.uint8)

        packet = build_video_packet(image, device_ts=42)

        self.assertGreater(len(packet), 8)
        jpeg_len = int.from_bytes(packet[0:4], "big")
        device_ts = int.from_bytes(packet[4:8], "big")
        self.assertEqual(jpeg_len, len(packet) - 8)
        self.assertEqual(device_ts, 42)

        encoded = np.frombuffer(packet[8:], dtype=np.uint8)
        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape[:2], (240, 320))


if __name__ == "__main__":
    unittest.main()
