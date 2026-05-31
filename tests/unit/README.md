# Unit Tests

This directory holds small tests that can run without a real ESP32 robot, DK2500 device, camera, microphone, or large model files.

Start here when you want to check protocol constants, message shapes, and helper functions. Keep unit tests fast and independent so new contributors can run them often.

Example:

```bash
python -m unittest discover tests/unit
```

