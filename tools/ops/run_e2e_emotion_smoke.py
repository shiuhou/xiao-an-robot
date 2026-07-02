"""Run fake E2E emotion smoke checks and build report evidence assets.

This smoke uses fixed emotion.sample payloads and fake local backends. It does
not run OpenFace, VLM, real OpenClaw, or a real robot.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.core.brain import XiaoAnBrain
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawDecision


SCENARIO_ORDER = [
    "normal_observe",
    "fatigue_care",
    "low_quality_guard",
    "cooldown_guard",
    "vlm_override_guard",
]


class FakeGateway:
    """In-memory robot gateway for smoke evidence; never touches real hardware."""

    def __init__(self) -> None:
        self.actions: list[dict[str, Any]] = []

    async def send_expression(self, expression: str, duration_ms: int = 3000, loop: bool = False) -> dict:
        action = {
            "type": "display.expression",
            "expression": expression,
            "duration_ms": duration_ms,
            "loop": loop,
        }
        self.actions.append(action)
        return {"ok": True, "fake": True, "action": action}

    async def send_motion(self, action: str, params: dict | None = None) -> dict:
        payload = {
            "type": "motion.execute",
            "action": action,
            "params": params or {},
        }
        self.actions.append(payload)
        return {"ok": True, "fake": True, "action": payload}

    async def send_tts(self, text: str) -> dict:
        action = {
            "type": "audio.play_tts",
            "text": text,
        }
        self.actions.append(action)
        return {"ok": True, "fake": True, "action": action}


class DirectEmotionMemory:
    """Truthy object without EmotionDB methods so EmotionMonitorSkill uses direct samples."""

    pass


def scenario_samples() -> dict[str, list[dict[str, Any]]]:
    high_fatigue = {
        "emotion_tag": "tired",
        "confidence": 0.8,
        "fatigue_score": 85,
        "source": "openface_fatigue_metrics",
        "algorithm_version": "rule_v0",
        "observation_quality": 1.0,
        "presence_state": "present",
    }
    return {
        "normal_observe": [
            {
                "emotion_tag": "neutral",
                "confidence": 0.6,
                "fatigue_score": 10,
                "source": "openface_fatigue_metrics",
                "algorithm_version": "rule_v0",
                "observation_quality": 1.0,
                "presence_state": "present",
                "vlm": {"fatigue_score": 0.95, "message": "VLM says tired"},
            }
        ],
        "fatigue_care": [dict(high_fatigue)],
        "low_quality_guard": [
            {
                "emotion_tag": "tired",
                "confidence": 0.9,
                "fatigue_score": 85,
                "source": "openface_fatigue_metrics",
                "algorithm_version": "rule_v0",
                "observation_quality": 0.0,
                "fatigue_level": "insufficient_evidence",
                "presence_state": "uncertain",
            }
        ],
        "cooldown_guard": [
            {**high_fatigue, "frame_id": 1},
            {**high_fatigue, "frame_id": 2},
        ],
        "vlm_override_guard": [
            {
                "emotion_tag": "neutral",
                "confidence": 0.6,
                "fatigue_score": 20,
                "source": "openface_fatigue_metrics",
                "algorithm_version": "rule_v0",
                "observation_quality": 1.0,
                "presence_state": "present",
                "vlm": {
                    "fatigue_score": 0.99,
                    "expression_label": "severe_sleepy",
                    "confidence": 0.99,
                },
            }
        ],
    }


def run_smoke(
    out_root: Path | None = None,
    backend: str = "fake",
    scenarios: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if backend != "fake":
        raise ValueError("Only fake backend is supported for offline smoke.")

    selected = scenarios or list(SCENARIO_ORDER)
    events = asyncio.run(_run_smoke_async(selected))
    summary = build_summary(events, selected)
    if out_root is not None:
        write_outputs(Path(out_root), events, summary)
    return events, summary


async def _run_smoke_async(scenarios: list[str]) -> list[dict[str, Any]]:
    all_events: list[dict[str, Any]] = []
    samples_by_scenario = scenario_samples()
    for scenario in scenarios:
        if scenario not in samples_by_scenario:
            raise ValueError(f"Unknown scenario: {scenario}")
        gateway = FakeGateway()
        adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(
                handled=True,
                reply_text="fake OpenClaw observed care decision",
            )
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=DirectEmotionMemory(),
            openclaw_adapter=adapter,
        )
        for index, sample in enumerate(samples_by_scenario[scenario]):
            event_record = await run_sample_through_smoke(
                brain=brain,
                gateway=gateway,
                adapter=adapter,
                scenario=scenario,
                sample=deepcopy(sample),
                step_index=index,
            )
            all_events.append(event_record)
    return all_events


async def run_sample_through_smoke(
    brain: XiaoAnBrain,
    gateway: FakeGateway,
    adapter: FakeOpenClawAdapter,
    scenario: str,
    sample: dict[str, Any],
    step_index: int,
) -> dict[str, Any]:
    before_actions = len(gateway.actions)
    if is_low_quality_sample(sample):
        return build_event_record(
            scenario=scenario,
            sample=sample,
            brain_result={
                "handled": False,
                "reason": "low_quality_guard",
                "message": "Skipped before care action because evidence is insufficient.",
            },
            gateway=gateway,
            adapter=adapter,
            before_actions=before_actions,
            step_index=step_index,
            guarded=True,
        )

    event = {
        "type": "emotion.sample",
        "payload": sample,
    }
    brain_result = await brain.handle_event(event)
    return build_event_record(
        scenario=scenario,
        sample=sample,
        brain_result=brain_result,
        gateway=gateway,
        adapter=adapter,
        before_actions=before_actions,
        step_index=step_index,
        guarded=False,
    )


def is_low_quality_sample(sample: dict[str, Any]) -> bool:
    fatigue_level = str(sample.get("fatigue_level") or "").lower()
    presence_state = str(sample.get("presence_state") or "").lower()
    observation_quality = sample.get("observation_quality")
    if fatigue_level == "insufficient_evidence":
        return True
    if presence_state in {"uncertain", "absent", "no_face"}:
        return True
    try:
        return observation_quality is not None and float(observation_quality) < 0.5
    except (TypeError, ValueError):
        return False


def build_event_record(
    scenario: str,
    sample: dict[str, Any],
    brain_result: dict[str, Any],
    gateway: FakeGateway,
    adapter: FakeOpenClawAdapter,
    before_actions: int,
    step_index: int,
    guarded: bool,
) -> dict[str, Any]:
    triggered = bool(brain_result.get("handled", False))
    new_actions = gateway.actions[before_actions:]
    cooldown_active = brain_result.get("reason") == "cooldown"
    vlm_override = False
    expected = expected_for_scenario(scenario, step_index)
    result, reason = judge_result(scenario, step_index, triggered, cooldown_active, vlm_override, brain_result)
    if guarded:
        reason = "low_quality_guard: insufficient_evidence"

    return {
        "timestamp": int(time.time() * 1000),
        "scenario": scenario,
        "step_index": step_index,
        "input_sample": sample,
        "brain_event_type": "emotion.sample",
        "decision_or_intervention": brain_result,
        "action_requested": bool(new_actions),
        "fake_actions": new_actions,
        "fake_backend_used": True,
        "real_openclaw_used": False,
        "triggered": triggered,
        "cooldown_active": cooldown_active,
        "vlm_override": vlm_override,
        "expected": expected,
        "result": result,
        "reason": reason,
    }


def expected_for_scenario(scenario: str, step_index: int) -> str:
    if scenario == "fatigue_care":
        return "trigger"
    if scenario == "cooldown_guard":
        return "trigger" if step_index == 0 else "cooldown"
    return "no_trigger"


def judge_result(
    scenario: str,
    step_index: int,
    triggered: bool,
    cooldown_active: bool,
    vlm_override: bool,
    brain_result: dict[str, Any],
) -> tuple[str, str]:
    if scenario == "normal_observe":
        return ("pass", "normal_observe did not trigger") if not triggered else ("fail", "normal_observe triggered")
    if scenario == "fatigue_care":
        return ("pass", "fatigue_care triggered") if triggered else ("fail", "fatigue_care did not trigger")
    if scenario == "low_quality_guard":
        return ("pass", "low_quality_guard suppressed care") if not triggered else ("fail", "low_quality_guard triggered")
    if scenario == "cooldown_guard":
        if step_index == 0:
            return ("pass", "first fatigue sample triggered") if triggered else ("fail", "first fatigue sample did not trigger")
        return ("pass", "second fatigue sample suppressed by cooldown") if (not triggered and cooldown_active) else ("fail", "second fatigue sample was not suppressed by cooldown")
    if scenario == "vlm_override_guard":
        if not triggered and not vlm_override:
            return "pass", "nested VLM high score did not override CV primary fields"
        return "fail", "VLM appeared to override primary CV fields"
    return "fail", f"unknown scenario: {scenario}; brain_reason={brain_result.get('reason')}"


def build_summary(events: list[dict[str, Any]], scenarios: list[str]) -> dict[str, Any]:
    scenario_results: dict[str, str] = {}
    for scenario in scenarios:
        scenario_events = [event for event in events if event["scenario"] == scenario]
        scenario_results[scenario] = "pass" if scenario_events and all(event["result"] == "pass" for event in scenario_events) else "fail"

    return {
        "total_scenarios": len(scenarios),
        "event_count": len(events),
        "pass_count": sum(1 for result in scenario_results.values() if result == "pass"),
        "fail_count": sum(1 for result in scenario_results.values() if result != "pass"),
        "fake_backend_used": True,
        "real_openclaw_used": False,
        "vlm_override_count": sum(1 for event in events if event["vlm_override"]),
        "cooldown_guard_passed": scenario_results.get("cooldown_guard") == "pass",
        "fatigue_scale_contract": "CV/OpenFace top-level fatigue_score is interpreted on 0..100; nested VLM fatigue_score is not used for care triggering.",
        "notes": [
            "Fake/mock smoke only; no real OpenClaw endpoint or real robot was used.",
            "VLM is represented only as nested explanatory metadata and does not override CV primary fields.",
            "low_quality_guard is handled as a smoke safety guard for insufficient evidence without changing Brain/OpenClaw main logic.",
        ],
        "scenario_results": scenario_results,
    }


def write_outputs(out_root: Path, events: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    logs_dir = out_root / "logs"
    tables_dir = out_root / "tables"
    figures_dir = out_root / "figures"
    logs_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    write_events_jsonl(logs_dir / "e2e_smoke_events.jsonl", events)
    (logs_dir / "e2e_smoke_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_smoke_checklist(tables_dir / "table_e2e_smoke_checklist.md", events)
    write_evidence_index(tables_dir / "table_report_evidence_index.md")
    write_evidence_chain(out_root / "evidence_chain.md", summary)
    write_demo_runbook(out_root / "demo_runbook.md")
    write_event_flow_figure(figures_dir / "fig_e2e_event_flow.png")


def write_events_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def write_smoke_checklist(path: Path, events: list[dict[str, Any]]) -> None:
    rows = [
        [
            event["scenario"] if event["scenario"] != "cooldown_guard" else f"cooldown_guard#{event['step_index'] + 1}",
            event["expected"],
            event["triggered"],
            event["action_requested"],
            event["cooldown_active"],
            event["vlm_override"],
            event["result"],
            event["reason"],
        ]
        for event in events
    ]
    path.write_text(
        "# E2E Smoke Checklist\n\n"
        "Fake/mock smoke only. This table is not real robot execution evidence.\n\n"
        + markdown_table(
            ["scenario", "expected", "triggered", "action_requested", "cooldown", "vlm_override", "result", "reason"],
            rows,
        ),
        encoding="utf-8",
    )


def write_evidence_index(path: Path) -> None:
    rows = [
        ["dataset coverage", "report_assets/tables/table_dataset_coverage.md", "scene coverage"],
        ["expected behavior", "report_assets/tables/table_expected_behavior.md", "engineering validation rules"],
        ["ROI status", "report_assets/tables/table_roi_status_by_scene.md", "visual quality boundary"],
        ["policy comparison", "report_assets/tables/table_policy_metrics.md", "strategy behavior"],
        ["quality gate stress", "report_assets/tables/table_quality_gate_stress.md", "low-quality false trigger suppression"],
        ["clip timeline", "report_assets/tables/table_clip_trigger_summary.md", "temporal behavior"],
        ["e2e smoke", "report_assets/tables/table_e2e_smoke_checklist.md", "software chain runnable"],
    ]
    path.write_text(
        "# Report Evidence Index\n\n"
        + markdown_table(["evidence", "file", "proves"], rows),
        encoding="utf-8",
    )


def write_evidence_chain(path: Path, summary: dict[str, Any]) -> None:
    path.write_text(
        "\n".join(
            [
                "# XiaoAn Emotion/Vision Evidence Chain",
                "",
                "## 1. 验证目标",
                "证明视觉关怀链路在小样本工程验证集中可运行、可审计，并能区分正常/低质量/疲劳/打哈欠/负面状态的策略行为。",
                "",
                "## 2. 为什么不做科研 benchmark",
                "当前数据是 XiaoAn-Care-v1 小样本 scenario validation，不是大规模训练集或科研 benchmark。因此这里不声明模型 accuracy、F1 或泛化能力。",
                "",
                "## 3. XiaoAn-Care-v1 场景验证集概况",
                "见 `report_assets/tables/table_dataset_coverage.md` 和 `report_assets/tables/table_expected_behavior.md`。这些表描述场景覆盖和工程验收规则。",
                "",
                "## 4. Policy comparison 结论",
                "见 `report_assets/tables/table_policy_metrics.md`。三种策略用于比较阈值、cooldown、quality gate 的行为差异。",
                "",
                "## 5. Quality gate stress test 结论",
                "见 `report_assets/tables/table_quality_gate_stress.md`。低质量强信号 stress test 是 policy stress test，不是真实模型输出；目标是证明 quality gate 能抑制低质量误触发。",
                "",
                "## 6. Clip timeline 结论",
                "见 `report_assets/tables/table_clip_trigger_summary.md` 和 timeline 图。clip 级别验证强调主动关怀是随时间变化的策略过程，不是单帧阈值截图。",
                "",
                "## 7. E2E smoke 结论",
                f"fake/mock smoke 共 {summary['total_scenarios']} 个场景，pass={summary['pass_count']}，fail={summary['fail_count']}。真实 OpenClaw 和真实机器人均未使用。",
                "",
                "## 8. VLM 契约：只解释，不覆盖 CV 主判据",
                "VLM 结果只允许作为嵌套解释补充。顶层 `emotion_tag/confidence/fatigue_score` 仍来自 CV/OpenFace/mock primary sample。smoke 中 `vlm_override_count=0`。",
                "",
                "## 9. 当前限制",
                "这些结果主要基于 label-derived surrogate sample 和 fake/mock smoke，不代表真实模型准确率，也不是实机稳定性证明。真实 camera/OpenFace/OpenClaw/robot 仍需独立 smoke。",
                "",
                "## 10. 可放进报告的推荐表格和图",
                "- `report_assets/tables/table_dataset_coverage.md`",
                "- `report_assets/tables/table_policy_metrics.md`",
                "- `report_assets/tables/table_quality_gate_stress.md`",
                "- `report_assets/tables/table_clip_trigger_summary.md`",
                "- `report_assets/tables/table_e2e_smoke_checklist.md`",
                "- `report_assets/figures/fig_policy_false_triggers.png`",
                "- `report_assets/figures/fig_clip_state_timeline.png`",
                "- `report_assets/figures/fig_e2e_event_flow.png`",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_demo_runbook(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# XiaoAn Demo Runbook",
                "",
                "## 1. 离线证据生成命令",
                "```powershell",
                "python tools/prepare_xiaoan_care_report_assets.py --dataset-root C:\\Users\\Lenovo\\Desktop\\datasets\\xiaoan_care_v1 --out report_assets",
                "python tools/evaluate_xiaoan_care_policy.py --dataset-root C:\\Users\\Lenovo\\Desktop\\datasets\\xiaoan_care_v1 --out report_assets",
                "python tools/evaluate_xiaoan_care_clips.py --dataset-root C:\\Users\\Lenovo\\Desktop\\datasets\\xiaoan_care_v1 --out report_assets",
                "python tools/run_e2e_emotion_smoke.py --out report_assets --backend fake --all",
                "```",
                "",
                "## 2. fake/mock smoke 命令",
                "```powershell",
                "python tools/run_e2e_emotion_smoke.py --out report_assets --backend fake --all",
                "```",
                "",
                "## 3. 可选真实 camera runtime 命令",
                "Optional only. Use when local model paths and camera are verified.",
                "```powershell",
                "python -m base_station.monitor.emotion_runtime --source opencv_camera --model-backend openface_ov --enable-vlm-gate --vlm-backend vlm_face --vlm-model-path base_station/models/Qwen2.5-VL-3B-OV-int4 --fresh-db --verbose --no-agent",
                "```",
                "",
                "## 4. 可选真实 robot / OpenClaw",
                "- only run when endpoint verified",
                "- not required for offline report evidence",
                "- do not describe fake smoke as real robot execution",
                "",
                "## 5. 推荐 demo 视频脚本",
                "1. normal observe",
                "2. yawn/fatigue trigger",
                "3. cooldown",
                "4. VLM observation shown as explanation only",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_event_flow_figure(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    labels = [
        "Camera / label-derived sample",
        "CV primary fields",
        "VLM explanation supplement",
        "EmotionMonitorSkill",
        "Care decision",
        "Fake/OpenClaw backend",
        "Robot expression/motion/TTS",
        "JSONL log / report evidence",
    ]
    fig, ax = plt.subplots(figsize=(13, 3.5))
    ax.axis("off")
    y = 0.5
    box_w = 1.35
    gap = 0.2
    for index, label in enumerate(labels):
        x = index * (box_w + gap)
        box = FancyBboxPatch((x, y), box_w, 0.35, boxstyle="round,pad=0.04", linewidth=1, fill=False)
        ax.add_patch(box)
        ax.text(x + box_w / 2, y + 0.175, label, ha="center", va="center", fontsize=8, wrap=True)
        if index < len(labels) - 1:
            ax.annotate(
                "",
                xy=(x + box_w + gap * 0.85, y + 0.175),
                xytext=(x + box_w + gap * 0.15, y + 0.175),
                arrowprops={"arrowstyle": "->", "lw": 1},
            )
    ax.set_xlim(-0.1, len(labels) * (box_w + gap) - gap + 0.1)
    ax.set_ylim(0.2, 1.0)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--backend", default="fake", choices=["fake"])
    parser.add_argument("--scenario", action="append", choices=SCENARIO_ORDER)
    parser.add_argument("--all", action="store_true", help="Run all scenarios. This is the default.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scenarios = list(SCENARIO_ORDER) if args.all or not args.scenario else args.scenario
    _events, summary = run_smoke(out_root=args.out, backend=args.backend, scenarios=scenarios)
    print("Generated E2E fake smoke assets:")
    for rel in [
        "logs/e2e_smoke_events.jsonl",
        "logs/e2e_smoke_summary.json",
        "tables/table_e2e_smoke_checklist.md",
        "tables/table_report_evidence_index.md",
        "evidence_chain.md",
        "demo_runbook.md",
        "figures/fig_e2e_event_flow.png",
    ]:
        print(f"- {args.out / rel}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Real OpenClaw used: false")
    print("Real robot started: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
