---
name: xiao-an-session
description: 小安机器人仓库 Codex 开工/收工/多 Agent 对齐协议。开始改代码或文档前 MUST 使用；任务结束 MUST 收工写回 Git。与 Cursor 共用 docs/agents/01_session_protocol.md。触发词：开工、收工、对齐进度、xiao-an session、session protocol、整合 Agent、按协议执行。
---

# xiao-an-session — Codex 会话协议

完整方案：**必须先读** `docs/agents/01_session_protocol.md`（Canonical，本文是执行摘要）。

优先级：`AGENTS.md` > 本 skill > 默认行为。

---

## 何时触发

| 用户说 | 动作 |
|--------|------|
| 开工 / 按协议开工 / xiao-an session 开工 | §开工 |
| 收工 / 按协议收工 | §收工 |
| 整合 Agent / 整合仓库状态 | 读 01 §9 |
| 任务里含「按 xiao-an-session」 | 先 §开工 再执行任务 |

若用户同时说 **team-lark** → 先执行 `team-lark` skill 第 0 步（档位 B），再 §开工。

---

## 开工（Open Session）

### MUST 读取（按顺序）

1. `docs/agents/README.md`
2. `docs/agents/00_snapshot.md`
3. 按 README 路由表加读 1–2 个文件（02/03/04/05/06/09）
4. 若用户给了 Queue ID → `docs/agents/08_priority_queue.yaml`

### MUST 执行

```powershell
git status
```

若有未预期 dirty 文件，**先报告用户**，勿 revert 他人改动。

### 档位（用户未说明则默认 A）

| 档位 | 额外动作 |
|------|----------|
| **A** Git | 无（默认） |
| **B** Git+飞书 | 调用 `team-lark` skill，输出今日简报 |
| **C** Git+mem | `claude-mem-mem-search` 查任务相关踩坑 |

### MUST 回复（开工对齐块）

```markdown
## 开工对齐
- 工具：Codex
- 档位：A / A+B / A+B+C
- 当前目标：…
- 修改范围：…
- 成功标准：…
- 阻塞（🔴）：…
- Queue：Txx / 无
```

### 禁止

- 跳过 README + snapshot 直接改代码
- 读 `docs/archive/`（除非用户指定）
- 未告知用户就改 `shared/` 或 `docs/protocol.md`
- 同一 `robot/firmware` workspace 并行多个 `pio run`

---

## 收工（Close Session）

### MUST 执行

1. 跑任务相关验证命令，报告精确 exit code / 关键日志
2. **always** → `00_snapshot.md`「近期重要变更」追加一行
3. 若改了代码 → 更新对应 `02/03/04` registry 行（状态+日期+命令）
4. 若涉及测试/env → 更新 `05_test_matrix.md`
5. 若做了 queue 任务 → 更新 `08_priority_queue_results.json`
6. 档位 B → 飞书任务「待验收」+ 交付说明
7. 档位 C → 值得记住的坑写入 claude-mem
8. `git diff --check`

### MUST 回复（收工摘要块）

使用 `01_session_protocol.md` §7.2 模板，字段齐全。

---

## 真相优先级

```
live source / platformio.ini > AGENTS.md > 最新 project_status > 00_snapshot > registry > 旧文档/archive
```

---

## Cursor 用户

本 skill 为 Codex 设计。若用户在 Cursor 中引用本文，同样读 `01_session_protocol.md` 执行；Cursor 无 skill 机制时，用户需手动 @ `docs/agents/01_session_protocol.md` 或 `.cursor/rules/agent-session.mdc`。

---

## 整合 Agent

用户说「整合」→ 读 `01_session_protocol.md` §9，跑 `python tools/generate_agent_registry.py`，产出 dated status + 不一致清单。
