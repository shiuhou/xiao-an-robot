"""Offline validation of the 衔接层 phase-1 mapping + note column (no network, no live DB).

Proves, against a THROWAWAY temp DB (never the live xiao_an.db):
  1. bridge.note_to_kwargs -> insert_work_activity lands a row with the locked
     mapping (project_id NULL, project_hint=title, note=gist, source="screen").
  2. gist reaches OpenClaw at ask-time: ContextBuilder surfaces `note` in
     context["work"]["recent_activities"] for a help-style query.
  3. the idempotent migration adds `note` to a DB that predates the column
     (the real situation for the already-existing board DB).

Run from pc_screen_tracker/:
    python scripts/validate_bridge.py
Exit 0 = all green.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

# --- make both `tracker.*` (pc client) and `agent.*` (0703 repo) importable ---
_PC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../pc_screen_tracker
_REPO_ROOT = os.path.dirname(_PC_ROOT)                                    # .../xiao-an-robot (repo root)
for _p in (_PC_ROOT, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tracker.bridge import note_to_kwargs                # noqa: E402
from tracker.understander import ActivityNote            # noqa: E402
from agent.core.memory import XiaoAnMemoryStore          # noqa: E402
from agent.core.context_builder import ContextBuilder    # noqa: E402


def _note(app, title, act, pid, hint, gist, conf, dur, ts) -> ActivityNote:
    return ActivityNote(
        timestamp_ms=ts, app_name=app, window_title=title, activity_type=act,
        project_id=pid, project_hint=hint, gist=gist, confidence=conf,
        duration_seconds=dur,
    )


SAMPLES = [
    _note("chrome.exe", "xiao-an-robot - GitHub", "researching", "t_001",
          "调研小安衔接层", "在 GitHub 上看 work_activities 表结构", 0.82, 95,
          1_720_000_000_000),
    _note("Code.exe", "memory.py - Visual Studio Code", "coding", "t_001",
          "调研小安衔接层", "在 VSCode 里读 insert_work_activity 实现", 0.88, 210,
          1_720_000_120_000),
    _note("WeChat.exe", "微信", "communication", "t_002",
          "和同学沟通", "微信里讨论比赛分工", 0.5, 60,
          1_720_000_400_000),
]


def check(label: str, cond: bool) -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise AssertionError(label)


def scenario_fresh_db() -> None:
    print("== 场景A:新库(schema.sql 已含 note 列)==")
    with tempfile.TemporaryDirectory(prefix="xa_validate_") as d:
        db = os.path.join(d, "throwaway.db")
        store = XiaoAnMemoryStore(db)
        for n in SAMPLES:
            store.insert_work_activity(**note_to_kwargs(n))

        rows = store.query_recent_work_activities(limit=10)
        check("落库行数 == 3", len(rows) == 3)
        latest = rows[0]  # newest first -> the WeChat note (ts 400000)
        check("最新行 source == 'screen'", latest["source"] == "screen")
        check("最新行 project_id 为 NULL(t_00x 未入库)", latest["project_id"] is None)
        check("最新行 project_hint == 任务名", latest["project_hint"] == "和同学沟通")
        check("最新行 note == gist", latest["note"] == "微信里讨论比赛分工")

        # ask-time: does gist reach OpenClaw's injected context?
        ctx = ContextBuilder(memory_store=store).build_for_text("帮我看看我当前工作的进度")
        check("求助文本触发 work scope", "work" in ctx)
        acts = ctx.get("work", {}).get("recent_activities", [])
        check("work.recent_activities 非空", len(acts) > 0)
        check("注入的活动带 note 字段", "note" in acts[0])
        check("注入的 note == 最新 gist", acts[0]["note"] == "微信里讨论比赛分工")
        store.close()


def scenario_migration() -> None:
    print("== 场景B:旧库迁移(建一个没有 note 列的 work_activities,再打开)==")
    with tempfile.TemporaryDirectory(prefix="xa_migrate_") as d:
        db = os.path.join(d, "legacy.db")
        # hand-build a pre-note work_activities table (the board's current shape)
        con = sqlite3.connect(db)
        con.executescript(
            """
            CREATE TABLE work_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                timestamp_ms INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'unknown',
                app_name TEXT NOT NULL DEFAULT '',
                window_title TEXT NOT NULL DEFAULT '',
                activity_type TEXT NOT NULL DEFAULT 'unknown',
                project_hint TEXT,
                project_id INTEGER,
                confidence REAL NOT NULL DEFAULT 0.0,
                duration_seconds REAL,
                created_at_ms INTEGER NOT NULL
            );
            """
        )
        con.commit()
        cols_before = {r[1] for r in con.execute("PRAGMA table_info(work_activities)")}
        con.close()
        check("旧库确实没有 note 列", "note" not in cols_before)

        # opening via the store must run the idempotent migration
        store = XiaoAnMemoryStore(db)
        cols_after = {r[1] for r in store.conn.execute("PRAGMA table_info(work_activities)")}
        check("打开后 note 列已被 ALTER 补上", "note" in cols_after)

        store.insert_work_activity(**note_to_kwargs(SAMPLES[0]))
        row = store.query_recent_work_activities(limit=1)[0]
        check("迁移后写入的行 note == gist", row["note"] == SAMPLES[0].gist)
        store.close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        scenario_fresh_db()
        scenario_migration()
    except AssertionError as exc:
        print(f"\n❌ 验证失败:{exc}")
        return 1
    print("\n✅ 全部通过:映射正确、gist 求助时可达 OpenClaw、旧库迁移生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
