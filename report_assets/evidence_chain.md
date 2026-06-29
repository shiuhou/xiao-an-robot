# XiaoAn Emotion/Vision Evidence Chain

## 1. 验证目标
证明视觉关怀链路在小样本工程验证集中可运行、可审计，并能区分正常/低质量/疲劳/打哈欠/负面状态的策略行为。

## 2. 为什么不做科研 benchmark
当前数据是 XiaoAn-Care-v1 小样本 scenario validation，不是大规模训练集或科研 benchmark。因此这里不声明模型 accuracy、F1 或泛化能力。

## 3. XiaoAn-Care-v1 场景验证集概况
见 `report_assets/tables/table_dataset_coverage.md` 和 `report_assets/tables/table_expected_behavior.md`。这些表描述场景覆盖和工程验收规则。

## 4. Policy comparison 结论
见 `report_assets/tables/table_policy_metrics.md`。三种策略用于比较阈值、cooldown、quality gate 的行为差异。

## 5. Quality gate stress test 结论
见 `report_assets/tables/table_quality_gate_stress.md`。低质量强信号 stress test 是 policy stress test，不是真实模型输出；目标是证明 quality gate 能抑制低质量误触发。

## 6. Clip timeline 结论
见 `report_assets/tables/table_clip_trigger_summary.md` 和 timeline 图。clip 级别验证强调主动关怀是随时间变化的策略过程，不是单帧阈值截图。

## 7. E2E smoke 结论
fake/mock smoke 共 5 个场景，pass=5，fail=0。真实 OpenClaw 和真实机器人均未使用。

## 8. VLM 契约：只解释，不覆盖 CV 主判据
VLM 结果只允许作为嵌套解释补充。顶层 `emotion_tag/confidence/fatigue_score` 仍来自 CV/OpenFace/mock primary sample。smoke 中 `vlm_override_count=0`。

## 9. 当前限制
这些结果主要基于 label-derived surrogate sample 和 fake/mock smoke，不代表真实模型准确率，也不是实机稳定性证明。真实 camera/OpenFace/OpenClaw/robot 仍需独立 smoke。

## 10. 可放进报告的推荐表格和图
- `report_assets/tables/table_dataset_coverage.md`
- `report_assets/tables/table_policy_metrics.md`
- `report_assets/tables/table_quality_gate_stress.md`
- `report_assets/tables/table_clip_trigger_summary.md`
- `report_assets/tables/table_e2e_smoke_checklist.md`
- `report_assets/figures/fig_policy_false_triggers.png`
- `report_assets/figures/fig_clip_state_timeline.png`
- `report_assets/figures/fig_e2e_event_flow.png`
