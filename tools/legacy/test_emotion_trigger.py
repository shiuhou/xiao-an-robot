"""Manually trigger EmotionMonitorSkill through the base_station /agent route."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.core.gateway import RobotGateway
from agent.skills.emotion_monitor import EmotionMonitorSkill


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a manual emotion trigger to Xiao An.")
    parser.add_argument("--url", default="ws://127.0.0.1:8765/agent", help="Base station /agent WebSocket URL.")
    parser.add_argument("--emotion", default="neutral", help="Emotion tag, for example neutral or anxious.")
    parser.add_argument("--confidence", type=float, default=0.8, help="Emotion confidence score.")
    parser.add_argument("--fatigue", type=float, default=0.0, help="Fatigue score.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    gateway = RobotGateway(url=args.url)
    skill = EmotionMonitorSkill(gateway=gateway)
    result = await skill.run({
        "emotion_tag": args.emotion,
        "confidence": args.confidence,
        "fatigue_score": args.fatigue,
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
