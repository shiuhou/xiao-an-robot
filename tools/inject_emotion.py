"""Inject one emotion record into the local SQLite database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from base_station.monitor.emotion_db import EmotionDB


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Insert one emotion row into the Xiao An SQLite database.")
    parser.add_argument("--db", default="agent/data/xiao_an.db", help="SQLite database path.")
    parser.add_argument("--source", choices=["face", "voice"], default="face", help="Emotion source.")
    parser.add_argument("--emotion", default="neutral", help="Emotion tag to insert.")
    parser.add_argument("--confidence", type=float, default=0.8, help="Emotion confidence score.")
    parser.add_argument("--fatigue", type=float, default=0.0, help="Fatigue score.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with EmotionDB(str(db_path)) as db:
        row_id = db.insert_emotion(
            source=args.source,
            emotion_tag=args.emotion,
            confidence=args.confidence,
            fatigue_score=args.fatigue,
        )

    print(json.dumps({
        "inserted": True,
        "id": row_id,
        "db": str(db_path),
        "source": args.source,
        "emotion_tag": args.emotion,
        "confidence": args.confidence,
        "fatigue_score": args.fatigue,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
