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
        text="今晚，小安在基站旁边发现了一扇很小的月亮门。门上写着：愿意一起做选择的人，才能打开星尘工作台。你想让我先检查蓝色齿轮，还是按下银色按钮？",
        choices=(
            StoryChoice("gear", "检查蓝色齿轮", "gear", ("齿轮", "蓝色齿轮", "检查齿轮")),
            StoryChoice("button", "按下银色按钮", "button", ("按钮", "银色按钮", "按按钮")),
        ),
    ),
    "gear": StoryNode(
        id="gear",
        expression="thinking",
        text="小安轻轻转动蓝色齿轮，屏幕上浮出一张星图。星图缺了一个角，需要找回一颗小小的星尘螺丝。现在有两条路：安静的档案室，或者发光的升降台。你选哪边？",
        choices=(
            StoryChoice("archive", "去档案室", "archive", ("档案室", "安静的档案室")),
            StoryChoice("lift", "去升降台", "lift", ("升降台", "发光的升降台")),
        ),
    ),
    "button": StoryNode(
        id="button",
        expression="surprised",
        text="银色按钮一亮，月亮门发出叮的一声。里面不是房间，而是一条漂浮的小轨道。轨道尽头有两个工具箱：一个写着勇气，一个写着耐心。你想打开哪个？",
        choices=(
            StoryChoice("courage", "打开勇气工具箱", "courage", ("勇气", "勇气工具箱")),
            StoryChoice("patience", "打开耐心工具箱", "patience", ("耐心", "耐心工具箱")),
        ),
    ),
    "archive": StoryNode(
        id="archive",
        expression="caring",
        text="档案室里很安静，所有旧计划都排成一行。小安找到一张便签，上面写着：重要的东西不是最快找到，而是有人陪你一起找。我们要继续慢慢找，还是让小安扫描一下？",
        choices=(
            StoryChoice("slow", "继续慢慢找", "ending_warm", ("慢慢找", "继续找")),
            StoryChoice("scan", "让小安扫描一下", "ending_scan", ("扫描", "扫描一下")),
        ),
    ),
    "lift": StoryNode(
        id="lift",
        expression="happy",
        text="升降台慢慢升起，整个工作台像星空一样亮了起来。小安看到那颗星尘螺丝就在最高处，但平台轻轻晃了一下。你要我伸手拿，还是先稳住平台？",
        choices=(
            StoryChoice("reach", "伸手拿", "ending_bright", ("拿", "伸手拿")),
            StoryChoice("steady", "先稳住平台", "ending_steady", ("稳住", "稳住平台")),
        ),
    ),
    "courage": StoryNode(
        id="courage",
        expression="happy",
        text="勇气工具箱打开了，里面没有工具，只有一束暖暖的光。小安把光别在胸前，说：那我们今天就勇敢一点点。你想直接打开月亮门，还是先叫醒工作台？",
        choices=(
            StoryChoice("open", "直接打开月亮门", "ending_door", ("打开月亮门", "直接打开")),
            StoryChoice("wake", "叫醒工作台", "ending_workbench", ("叫醒", "叫醒工作台")),
        ),
    ),
    "patience": StoryNode(
        id="patience",
        expression="idle",
        text="耐心工具箱里有一个小沙漏。沙子落下的时候，工作台的灯一点一点亮起来。小安说：慢一点也没关系，我们正在靠近答案。你想等沙漏走完，还是轻轻敲门？",
        choices=(
            StoryChoice("wait", "等沙漏走完", "ending_lamp", ("等沙漏", "沙漏")),
            StoryChoice("knock", "轻轻敲门", "ending_knock", ("敲门", "轻轻敲门")),
        ),
    ),
    "ending_warm": StoryNode(
        id="ending_warm",
        expression="caring",
        text="小安陪你慢慢找，最后在一页旧计划下面发现了星尘螺丝。月亮门亮起来，说：认真生活的人，总会被温柔找到。",
    ),
    "ending_scan": StoryNode(
        id="ending_scan",
        expression="thinking",
        text="小安启动扫描，小屏幕上跳出一颗闪闪的小点。星尘螺丝就在桌角。小安说：有时候答案很近，只是需要换一种看法。",
    ),
    "ending_bright": StoryNode(
        id="ending_bright",
        expression="happy",
        text="小安伸手拿到星尘螺丝，工作台一下子亮成小小银河。屏幕写着：选择完成，陪伴继续。今天的小冒险成功啦。",
    ),
    "ending_steady": StoryNode(
        id="ending_steady",
        expression="caring",
        text="小安先稳住平台，再轻轻拿下螺丝。工作台没有晃，月亮门也慢慢打开。小安说：稳稳来，也是一种很厉害的勇敢。",
    ),
    "ending_door": StoryNode(
        id="ending_door",
        expression="surprised",
        text="月亮门被勇气之光推开，里面不是宝藏，而是一盏给认真工作的人准备的小灯。小安把灯递给你：今天辛苦啦。",
    ),
    "ending_workbench": StoryNode(
        id="ending_workbench",
        expression="speaking",
        text="小安叫醒工作台，所有按钮都轻轻回应。工作台说：已经准备好陪你开始下一个任务。小安也亮起表情：我也准备好啦。",
    ),
    "ending_lamp": StoryNode(
        id="ending_lamp",
        expression="idle",
        text="沙漏走完，工作台自己亮了起来。小安小声说：你看，等待不是停下，而是在给答案一点点出现的时间。",
    ),
    "ending_knock": StoryNode(
        id="ending_knock",
        expression="happy",
        text="你轻轻敲门，月亮门也轻轻回应。门后飘出一颗星尘，落在小安掌心。小安说：谢谢你和我一起完成这个故事。",
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
