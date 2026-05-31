#!/usr/bin/env bash
set -e

# Print the recommended startup order. Keeping process management manual avoids
# hiding logs or leaving background services running by accident.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Recommended startup order:"
echo "1. bash scripts/start_base_station.sh"
echo "2. bash scripts/start_agent.sh"
echo "3. bash scripts/run_mock_robot.sh"
echo ""
echo "Open each command in a separate terminal so logs stay visible."

