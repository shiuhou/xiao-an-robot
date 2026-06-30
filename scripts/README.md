# Scripts

Startup, setup, and debug helpers for the DK-2500 base station, local Agent, and mock robot.

Run from the repository root unless a script says otherwise.

Hardware bring-up helpers live under `robot/firmware/tools/`. Python operation and probe tools live under [../tools/](../tools/).

## Setup

Implementations live under `scripts/setup/`. Root-level `scripts/*.sh` launchers remain as compatibility wrappers.

| Script | Purpose |
| --- | --- |
| `setup/check_env.sh` | Basic shell/environment check. |
| `setup/init_db.sh` | Initialize local runtime DB/schema. |
| `setup/setup_intel_board.sh` | DK-2500 / Intel board setup helper. |

## Start

Implementations live under `scripts/start/`. Root-level launchers remain for existing docs and habits.

| Script | Purpose |
| --- | --- |
| `start/start_base_station.sh` | Start base-station runtime. |
| `start/start_agent.sh` | Start local Agent runtime. |
| `start/start_local_api.sh` | Start local debug API. |
| `start/start_all.sh` | Start combined local services. |
| `start/run_mock_robot.sh` | Start mock robot for software checks. |

## Debug

Implementations live under `scripts/debug/`. Root-level Python wrappers keep `python scripts\try_vlm_once.py ...` working.

| Script | Purpose |
| --- | --- |
| `debug/debug_camera_cv_vlm_e2e.py` | Camera/CV/VLM end-to-end diagnostic. |
| `debug/try_vlm_once.py` | Single VLM attempt/debug helper. |

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

