# Mocks

Mocks simulate hardware or services that may not be available during early development.

`mock_robot.py` acts like a simple ESP32 robot client. It connects to the base station `/control` WebSocket channel, sends `device.hello`, keeps sending `device.heartbeat`, and prints commands received from the server.

Example:

```bash
python tests/mocks/mock_robot.py --host 127.0.0.1 --port 8765
```

