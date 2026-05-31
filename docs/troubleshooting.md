# Troubleshooting

## WebSocket Cannot Connect

- Confirm the base station server is running.
- Confirm the client is using the right host and port.
- Check that `/control` is included in the WebSocket URL.

## Port Is Already In Use

- Find the process using port `8765`.
- Stop the old server or change the configured control port.

## Database Does Not Exist

Run:

```bash
bash scripts/init_db.sh
```

Then confirm `agent/data/xiao_an.db` exists.

## Virtual Environment Is Not Active

Activate the correct environment before installing or running:

```bash
source base_station/venv/bin/activate
source agent/venv/bin/activate
```

Use one terminal per service to avoid mixing environments.

## Model Files Do Not Exist

- Check `base_station/models/`.
- Run `bash base_station/models/download_models.sh` if the model download script is ready for your network.
- Do not commit downloaded model files.

## Microphone or Camera Permission Is Missing

- Confirm the device appears in `lsusb`.
- Check OS privacy settings.
- Test microphone with `arecord`.
- Test camera with the OpenCV snippet in `hardware/dk2500/peripheral_test.md`.

## Agent Does Not Receive Trigger Events

- Confirm the base station receives robot messages.
- Confirm the Agent process is running.
- Check the gateway path between `base_station/` and `agent/`.
- Inspect logs in the terminal first, then add structured logs under `logs/` if needed.

