# Agent 协作方案 — 开工 / 收工 / 多工具对齐

> **Canonical 文档（唯一流程真相）。** Codex 为主力；Cursor 为辅，仅在用户指定时按本文同一套流程执行。
> 最后更新：2026-06-26

---

## 1. 要解决什么问题

本仓库文件多、格式杂（固件、Python、MD、YAML、硬件文档）。若 Agent 不强制「先对齐再动手」，会出现：

- 不主动读 `docs/agents/`，改错目录或用过期文档
- 多个 Agent / 多次会话重复踩坑
- 注册表、快照、源码三方不一致
- 部分 MD 长期不更新，被误当真相

**目标不是让 Agent 扫描全库**，而是用 **少量强制入口 + Git 写回 + 可选飞书/claude-mem**，把任意 Codex（或 Cursor）会话接到同一条进度线上。

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **Git 为进度总线** | 进度、任务、变更写进仓库内 MD/YAML/JSON，不靠聊天历史 |
| **一份流程文档** | 本文 + `AGENTS.md` + `docs/agents/README.md`；工具侧只「指向」不复制 |
| **Codex 为中心** | 默认用 Codex + 项目 Skill `xiao-an-session`；Cursor 按需手动触发 |
| **最小必读** | 开工读 2–4 个文件，按任务类型加读 registry |
| **收工必写回** | registry / test_matrix / snapshot / queue results 四选一 이상，视任务而定 |
| **真相有优先级** | 见 §3.3；禁止用 `docs/archive/` 或旧 dated status 当唯一依据 |

---

## 3. 三层分工（全库统一）

### 3.1 架构图

```
                    ┌─────────────────────────────┐
                    │  Git 仓库 — 流程与进度真相   │
                    │  AGENTS.md                  │
                    │  docs/agents/*              │
                    └──────────────┬──────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
   Codex（主力）            Cursor（按需）           飞书 Base（可选）
   AGENTS.md               用户说「按 01 开工」      team-lark skill
   xiao-an-session skill   .cursor/rules 薄适配      多人/多窗口并行
   claude-mem（可选）       同一套 01 文档
```

### 3.2 文档层级（不要混用）

| 层级 | 路径 | 粒度 | 谁维护 | Agent 怎么用 |
|------|------|------|--------|--------------|
| **L0 契约** | `AGENTS.md`, `docs/protocol.md`, `shared/protocol/*` | 仓库边界、env 名、协议字段 | 人工共识 | 改边界/协议前必读 |
| **L1 路由+进度** | `docs/agents/README.md`, `00_snapshot.md`, 本文 | 当前目标、近期变更、开工收工 | **每个 Agent 收工更新 snapshot** | **每次开工必读** |
| **L2 注册表** | `02_*` ~ `05_*`, `06_integration_phases`, `09_*` | 文件 + 函数 + 状态 + 验证命令 | 改代码时同步一行 | 按任务类型选读 |
| **L3 源码** | `robot/firmware/src/*`, `robot/mergetesting/src/*`, `base_station/*` | 逐行真相 | Git | 动手前读相关文件，不要复制进 MD |
| **L4 任务队列** | `08_priority_queue.yaml`, `08_priority_queue_results.json` | 串行任务、依赖、结果 | Agent 跑 queue 时更新 | 联调/构建链任务用 |
| **L5 自动生成** | `docs/agents/_generated/file_inventory.md` | 文件清单（无状态） | `python tools/generate_agent_registry.py` | 整合 Agent / 文档卫生用 |

### 3.3 真相优先级（冲突时）

```
live source / platformio.ini
  > AGENTS.md
  > 最新 docs/project_status_YYYY-MM-DD.md
  > docs/agents/00_snapshot.md
  > docs/agents/02~05 registry
  > 旧 project_status / docs/archive/
```

### 3.4 状态图例（全库统一）

| 标记 | 含义 |
|------|------|
| ✅ | 已实现且在目标 env 编译/测试通过 |
| 🟡 | 部分实现或仅 isolated env 可用 |
| ⬜ | stub / TODO |
| 🔴 | 已知阻塞 |
| 🧪 | 仅单元测试/mock，未接硬件 |

---

## 4. 三档协作（可同时启用）

三档 **叠加** 使用：A 为底，B 在并行多 Agent 时开，C 作 Codex 经验补充。

### 档位 A — 仅 Git（默认，单人 + Codex 为主）

**共享状态文件：**

| 文件 | 用途 |
|------|------|
| `00_snapshot.md` | 进度总表 + 「近期重要变更」 |
| `02~05 registry` | 模块级状态 |
| `05_test_matrix.md` | env/测试 P·H·F |
| `08_priority_queue.yaml` | 待办任务定义 |
| `08_priority_queue_results.json` | 任务执行结果 |
| `docs/project_status_YYYY-MM-DD.md` | 大联调/里程碑快照 |

**会话切换（Codex → 新 Codex 窗口）：**

```powershell
git status
git pull   # 若有多机协作
# 读 00_snapshot.md 末尾「近期重要变更」
# 读 08_priority_queue_results.json 看 queue 跑到哪
```

### 档位 B — Git + 飞书（多窗口 / 要给人看进度）

使用项目 Skill：`.agents/skills/team-lark/SKILL.md`

| 时机 | 动作 |
|------|------|
| **开工** | 用户说「team-lark」或「对齐进度」→ Agent 读飞书任务表 + 输出今日简报 |
| **认领** | 在飞书任务表把状态改为「进行中」，或新建任务写清范围 |
| **收工** | 状态改「待验收」，交付物字段写：改动路径、验证命令、snapshot 是否已更新 |
| **整合** | 人工或整合 Agent 验收 →「已完成」 |

飞书是 **任务与人** 的共享层；**技术细节** 仍以 Git snapshot/registry 为准。两边都要写：飞书写「做了什么」，Git 写「改了什么文件、验证命令」。

### 档位 C — Git + claude-mem（Codex 跨会话踩坑记忆）

| 写什么进 mem | 写什么进 Git |
|--------------|--------------|
| OTA 顺序、motor 方向宏、引脚冲突、build 并行禁忌 | 进度、registry 状态、test 结果、queue |
| 「上次 T09 失败因为 WiFi 凭证占位」 | `00_snapshot` 🔴 阻塞行 |

**规则：** claude-mem 存 **经验**；不存 **唯一进度**。收工仍必须更新 snapshot/registry。

查询示例（Codex）：用户说「查 mem：mergetesting OTA」→ 用 `claude-mem-mem-search`。

---

## 5. Codex 主力工作流

### 5.1 工具链

| 组件 | 路径 | 作用 |
|------|------|------|
| 仓库规则 | `AGENTS.md` | Codex 自动加载 |
| 会话 Skill | `.agents/skills/xiao-an-session/SKILL.md` | 强制开工/收工步骤 |
| 团队 Skill | `.agents/skills/team-lark/SKILL.md` | 档位 B |
| 本文 | `docs/agents/01_session_protocol.md` | 完整方案 |

**用户口令（推荐）：**

- 开工：`按 xiao-an-session 开工` + 任务模板（§6.1）
- 收工：`按 xiao-an-session 收工`
- 并行对齐：`team-lark 对齐进度`
- 整合：`按 01 文档做整合 Agent`（§7）

### 5.2 Cursor 辅用（非默认）

Cursor **不会**自动跑本流程，除非用户明确说：

```text
请按 docs/agents/01_session_protocol.md 和 xiao-an-session 流程执行。
先读 README + 00_snapshot，再开始任务。
```

可选：`.cursor/rules/agent-session.mdc` 已在仓库中；用户可在 Cursor 启用 alwaysApply，或每次手动 @ 该 rule。

---

## 6. 开工协议（Open Session）

### 6.1 用户任务模板（复制给 Codex）

```markdown
按 xiao-an-session / docs/agents/01_session_protocol.md 开工。

## 任务
[一句话目标]

## 协作档位
- [ ] A 仅 Git（默认）
- [ ] B 先 team-lark 对齐
- [ ] C 查 claude-mem：[关键词]

## 范围
- 只改：[目录或文件]
- 禁止动：[如 shared/protocol、docs/archive]

## 必读（Agent 自行补全 registry）
- docs/agents/README.md
- docs/agents/00_snapshot.md
- [02/03/04/05/06/09 择一]

## 成功标准
- 命令：[具体 pio run / unittest / 联调步骤]
- 文档：[要更新的 registry 行]

## Queue（可选）
- 任务 ID：Txx（来自 08_priority_queue.yaml）
```

### 6.2 Agent 开工 MUST 步骤

**Step 0 — 环境**

```powershell
git status
# 若有未预期改动，先报告用户，勿擅自 revert
```

**Step 1 — 必读（不可跳过）**

1. `docs/agents/README.md`
2. `docs/agents/00_snapshot.md`
3. 按 README「阅读顺序」表加读 1–2 个 registry / checklist
4. 若用户指定 Queue ID → 读 `08_priority_queue.yaml` 对应 task

**Step 2 — 档位 B（若启用）**

执行 `team-lark` skill 第 0 步，输出今日简报，确认本任务与飞书任务一致。

**Step 3 — 档位 C（若启用）**

`claude-mem-mem-search` 查与任务相关的历史踩坑，摘要给用户。

**Step 4 — 对齐声明（回复用户）**

开工回复须包含：

```markdown
## 开工对齐
- 工具：Codex
- 档位：A / A+B / A+B+C
- 当前目标（摘自 snapshot）：…
- 我将修改的范围：…
- 成功标准：…
- 已知阻塞（🔴）：…
- Queue：Txx / 无
```

**Step 5 — 动手**

- 只改任务范围内文件
- 动 `shared/`、`docs/protocol.md` 前 **必须先停** 并告知用户
- 同一 `robot/firmware` workspace **不要并行** 多个 `pio run`（共享 `.pio/build`）

### 6.3 按任务类型的必读路由

| 任务 | 加读 |
|------|------|
| 改 `robot/firmware` | `02_firmware_registry.md`, `05_test_matrix.md` |
| 改 `robot/mergetesting` | `03_mergetesting_registry.md`, `06_integration_phases.md` |
| 改 `base_station` / `agent` | `04_base_station_agent_registry.md`, `docs/protocol.md` |
| 联调 / 烧录 | `09_hardware_bringup_checklist.md`, 最新 `project_status_*.md` |
| 跑测试 / CI | `05_test_matrix.md` |
| Agent loop | `08_priority_queue.yaml` |
| 文档卫生 / 整合 | 本文 §7, `07_maintenance.md`, `_generated/file_inventory.md` |

---

## 7. 收工协议（Close Session）

### 7.1 Agent 收工 MUST 步骤

| 步骤 | 条件 | 动作 |
|------|------|------|
| 1 验证 | _always_ | 跑任务相关命令，报告 **精确输出**（exit code） |
| 2 registry | 改了代码 | 更新 `02/03/04` 对应行：状态 + 日期 + 验证命令 |
| 3 test_matrix | 涉及 env/测试 | 更新 `05_test_matrix.md` P/H/F + 日期 |
| 4 snapshot | _always_ | 在 `00_snapshot.md`「近期重要变更」**追加一行** |
| 5 queue | 做了 queue 任务 | 更新 `08_priority_queue_results.json` |
| 6 dated status | 联调里程碑 | 新建或更新 `docs/project_status_YYYY-MM-DD.md` |
| 7 档位 B | 启用飞书 | 任务状态 → 待验收，填交付说明 + Git 改动摘要 |
| 8 档位 C | 有值得记住的坑 | 写入 claude-mem（一句话标题 + 复现/规避） |
| 9 检查 | _always_ | `git diff --check` |

### 7.2 收工摘要模板（Agent 必须输出）

```markdown
## 收工摘要
- 工具：Codex
- 协作档位：A / A+B / A+B+C
- 任务 / Queue ID：…
- 改动文件：
  - …
- 验证：
  - 命令：…
  - 结果：SUCCESS / FAIL（附关键日志一行）
- 文档已更新：
  - [ ] 02/03/04 registry
  - [ ] 05_test_matrix
  - [ ] 00_snapshot 追加行
  - [ ] 08_priority_queue_results.json
  - [ ] project_status_YYYY-MM-DD.md
  - [ ] 飞书任务（档位 B）
  - [ ] claude-mem（档位 C）
- 阻塞（🔴）：无 / …
- 下一 Agent 建议：从 Txx 继续 / 需用户 …
```

### 7.3 snapshot 追加行格式

在 `00_snapshot.md`「近期重要变更」表追加：

```markdown
| 简述 | 路径 | 影响 |
| [动词] xxx | `path/to/file` | Agent 应… |
```

**禁止**在 registry 里贴 unified diff；用 Git 查历史。

---

## 8. 多 Agent 并行规则

### 8.1 任务切分

| ✅ 好切分 | ❌ 坏切分 |
|----------|----------|
| 「mergetesting motion_service hardening」 | 「整个机器人做好」 |
| 「更新 03_registry + build display_only」 | 「检查所有 docs」 |
| 单目录：`robot/mergetesting/src/services/` | 同时改 firmware + mergetesting + protocol |

### 8.2 目录 ownership（减少冲突）

摘自 `00_snapshot.md`「谁改什么」：

| 目录 | Agent 注意 |
|------|------------|
| `robot/firmware` | 单项功能验证；勿把联调 loop 塞进 `main.cpp` |
| `robot/mergetesting` | DK-2500 联调；可激进；不回迁成 firmware 联调入口 |
| `base_station` | 改 protocol 要同步 `shared/` |
| `agent` | Gateway/Brain 与 WS 耦合 |
| `docs/protocol.md` | 破坏性变更需共识；禁止只改一处 |

### 8.3 串行 vs 并行

| 类型 | 策略 |
|------|------|
| 有依赖（build 链 T00→T06、协议变更） | **串行**，用 `08_priority_queue.yaml` |
| 无依赖（registry 刷新、单元测试、文档卫生） | 可并行，但 **不要** 同时改同一文件 |
| 整合 | 单独开「整合 Agent」会话（§9） |

---

## 9. 整合 Agent（Integrator）

**何时跑：** 大联调前后、每周一次、或用户说「整合仓库状态」。

**职责（只读+文档+轻量脚本，不擅自大改代码）：**

```powershell
python tools/generate_agent_registry.py
git status
# 读 08_priority_queue_results.json
# 对照 00_snapshot vs 05_test_matrix vs registry
# 列出 orphan / stale 文档（docs/archive 除外）
```

**交付：**

1. 更新或新建 `docs/project_status_YYYY-MM-DD.md`
2. 修正明显不一致的 registry 行（或标 🔴 待人工）
3. 输出「整库状态板」摘要给用户

**整合 Agent 开工口令：**

```markdown
按 01_session_protocol §9 做整合 Agent。档位 A。不要改源码，除非 fixing 明显 typo。
```

---

## 10. 文档卫生（防遗忘文件）

| 频率 | 动作 |
|------|------|
| 每次大改/联调 | 新建 `project_status_YYYY-MM-DD.md` |
| 每周或整合时 | `python tools/generate_agent_registry.py` → 对照 `_generated/file_inventory.md` |
| 确认过时 | MD 顶部加 `> ⚠️ ARCHIVED — 以 00_snapshot 为准`，移入 `docs/archive/` |

**不建议 Agent 做：**

- 生成与源码重复的巨型 MD
- 提交 `.pio/`, `runtime/*.jpg`, `.env`, `config.local.h`
- 用过期 `project_status` 覆盖新 snapshot

详见 [07_maintenance.md](./07_maintenance.md)。

---

## 11. 两条固件线（极易混淆，开工必核对）

| 路径 | 用途 |
|------|------|
| `robot/firmware` + dedicated env | 小机器人 **单项** 硬件验证 |
| `robot/mergetesting` | **DK-2500 联调**（WS `/control` `/video` `/audio`） |

DK-2500 联调 **烧 mergetesting**，不要把新联调入口加回 `robot/firmware/main.cpp`。

---

## 12. 快速参考 — 文件地图

```
AGENTS.md                          # L0 仓库规则（Codex 自动读）
docs/agents/
  README.md                        # L1 入口路由
  01_session_protocol.md           # L1 本文 — 开工收工全流程
  00_snapshot.md                   # L1 当前进度（收工必更新）
  02_firmware_registry.md          # L2
  03_mergetesting_registry.md      # L2
  04_base_station_agent_registry.md
  05_test_matrix.md
  06_integration_phases.md
  07_maintenance.md
  08_priority_queue.yaml
  08_priority_queue_results.json
  09_hardware_bringup_checklist.md
  10_repo_map.md                 # L1 整库目录索引
  _generated/file_inventory.md   # L5 自动生成
.agents/skills/
  xiao-an-session/SKILL.md         # Codex 开工收工 Skill
  team-lark/SKILL.md               # 档位 B
.cursor/rules/
  agent-session.mdc                  # Cursor 可选薄适配
```

---

## 13. 相关文档

- [README.md](./README.md) — Agent 入口
- [07_maintenance.md](./07_maintenance.md) — 何时更新哪些文件
- [AGENTS.md](../../AGENTS.md) — 仓库级规则
- [superpowers-using-superpowers](~/.codex/skills/superpowers-using-superpowers/SKILL.md) — Skill 优先级：`AGENTS.md` > skills > 默认系统提示
