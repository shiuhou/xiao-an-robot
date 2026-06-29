# Scripts

Startup, setup, and debug helpers for the DK-2500 base station, local Agent, and mock robot.

Run from the repository root unless a script says otherwise.

Hardware bring-up helpers live under `robot/firmware/tools/`. Python operation and probe tools live under [../tools/](../tools/).

## Setup

| Script | Purpose |
| --- | --- |
| `check_env.sh` | Basic shell/environment check. |
| `init_db.sh` | Initialize local runtime DB/schema. |
| `setup_intel_board.sh` | DK-2500 / Intel board setup helper. |

## Start

| Script | Purpose |
| --- | --- |
| `start_base_station.sh` | Start base-station runtime. |
| `start_agent.sh` | Start local Agent runtime. |
| `start_local_api.sh` | Start local debug API. |
| `start_all.sh` | Start combined local services. |
| `run_mock_robot.sh` | Start mock robot for software checks. |

## Debug

| Script | Purpose |
| --- | --- |
| `debug_camera_cv_vlm_e2e.py` | Camera/CV/VLM end-to-end diagnostic. |
| `try_vlm_once.py` | Single VLM attempt/debug helper. |

## Common Order

```bash
bash scripts/check_env.sh
bash scripts/init_db.sh
bash scripts/start_base_station.sh
bash scripts/start_agent.sh
bash scripts/run_mock_robot.sh
```

## Boundary

Scripts are wrappers. Keep reusable Python behavior in `tools/`, `base_station/`, or `agent/` rather than growing large shell scripts.

