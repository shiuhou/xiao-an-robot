# Xiao An Runtime Debug Console

本文档用于 Step 30.7 Electron 前端运行调试台的启动、验收和演示。

前端现在用于比赛演示和联调：查看本地运行状态、向 OpenClaw
`xiaoan-runtime` 发送消息、手动触发机器人动作、查看情绪/陪伴事件和动作
日志。它不再把本地 Tasks、Reminders、Memory、Work Activity 或 Screen
Report 作为主线产品入口。

OpenClaw `xiaoan-runtime` 负责用户画像、长期记忆、定时提醒、任务、晨报/
日报、自然语言回复和工具选择。`xiao-an-robot` 前端只展示本地机器人运行
和调试状态；SQLite 是 Local Event Store，不是用户长期记忆主源。

## 前置条件

- Node.js LTS，包含 `node` 和 `npm`
- Python 环境已安装仓库测试/运行依赖
- Python Local API 可启动

## 启动后端 API

在仓库根目录启动 Local API：

```powershell
python -m base_station.api.server --host 127.0.0.1 --port 8787 --db-path agent/data/xiao_an.db --verbose
```

可选健康检查：

```powershell
curl http://127.0.0.1:8787/api/health
```

成功响应应包含 `"ok": true`。

## 启动前端

```powershell
cd frontend
npm install
npm run dev
```

`npm run dev` 会启动 Vite 开发服务器和 Electron 窗口。

## 构建

```powershell
cd frontend
npm run build
```

构建产物写入 `frontend/dist/`。

## 页面功能

### Status

调用 `GET /api/health`、`GET /api/status`、`GET /api/tools`。

页面显示：

- Local API 在线状态
- OpenClaw backend、Gateway URL、agent
- Robot WebSocket 和机器人连接语义
- SQLite 数据库路径与 `local_event_store` 角色
- 本地组件状态
- OpenClaw-facing `xiaoan.*` 工具清单
- OpenClaw / Xiao An Robot 职责边界
- legacy/deprecated 本地能力列表

### Chat

调用 `POST /api/chat`，通过 `frontend.message` 进入 `XiaoAnBrain`，
再经过 OpenClaw Bridge 和 `ActionExecutor`。

页面显示：

- OpenClaw reply text
- OpenClaw tool calls（如果后端响应包含）
- executed actions
- skipped actions
- raw JSON

### Robot Debug

调用 `POST /api/tools/call` 手动触发 OpenClaw-facing 机器人工具：

- `xiaoan.robot.say`
- `xiaoan.robot.expression`
- `xiaoan.robot.move_out`
- `xiaoan.robot.return_to_dock`
- `xiaoan.robot.care`

机器人离线时，结果区会显示本地动作失败原因；成功时可用于 mock robot 或
真实机器人联调。

### Emotion Timeline

调用 `GET /api/memory/recent`，只读取 Local Event Store 中的运行事件：

- `emotion.sample`
- `emotion.intervention`
- `companion.request`

这不是长期记忆管理界面，只是情绪触发链路的调试时间线。

### Runtime Logs

调用 `GET /api/tool-runs` 和 `GET /api/memory/recent?event_type=robot.care_action`。

页面显示：

- 最近 tool runs
- `robot.care_action`
- failed tool run 错误数量和错误信息

## 降级入口

本地 Tasks、Reminders、Notes、Summaries、Work Activity 和 Screen Report 的
旧 API 仍保留，供测试和兼容使用。它们不再出现在前端主导航中，也不再作为
小安本体产品能力推荐给 OpenClaw。

## 标准演示流程

1. 启动 Python Local API。
2. 在 `frontend/` 执行 `npm run dev`。
3. 打开 **Status**，确认 API、OpenClaw backend、DB path、components 和
   OpenClaw-facing tools 可见。
4. 打开 **Chat**，发送 `你好小安` 或 `我有点累`，查看 reply/tool calls/
   action results。
5. 启动 base_station ws server 和 mock_robot 后，打开 **Robot Debug**，
   点击 **Care**，确认 mock_robot 收到 expression、motion、audio 命令。
6. 打开 **Emotion Timeline**，查看 `emotion.sample`、
   `emotion.intervention`、`companion.request`。
7. 打开 **Runtime Logs**，查看 tool runs、care actions 和失败信息。

## 验收 Checklist

- [ ] `npm run build` 通过
- [ ] `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q` 通过
- [ ] Status 显示 Local API、OpenClaw backend、机器人连接语义、数据库路径和组件状态
- [ ] Chat 能显示 OpenClaw reply/tool_calls/action results
- [ ] Robot Debug 能触发 `xiaoan.robot.*`
- [ ] Emotion Timeline 能显示运行事件
- [ ] Runtime Logs 能显示 tool_runs、robot.care_action 和错误信息
- [ ] 前端主导航不再展示 Tasks、Reminders、Memory、Work Activity、Screen Report

## 常见问题

### API Offline 或 `Failed to fetch`

检查 Python API 是否已启动：

```powershell
curl http://127.0.0.1:8787/api/health
```

### 机器人动作失败

先确认 base_station WebSocket server 和 mock_robot/真实机器人已经连接。离线
时 Robot Debug 会显示从 `RobotGateway` 返回的失败原因。

### `reply_text` 为空

fake/OpenClaw adapter 可能返回空回复。检查 route、reason、tool calls 和 raw
JSON；空回复不等同于 HTTP 请求失败。
