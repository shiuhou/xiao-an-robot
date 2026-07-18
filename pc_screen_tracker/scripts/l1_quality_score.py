"""L1 采集层 · 正文质量验收标准 + scorer.

Defines a scorable rubric per screen category and scores an existing
frames.jsonl against it. This is the FIRST iteration of the "define
acceptance criteria, then loop" idea from ARCHITECTURE §13/14 — it
establishes a numeric BASELINE. It does not (yet) auto-tune extraction
parameters; that closed loop is the next iteration once a baseline exists.

Categories (kind + app heuristic, matching the 3-category split the user
defined earlier: browser web/AI-chat, privacy software, OS-native):
  browser   - kind in {browser_page, browser_chat}
  editor    - app == Code.exe (or similar known editors)
  shell     - app in known terminal apps (WindowsTerminal.exe, cmd.exe, ...)
  other     - anything else (explorer.exe task-switcher frames, etc.)

Metrics (0..1, higher = better), computed only over `full`-policy frames
with non-empty content (meta_only/none frames are correctly content-less
by design and are excluded, not penalized):
  noise_ratio      - fraction of content LINES matching a known-noise
                      wordlist (hot-search / nav / recommendation chrome).
                      Lower is better; reported as (1 - noise_ratio) so all
                      metrics share "higher = better".
  relevance_hit     - does content contain a token from the title/url
                      (proxy for "on-topic vs off-topic noise dominating")?
  content_coverage  - fraction of full-policy frames that captured any
                      content at all (extraction didn't come back empty).

Run from pc_screen_tracker/:
    python scripts/l1_quality_score.py frames.jsonl
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

# Known noise: hot-search / trending-news / nav chrome that shows up in
# content regardless of what the user actually searched/read. Extend this
# list as new false-signal patterns are found in future captures.
_NOISE_PATTERNS = [
    r"热搜", r"热榜", r"推荐", r"筛选", r"^登录$", r"^注册$",
    r"股|杠杆|爆仓|山体垮塌|学位被撤销|英格兰|阿根廷",  # sample trending-news tokens seen in real data
    r"广告", r"下载客户端", r"更多回答", r"关注问题",
]
_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS))

_SHELL_APPS = {"windowsterminal.exe", "cmd.exe", "powershell.exe", "conhost.exe"}
_EDITOR_APPS = {"code.exe", "devenv.exe", "pycharm64.exe"}


def _category(app: str, kind: str) -> str:
    app_l = (app or "").lower()
    if kind in {"browser_page", "browser_chat"}:
        return "browser"
    if app_l in _EDITOR_APPS:
        return "editor"
    if app_l in _SHELL_APPS:
        return "shell"
    return "other"


def _relevance_tokens(title: str, url: str) -> set[str]:
    text = f"{title} {url}"
    # crude tokenizer: keep CJK runs and alnum runs >=2 chars
    tokens = re.findall(r"[一-鿿]{2,}|[A-Za-z0-9]{2,}", text)
    return {t.lower() for t in tokens}


def score(frames: list[dict]) -> dict:
    by_cat: dict[str, dict] = defaultdict(lambda: {
        "frames_full": 0, "frames_with_content": 0,
        "lines_total": 0, "lines_noisy": 0,
        "relevance_checked": 0, "relevance_hit": 0,
    })

    for f in frames:
        if f.get("capture_policy") != "full":
            continue
        cat = _category(f.get("app", ""), f.get("kind", ""))
        bucket = by_cat[cat]
        bucket["frames_full"] += 1

        content = f.get("content") or []
        if content:
            bucket["frames_with_content"] += 1
        for line in content:
            bucket["lines_total"] += 1
            if _NOISE_RE.search(line):
                bucket["lines_noisy"] += 1

        tokens = _relevance_tokens(f.get("title", ""), f.get("url", ""))
        joined = " ".join(content).lower()
        if tokens and content:
            bucket["relevance_checked"] += 1
            if any(t in joined for t in tokens):
                bucket["relevance_hit"] += 1

    report = {}
    for cat, b in by_cat.items():
        noise_ratio = b["lines_noisy"] / b["lines_total"] if b["lines_total"] else 0.0
        coverage = b["frames_with_content"] / b["frames_full"] if b["frames_full"] else 0.0
        relevance = b["relevance_hit"] / b["relevance_checked"] if b["relevance_checked"] else None
        report[cat] = {
            "frames_full": b["frames_full"],
            "content_coverage": round(coverage, 2),
            "signal_ratio (1-noise)": round(1 - noise_ratio, 2),
            "relevance_hit_rate": round(relevance, 2) if relevance is not None else "n/a",
            "lines_total": b["lines_total"],
            "lines_noisy": b["lines_noisy"],
        }
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("usage: python scripts/l1_quality_score.py frames.jsonl")
        return 1
    with open(sys.argv[1], encoding="utf-8") as fh:
        frames = [json.loads(line) for line in fh if line.strip() and "kind" in line]

    report = score(frames)
    print(f"== L1 质量基线 == ({sys.argv[1]}, {len(frames)} 条 full-policy 候选帧)\n")
    for cat in ("browser", "editor", "shell", "other"):
        if cat not in report:
            continue
        r = report[cat]
        print(f"[{cat}]  frames={r['frames_full']}  "
              f"content_coverage={r['content_coverage']}  "
              f"signal_ratio={r['signal_ratio (1-noise)']}  "
              f"relevance_hit_rate={r['relevance_hit_rate']}  "
              f"(噪声行 {r['lines_noisy']}/{r['lines_total']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
