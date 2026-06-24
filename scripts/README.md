# Scripts

Startup and setup helpers for the DK-2500 base station, Agent, and mock robot.

**Note:** Hardware bring-up scripts live under `robot/firmware/tools/` (face preview, QR servo, motor keyboard). Root `tools/` holds Python ops probes (`send_robot_command.py`, registry generator, etc.).

Run from the repository root unless a script says otherwise.

Recommended order:

```bash
bash scripts/check_env.sh
bash scripts/init_db.sh
bash scripts/start_base_station.sh
bash scripts/start_agent.sh
bash scripts/run_mock_robot.sh
```

