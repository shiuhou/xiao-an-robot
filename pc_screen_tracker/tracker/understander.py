"""Understanding layer: atomic segment -> activity note (work_activities row).

The Understander is also the *associator* (§6.5): one call per closed segment
decides whether the segment continues an existing task or starts a new one, and
maintains a rolling list of active tasks (the "state") so the model can
reconstruct a cross-window narrative.

Two backends behind one interface:
  * RuleUnderstander  — no network; cheap same-app heuristic. Offline path AND
    the fallback whenever the cloud is unreachable / unconfigured.
  * QwenUnderstander  — Alibaba Qwen via the OpenAI-compatible DashScope
    endpoint, one chat.completions call per full-content segment (JSON mode).

PRIVACY RED LINE (enforced here, not by the caller): a segment whose
capture_policy is not "full" (im=meta_only, sensitive=none) NEVER has its body
put into the request or sent over the network. Those are associated locally on
metadata only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from tracker.segmenter import Segment

try:  # openai is optional; RuleUnderstander works without it
    from openai import OpenAI
except Exception:  # noqa: BLE001  # pragma: no cover
    OpenAI = None

MAX_ACTIVE_TASKS = 5          # rolling-state cap (bounds context size)
TASK_IDLE_CLOSE_S = 1800.0   # 30 min with no activity -> auto-close a task
RECENT_TRACE = 4             # segments of cross-window context kept per task
CONTENT_SNIPPET = 500        # chars of body sent per full segment


# --------------------------------------------------------------------------- #
# outputs
# --------------------------------------------------------------------------- #
@dataclass
class ActivityNote:
    """One row destined for work_activities (§6.5 mapping)."""
    timestamp_ms: int
    app_name: str
    window_title: str
    activity_type: str          # coding/researching/writing/communication/...
    project_id: str
    project_hint: str           # human task title
    gist: str                   # one-line what-this-segment-is
    confidence: float
    duration_seconds: int
    source: str = "screen"
    capture_policy: str = "full"   # from source segment; transport red line only, not a DB column

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class _Task:
    project_id: str
    title: str
    activity_type: str
    last_active_ms: int
    trace: list[dict] = field(default_factory=list)   # [{app,title,gist}]

    def touch(self, seg: Segment, gist: str, activity_type: str) -> None:
        self.last_active_ms = seg.end_ms
        self.activity_type = activity_type or self.activity_type
        self.trace.append({"app": seg.app, "title": seg.title[:80], "gist": gist})
        self.trace = self.trace[-RECENT_TRACE:]


class Understander(Protocol):
    def ingest(self, seg: Segment) -> ActivityNote: ...


# --------------------------------------------------------------------------- #
# shared task-state bookkeeping
# --------------------------------------------------------------------------- #
class _TaskState:
    def __init__(self) -> None:
        self._tasks: dict[str, _Task] = {}
        self._n = 0

    def active(self, now_ms: int) -> list[_Task]:
        live = [t for t in self._tasks.values()
                if now_ms - t.last_active_ms <= TASK_IDLE_CLOSE_S * 1000]
        live.sort(key=lambda t: t.last_active_ms, reverse=True)
        return live[:MAX_ACTIVE_TASKS]

    def get(self, pid: str) -> "_Task | None":
        return self._tasks.get(pid)

    def new(self, title: str, activity_type: str, seg: Segment) -> _Task:
        self._n += 1
        pid = f"t_{self._n:03d}"
        t = _Task(pid, title or "(未命名任务)", activity_type, seg.end_ms)
        self._tasks[pid] = t
        return t


def _note(seg: Segment, task: _Task, gist: str, act: str,
          *, confidence: float) -> ActivityNote:
    return ActivityNote(
        timestamp_ms=seg.start_ms, app_name=seg.app, window_title=seg.title,
        activity_type=act, project_id=task.project_id, project_hint=task.title,
        gist=gist, confidence=round(confidence, 2),
        duration_seconds=int(seg.duration_s),
        capture_policy=seg.capture_policy,
    )


# --------------------------------------------------------------------------- #
# rule backend (no network) — offline path + cloud fallback
# --------------------------------------------------------------------------- #
_ACT_BY_KIND = {
    "browser_chat": "researching", "browser_page": "browsing",
    "im": "communication", "os_shell": "terminal", "generic": "working",
    "sensitive": "private",
}


class RuleUnderstander:
    """Cheap associator: continue the most-recent active task if it's the same
    app, else open a new one. Deterministic, no LLM, good enough offline."""

    def __init__(self, state: "_TaskState | None" = None) -> None:
        self.state = state or _TaskState()

    def ingest(self, seg: Segment) -> ActivityNote:
        act = _ACT_BY_KIND.get(seg.kind, "working")
        gist = seg.title or seg.headline or seg.app
        active = self.state.active(seg.start_ms)
        task = next((t for t in active if t.trace and t.trace[-1]["app"] == seg.app), None)
        if task is None:
            task = self.state.new(seg.headline or seg.title or seg.app, act, seg)
        task.touch(seg, gist, act)
        return _note(seg, task, gist, act, confidence=0.4)


# --------------------------------------------------------------------------- #
# qwen backend (OpenAI-compatible DashScope, JSON mode)
# --------------------------------------------------------------------------- #
_SYSTEM = (
    "你在重建用户的电脑工作叙事。你会看到一个刚结束的活动片段(某个窗口的一段连续停留),"
    "以及当前正在进行的若干任务线(每条带最近几个跨窗口片段的轨迹 recent_trace)。\n"
    "\n你有两项职责,分别遵守不同尺度:\n"
    "\n【职责一 · 关联要敢缝合】判断这个新片段延续了哪条任务,还是开启新任务。"
    "**主动寻找跨窗口的任务关联**,不要因为换了个 app 或网站就默认是新任务。真实工作往往横跨多个"
    "窗口解决同一件事:在编辑器和搜索引擎/GitHub 之间来回=在查资料改同一段代码;先搜某主题再去"
    "对应的代码仓库/文档=同一条调研线;文档和聊天窗口之间来回=根据讨论写材料。判断关联时看"
    "**语义主题、实体(项目名/关键词/机构)、时间邻近、来回切换模式**是否指向同一目标,只要有合理"
    "联系就倾向于归到同一任务(延续),不要过度拆分成一堆碎任务。\n"
    "\n【职责二 · 描述要忠于内容】gist 只能根据片段里实际给出的 title/url/content/键鼠字段来写。"
    "**不要编造字段里没有的具体名词、数字、命令、文件名、主机名、端口、报错**——写得笼统也不要"
    "编造细节。gist 只描述这一个片段,不要把 recent_trace 里别的片段的内容搬进来当成本段发生的事。\n"
    "\n【注意噪声】content 可能含页面噪声(导航栏、热搜榜、推荐位、按钮文字),这些不代表用户真正在看"
    "的东西。若 title/url 指向明确主题(某仓库、某搜索词),以 title/url 为准,别被 content 里无关的"
    "新闻标题带偏。content 为空或只有噪声时,就当作浏览/切换类,confidence 相应降低。\n"
    "\n只输出一个 JSON 对象,字段如下:\n"
    "  continues_project_id: 字符串。延续已有任务时填其 project_id;确实是新任务才填 \"NEW\"。\n"
    "  new_task_title: 字符串。continues_project_id 为 \"NEW\" 时给一句话任务名(概括这条任务的目标,"
    "不要只抄单个窗口标题),否则空串。\n"
    "  activity_type: 字符串。coding/researching/writing/communication/browsing/terminal/other 之一。\n"
    "  gist: 字符串。一句中文说清这个片段在干嘛,忠于给定字段,不编造具体细节。\n"
    "  confidence: 0到1的小数,你对该判断的把握;凭据不足时给低分。\n"
    "  task_closed: 布尔。若这个片段完成了该任务则 true,否则 false。"
)

_REQUIRED = ("continues_project_id", "new_task_title", "activity_type",
             "gist", "confidence", "task_closed")


def _snippet(seg: Segment) -> str:
    return " / ".join(seg.content)[:CONTENT_SNIPPET]


class QwenUnderstander:
    """Associate via Qwen (OpenAI-compatible). Non-`full` segments are handled
    locally and never enter the request (red line). Any failure falls back to
    the rule path — segments are never lost."""

    def __init__(self, api_key: str, *, model: str = "qwen-plus",
                 base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
                 max_tokens: int = 1024) -> None:
        if OpenAI is None:
            raise RuntimeError("openai SDK not installed; run: pip install openai")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_tokens = max_tokens
        self.state = _TaskState()
        self._rule = RuleUnderstander(self.state)   # shares the task ledger

    def ingest(self, seg: Segment) -> ActivityNote:
        # RED LINE: only full-content segments may leave the machine.
        if seg.capture_policy != "full":
            return self._rule.ingest(seg)
        try:
            return self._cloud(seg)
        except Exception as exc:  # noqa: BLE001 — never lose a segment
            note = self._rule.ingest(seg)
            note.gist = f"[降级 {type(exc).__name__}] {note.gist}"
            note.confidence = min(note.confidence, 0.3)
            return note

    def _payload(self, seg: Segment) -> dict:
        active = self.state.active(seg.start_ms)
        return {
            "new_segment": {
                "app": seg.app, "kind": seg.kind, "title": seg.title,
                "url": seg.url, "mode": seg.mode,
                "dwell_s": round(seg.duration_s), "keys": seg.keys,
                "clicks": seg.clicks, "content": _snippet(seg),
            },
            "active_tasks": [
                {"project_id": t.project_id, "title": t.title,
                 "activity_type": t.activity_type, "recent_trace": t.trace}
                for t in active
            ],
        }

    def _cloud(self, seg: Segment) -> ActivityNote:
        payload = self._payload(seg)
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",
                 "content": "以下是待判断的活动片段与当前任务线(JSON):\n"
                            + json.dumps(payload, ensure_ascii=False)},
            ],
        )
        a = json.loads(resp.choices[0].message.content)
        if not all(k in a for k in _REQUIRED):
            raise ValueError(f"missing fields in model output: {a}")

        pid = str(a["continues_project_id"])
        act = str(a["activity_type"]) or "working"
        if pid != "NEW" and self.state.get(pid):
            task = self.state.get(pid)
        else:
            task = self.state.new(str(a["new_task_title"]), act, seg)
        gist = str(a["gist"]) or seg.title
        task.touch(seg, gist, act)
        return _note(seg, task, gist, act, confidence=float(a["confidence"]))


# --------------------------------------------------------------------------- #
# factory
# --------------------------------------------------------------------------- #
def make_understander(backend: str, *, api_key: str = "", model: str = "qwen-plus",
                      base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
                      ) -> Understander:
    """Pick a backend. 'qwen' needs openai + a key; missing either -> rule
    fallback with a printed notice (segments are never lost)."""
    if backend == "qwen":
        if OpenAI is None:
            print("[understander] openai 未安装,降级 rule 后端 (pip install openai)")
        elif not api_key:
            print("[understander] 未配置 qwen_api_key,降级 rule 后端")
        else:
            return QwenUnderstander(api_key, model=model, base_url=base_url)
    return RuleUnderstander()
