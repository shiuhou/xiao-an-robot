# Agent 文档维护规范

> 开工/收工全流程见 [01_session_protocol.md](./01_session_protocol.md)。Codex 用户：`按 xiao-an-session 收工` 时按 §7 检查本表。

## 何时更新

| 事件 | 更新哪些文件 |
|------|-------------|
| 新 PlatformIO env / 新 src 文件 | `02_firmware_registry.md`, `05_test_matrix.md` |
| mergetesting 模块变更 | `03_mergetesting_registry.md`, `EXTRACTION_MAP.md` |
| 协议字段变更 | `docs/protocol.md`, `shared/*`, **禁止只改一处** |
| 联调前/后 | `00_snapshot.md`, 新建 `docs/project_status_YYYY-MM-DD.md` |
| 整库整理 / 整合 Agent | `10_repo_map.md` §7, `_generated/file_inventory.md` |
| 测试跑通/失败 | `05_test_matrix.md` 改 P/H/F + 日期 |

## 变更记录写法

在 `00_snapshot.md` 的「近期重要变更」追加表格行：

```markdown
| 简述 | 路径 | 影响 |
| 新增 xxx | `path/to/file` | Agent 应… |
```

**不要**在注册表里贴 unified diff；用 Git 查变更：

```powershell
git log -5 --oneline -- robot/firmware/src/
git diff main -- robot/mergetesting/
```

## 自动清单（不含状态）

```powershell
python tools/generate_agent_registry.py
```

输出：`docs/agents/_generated/file_inventory.md`
人工状态列仍在 `02_*` / `03_*` 维护。

## 粒度原则

| 需要 | 做法 |
|------|------|
| 知道某文件干什么 | 注册表一行 |
| 知道函数行为 | 注册表 + 指向行号范围 |
| 知道每行代码 | **读源文件**，不要复制进 MD |
| 知道测试是否过 | `05_test_matrix.md` |

## 多 Agent 并行建议

详见 [01_session_protocol.md §8](./01_session_protocol.md#8-多-agent-并行规则)。摘要：

1. 开工前读 `00_snapshot.md` + 用 `xiao-an-session` skill
2. 只改自己目录；动 `shared/` 或 `protocol.md` 先通知
3. 收工更新 registry + test matrix + snapshot 一行 + 收工摘要
4. 并行多窗口可选档位 B（`team-lark`）；Codex 踩坑可选档位 C（claude-mem）
5. 勿 force-push；见根目录 `AGENTS.md`

## 不建议 Agent 做的文档

- 不要生成与源码重复的 5000 行 MD
- 不要提交 `.pio/`, `runtime/*.jpg`, `.env`
- 不要用过期 `project_status` 当唯一真相
