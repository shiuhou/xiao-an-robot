# Integration Tests

This directory is for tests that exercise multiple modules together, such as the DK2500 WebSocket server and a fake robot client.

Keep these tests safe to run on a development laptop. If a test needs a live server, document the expected command and port in the test file.

Example manual flow:

```bash
bash scripts/start_base_station.sh
bash scripts/run_mock_robot.sh
```

