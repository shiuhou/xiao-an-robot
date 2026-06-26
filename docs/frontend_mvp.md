# Xiao An Frontend MVP

本文档用于 Step 29 Electron 前端 MVP 的启动、验收和演示。前端通过
Python Local API 使用小安的聊天、上下文、任务、提醒和统一记忆能力。

Step 30.1 之后，本页中的 Tasks、Reminders、Memory、Project Context
流程只代表 legacy compatibility 和本地调试面，不再代表主线产品能力。
用户画像、长期记忆、定时提醒、任务、晨报/日报、自然语言回复和工具选择
由 OpenClaw `xiaoan-runtime` 负责；本仓库保留机器人身体、感知链路、本地
情绪阈值、安全策略、ESP32 通信、动作执行和 Local Event Store。

## 前置条件

- Windows 主机
- Node.js LTS，包含 `node` 和 `npm`
- Python conda 环境 `xiao-mvp`
- 后端 Local API 已完成 Step 28
- 仓库已切换到需要验收的开发分支

## 启动后端 API

在仓库根目录激活 Python 环境：

```powershell
conda activate xiao-mvp
```

启动 Local API：

```powershell
python -m base_station.api.server --host 127.0.0.1 --port 8787 --db-path agent/data/xiao_an.db --verbose
```

可选健康检查：

```powershell
curl http://127.0.0.1:8787/api/health
```

成功响应应包含：

```json
{
  "ok": true
}
```

## 启动前端

打开另一个终端：

```powershell
cd frontend
npm install
npm run dev
```

`npm run dev` 会启动 Vite 开发服务器和 Electron 窗口。

## 构建和生产启动

```powershell
cd frontend
npm run build
npm start
```

`npm run build` 将 renderer 资源写入 `frontend/dist/`。`npm start`
使用 Electron 加载该构建结果。

## 端口说明

| 地址 | 用途 |
| --- | --- |
| `127.0.0.1:8787` | Python Local API Server |
| `127.0.0.1:5173` | Vite dev server，仅开发模式使用 |

如果 `5173` 可以打开但请求 `8787` 失败，说明前端已启动而后端 API
尚未启动。

## 页面功能

### Status

调用以下接口检查本地服务：

- `GET /api/health`
- `GET /api/status`
- `GET /api/tools`

页面显示 API 在线状态、数据库路径、Robot WebSocket 地址、运行组件和本地
工具列表。

### Chat

调用 `POST /api/chat`，通过现有 `frontend.message` 路径把文本交给
`XiaoAnBrain`。页面显示：

- `handled`
- `route`
- `reason`
- `reply_text`
- executed actions
- skipped actions
- raw JSON

当前 mock/OpenClaw adapter 可能返回 `handled=false` 或空 `reply_text`。
只要 HTTP 响应成功且 `ok=true`，这仍是正常结果。

### Context Preview

调用 `POST /api/context/preview`，显示：

- requested scopes
- context policy
- matched keywords
- confidence
- project memory summary
- raw context JSON

Context Preview 是只读预览。它不会调用 OpenClaw、执行工具、触发机器人或
写入统一记忆。

### Tasks

Legacy compatibility only. 主线产品任务归 OpenClaw `xiaoan-runtime`。

支持：

- 创建任务
- 查询任务
- 完成 pending 任务
- 取消 pending 任务

完成或取消后，页面会重新查询后端状态。`done` 和 `cancelled` 任务不会显示
无意义的操作按钮。

### Reminders

Legacy compatibility only. 主线产品提醒归 OpenClaw `xiaoan-runtime`。

支持：

- 创建提醒
- 查询提醒
- 查询到期提醒
- 将到期提醒标记为 fired
- 取消 pending 提醒

Reminder 是定时提醒，不等同于 Task。

### Memory

Legacy compatibility only. SQLite 是 Local Event Store，不是用户长期记忆主源。

包含四个只读视图：

- Notes：查询最近笔记或按内容搜索
- Recent Memory：按 `event_type` 查询统一事件流
- Tool Runs：按工具名和 `status` 查询工具调用记录
- Project Context：查看 notes、tasks、reminders 的轻量项目上下文

长 payload、arguments、result 和 raw context 默认折叠，避免页面被大块
JSON 撑开。

### Tools

当前 Sidebar 保留 Tools 入口，但 Step 29 不提供工具调用调试面板。

## 标准演示流程

### 1. 启动服务

1. 在仓库根目录启动 Python Local API。
2. 在 `frontend/` 目录执行 `npm run dev`。
3. 等待 Electron 窗口打开。

### 2. 验证 Status

1. 打开 **Status**。
2. 确认 API Status 显示 **Online**。
3. 确认 service、status、db_path、robot_ws_url 和 components 有数据。
4. 确认 Local Tools 显示工具数量和名称。

### 3. 验证 Chat

1. 打开 **Chat**。
2. 在 Chat Message 输入：

   ```text
   你好小安
   ```

3. 保持 session ID 为 `default`。
4. 点击 **Send**。
5. 确认页面显示 handled、route、reason 和返回 JSON。

### 4. 验证 Context Preview

依次预览以下文本：

```text
我还有哪些任务没完成？
```

预期 requested scopes 包含 `tasks`。

```text
我刚才让你记了什么？
```

预期 requested scopes 包含 `notes`。

```text
你好小安
```

预期不注入大量项目记忆，requested scopes 通常为空。

### 5. 验证 Tasks

1. 打开 **Tasks**。
2. 创建：

   ```text
   Step 29.6 demo task
   ```

3. 点击该任务的 **Complete**，确认状态变为 `done`。
4. 再创建：

   ```text
   Step 29.6 task to cancel
   ```

5. 点击 **Cancel**，确认状态变为 `cancelled`。

### 6. 验证 Reminders

1. 打开 **Reminders**。
2. 创建：

   ```text
   Step 29.6 demo reminder
   ```

3. 将 `delay_seconds` 设置为 `1`。
4. 等待约 2 秒。
5. 点击 **Query Due Reminders**。
6. 确认该提醒出现在 Due Reminders。
7. 点击 **Mark Fired**，确认状态变为 `fired`。
8. 再创建：

   ```text
   Step 29.6 reminder to cancel
   ```

9. 将 `delay_seconds` 设置为 `600`。
10. 点击 **Cancel**，确认状态变为 `cancelled`。

### 7. 准备和验证 Memory

如果数据库中还没有演示笔记，可以先通过 Local API 写入一条：

```powershell
curl -X POST http://127.0.0.1:8787/api/tools/call `
  -H "Content-Type: application/json" `
  -d '{"tool":"note.add","arguments":{"content":"Step 29.6 frontend demo note"},"session_id":"frontend-demo"}'
```

然后打开 **Memory**：

1. Notes 搜索 `Step 28.6` 或 `Step 29.6`。
2. Recent Memory 查看最近的 memory events。
3. Tool Runs 查看 `note.add`、`task.add`、`task.complete`、
   `reminder.add` 等记录。
4. Project Context 依次选择 `notes`、`tasks`、`reminders`。
5. 确认摘要与最近记录能正确显示。

## 验收 Checklist

- [ ] `npm install` 通过
- [ ] `npm run build` 通过
- [ ] `python -m unittest discover -s tests -v` 通过
- [ ] Status 显示 API Online
- [ ] API Offline 时页面不崩溃，并显示可读错误
- [ ] Chat 能显示成功 HTTP 返回，包括 `handled=false`
- [ ] Context Preview 能识别 tasks scope
- [ ] Context Preview 能识别 notes scope
- [ ] Context Preview 对普通问候返回 no-context
- [ ] Tasks create 通过
- [ ] Tasks complete 通过
- [ ] Tasks cancel 通过
- [ ] Reminders create 通过
- [ ] Reminders due 查询通过
- [ ] Reminders mark-fired 通过
- [ ] Reminders cancel 通过
- [ ] Memory Notes 查询通过
- [ ] Memory Recent Events 查询通过
- [ ] Memory Tool Runs 查询通过
- [ ] Memory Project Context 查询通过

## 常见问题

### `npm` 不是内部或外部命令

安装 Node.js LTS，并重新打开终端。验证：

```powershell
node --version
npm --version
```

### API Offline 或 `Failed to fetch`

检查 Python API 是否已启动，并访问：

```powershell
curl http://127.0.0.1:8787/api/health
```

### `5173` 能打开但 `8787` 请求失败

前端开发服务器已经启动，但 Python Local API 没有启动。回到仓库根目录启动
API server。

### `reply_text` 为空

当前 mock/OpenClaw adapter 下可能正常。检查 `handled`、`route`、`reason`
和 raw JSON，不要把空回复自动视为请求失败。

### Context Preview 不写入记忆

这是预期行为。Context Preview 是只读预览，不执行工具，也不写
`memory_events`。

### 中文 curl query 乱码

前端使用 `URLSearchParams` 构造查询参数，不会手工拼接中文 URL。手写 curl
时应对 query 参数执行 URL encode，或优先使用前端界面。

## 机器人控制边界

当前 Step 29 不包含真实机器人控制按钮，也不暴露 `/api/robot/*`。

机器人与基站之间仍通过 WebSocket / `RobotGateway` 通信。未来如需从前端
手动调试机器人，可以新增独立的 Robot Debug API，但它不是当前 Frontend
MVP 的组成部分。

屏幕监控已退出 MVP；不要把 screen monitoring 作为后续前端目标。
