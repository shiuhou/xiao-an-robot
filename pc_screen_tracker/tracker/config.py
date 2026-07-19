"""Runtime configuration for the screen usage tracker.

Privacy tiers (choose via config.json -> "privacy_level"):
  L0  only app name + derived category (no window title, no url)
  L1  + window title + browser domain (no full url path)   <-- default
  L2  + full browser url + focused text preview

The `samples` (stats) table always honours the tier above. When
`understand_enabled` is on, the separate local `frames` table additionally
captures body text at any tier so the Qwen gist can be specific — an explicit
opt-in that overrides the tier's "no text preview" default. Blocklist apps and
sensitive/IM surfaces are still never read, at every tier.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "data" / "usage.db"
CONFIG_PATH = BASE_DIR / "config.json"


@dataclass
class Config:
    privacy_level: str = "L1"          # L0 | L1 | L2
    sample_interval_sec: float = 5.0   # how often to snapshot the foreground
    idle_threshold_sec: float = 60.0   # >= this idle => sample counts as "away"
    db_path: str = str(DEFAULT_DB)
    # apps whose title/url must never be stored even at L1/L2 (regex on app name)
    blocklist_apps: list[str] = field(default_factory=lambda: [
        r"(?i)keepass", r"(?i)1password", r"(?i)bitwarden", r"(?i)bank",
    ])
    # browser processes we try to read a url/domain from (L1+)
    browser_procs: list[str] = field(default_factory=lambda: [
        "chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe",
    ])

    # --- understanding layer (§6.5) ---
    understander_backend: str = "rule"     # "rule" (offline) | "qwen" (cloud)
    qwen_api_key: str = ""                  # DashScope key; keep out of git
    qwen_model: str = "qwen-plus"          # qwen-plus | qwen-max | qwen-turbo
    # OpenAI-compatible DashScope endpoint. Beijing default; international site is
    # https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # wire the understanding layer into live `track`: capture body-text frames and
    # run the segment->understand->post loop. Off by default => `track` stays a
    # pure stats collector (no extra UIA cost, no frames stored, nothing posted).
    understand_enabled: bool = False
    # how often the background understand loop runs a cycle (seconds).
    understand_interval_sec: float = 900.0

    # --- 衔接层 (§衔接, phase 2): board ingest endpoint ---
    # base URL of the Intel board's local API, e.g. "http://10.7.146.x:PORT".
    # Empty => transport disabled (notes stay on the PC).
    board_base_url: str = ""
    # how often `track` pushes a usage summary to the board (voice screen report
    # cache). Only active when board_base_url is set.
    summary_push_interval_sec: float = 1800.0

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
            except Exception as exc:  # noqa: BLE001
                print(f"[config] failed to read config.json, using defaults: {exc}")
        cfg.privacy_level = cfg.privacy_level.upper()
        Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
        return cfg

    def save_template(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
