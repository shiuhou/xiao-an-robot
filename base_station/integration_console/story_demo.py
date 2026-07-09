"""Deterministic interactive story demo for the Integration Console."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


STORY_SCHEMA_VERSION = "xiaoan.fast_demo_story_state.v1"
STORY_ID = "moon_door"
STORY_TITLE = "月亮门和小安的星尘工作台"
START_NODE_ID = "intro"
STORY_START_KEYWORDS = ("故事", "讲故事", "讲个故事", "听故事", "开始故事", "故事模式")


@dataclass(frozen=True)
class StoryChoice:
    id: str
    label: str
    next_node: str
    aliases: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "next_node": self.next_node,
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True)
class StoryNode:
    id: str
    text: str
    expression: str
    choices: tuple[StoryChoice, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "expression": self.expression,
            "choices": [choice.as_dict() for choice in self.choices],
            "is_terminal": not self.choices,
        }


STORY_NODES: dict[str, StoryNode] = {
    "intro": StoryNode(
        id="intro",
        expression="thinking",
        text="小安发现月亮门。选齿轮，还是按钮？",
        choices=(
            StoryChoice("gear", "检查蓝色齿轮", "gear", ("齿轮", "蓝色齿轮", "检查齿轮")),
            StoryChoice("button", "按下银色按钮", "button", ("按钮", "银色按钮", "按按钮")),
        ),
    ),
    "gear": StoryNode(
        id="gear",
        expression="thinking",
        text="齿轮亮起星图。去档案室，还是升降台？",
        choices=(
            StoryChoice("archive", "去档案室", "archive", ("档案室", "安静的档案室")),
            StoryChoice("lift", "去升降台", "lift", ("升降台", "发光的升降台")),
        ),
    ),
    "button": StoryNode(
        id="button",
        expression="surprised",
        text="按钮打开轨道。选勇气，还是耐心？",
        choices=(
            StoryChoice("courage", "打开勇气工具箱", "courage", ("勇气", "勇气工具箱")),
            StoryChoice("patience", "打开耐心工具箱", "patience", ("耐心", "耐心工具箱")),
        ),
    ),
    "archive": StoryNode(
        id="archive",
        expression="caring",
        text="档案室有便签。慢慢找，还是扫描？",
        choices=(
            StoryChoice("slow", "继续慢慢找", "ending_warm", ("慢慢找", "继续找")),
            StoryChoice("scan", "让小安扫描一下", "ending_scan", ("扫描", "扫描一下")),
        ),
    ),
    "lift": StoryNode(
        id="lift",
        expression="happy",
        text="升降台升起。伸手拿，还是稳住平台？",
        choices=(
            StoryChoice("reach", "伸手拿", "ending_bright", ("拿", "伸手拿")),
            StoryChoice("steady", "先稳住平台", "ending_steady", ("稳住", "稳住平台")),
        ),
    ),
    "courage": StoryNode(
        id="courage",
        expression="happy",
        text="勇气箱发光。打开月亮门，还是叫醒工作台？",
        choices=(
            StoryChoice("open", "直接打开月亮门", "ending_door", ("打开月亮门", "直接打开")),
            StoryChoice("wake", "叫醒工作台", "ending_workbench", ("叫醒", "叫醒工作台")),
        ),
    ),
    "patience": StoryNode(
        id="patience",
        expression="idle",
        text="耐心箱有沙漏。等沙漏，还是敲门？",
        choices=(
            StoryChoice("wait", "等沙漏走完", "ending_lamp", ("等沙漏", "沙漏")),
            StoryChoice("knock", "轻轻敲门", "ending_knock", ("敲门", "轻轻敲门")),
        ),
    ),
    "ending_warm": StoryNode(
        id="ending_warm",
        expression="caring",
        text="你们找到了螺丝。月亮门温柔地亮了。",
    ),
    "ending_scan": StoryNode(
        id="ending_scan",
        expression="thinking",
        text="扫描发现螺丝就在桌角。答案其实很近。",
    ),
    "ending_bright": StoryNode(
        id="ending_bright",
        expression="happy",
        text="小安拿到螺丝。工作台亮成银河。",
    ),
    "ending_steady": StoryNode(
        id="ending_steady",
        expression="caring",
        text="小安稳住平台。稳稳来，也很勇敢。",
    ),
    "ending_door": StoryNode(
        id="ending_door",
        expression="surprised",
        text="月亮门打开。小安递给你一盏小灯。",
    ),
    "ending_workbench": StoryNode(
        id="ending_workbench",
        expression="speaking",
        text="工作台醒了。小安说，我准备好啦。",
    ),
    "ending_lamp": StoryNode(
        id="ending_lamp",
        expression="idle",
        text="沙漏走完，工作台亮了。等待也有力量。",
    ),
    "ending_knock": StoryNode(
        id="ending_knock",
        expression="happy",
        text="星尘落在小安掌心。故事完成啦。",
    ),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_story_node(node_id: str | None) -> StoryNode:
    return STORY_NODES.get(str(node_id or ""), STORY_NODES[START_NODE_ID])


def build_story_state(*, node_id: str = START_NODE_ID, active: bool = True) -> dict[str, Any]:
    node = get_story_node(node_id)
    timestamp = now_iso()
    return {
        "schema_version": STORY_SCHEMA_VERSION,
        "story_id": STORY_ID,
        "title": STORY_TITLE,
        "active": bool(active and node.choices),
        "status": "waiting_choice" if node.choices and active else "completed",
        "current_node": node.id,
        "last_node": node.as_dict(),
        "history": [node.id],
        "updated_at": timestamp,
        "started_at": timestamp,
    }


def story_state_summary(state: dict[str, Any] | None) -> dict[str, Any]:
    raw = state if isinstance(state, dict) else {}
    node = get_story_node(raw.get("current_node"))
    history = raw.get("history") if isinstance(raw.get("history"), list) else []
    active = bool(raw.get("active", False))
    return {
        "ok": True,
        "schema_version": STORY_SCHEMA_VERSION,
        "story_id": STORY_ID,
        "title": STORY_TITLE,
        "active": active,
        "status": str(raw.get("status") or ("waiting_choice" if active else "idle")),
        "current_node": node.as_dict(),
        "history": history,
        "updated_at": raw.get("updated_at"),
        "started_at": raw.get("started_at"),
        "last_execution": raw.get("last_execution") if isinstance(raw.get("last_execution"), dict) else {},
    }


def resolve_story_choice(state: dict[str, Any], choice_text: str) -> StoryChoice | None:
    node = get_story_node(state.get("current_node"))
    normalized = _normalize(choice_text)
    if not normalized:
        return None
    for choice in node.choices:
        candidates = (choice.id, choice.label, *choice.aliases)
        if any(_normalize(candidate) in normalized or normalized in _normalize(candidate) for candidate in candidates):
            return choice
    return None


def is_story_start_request(text: str) -> bool:
    normalized = _normalize(text)
    return bool(normalized and any(_normalize(keyword) in normalized for keyword in STORY_START_KEYWORDS))


def advance_story_state(state: dict[str, Any], choice: StoryChoice) -> dict[str, Any]:
    node = get_story_node(choice.next_node)
    history = state.get("history") if isinstance(state.get("history"), list) else []
    updated = {
        **state,
        "active": bool(node.choices),
        "status": "waiting_choice" if node.choices else "completed",
        "current_node": node.id,
        "last_node": node.as_dict(),
        "last_choice": choice.as_dict(),
        "history": [*history, choice.id, node.id],
        "updated_at": now_iso(),
    }
    return updated


def stop_story_state(state: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = state if isinstance(state, dict) else {}
    return {
        **raw,
        "schema_version": STORY_SCHEMA_VERSION,
        "story_id": STORY_ID,
        "title": STORY_TITLE,
        "active": False,
        "status": "stopped",
        "updated_at": now_iso(),
    }


def iter_story_demo_tts_texts() -> list[dict[str, str]]:
    return [
        {
            "link": "story",
            "intent": node.id,
            "variant": "0",
            "text": node.text,
        }
        for node in STORY_NODES.values()
    ]


def _normalize(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "").replace("，", "").replace("。", "")
