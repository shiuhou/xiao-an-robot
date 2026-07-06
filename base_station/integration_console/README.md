# Xiao-An DK-2500 Integration Console

工程联调用本地前端，不是正式用户产品 UI。它用 Python 标准库 HTTP server 提供 `/console` 页面和 JSON API，离线运行，不依赖 Electron、Vite、React 或 CDN。

## Run

```powershell
python -m base_station.ws_server.server
python -m base_station.integration_console.console_server --host 0.0.0.0 --port 8090 --ws-url ws://127.0.0.1:8765/agent --runtime-dir runtime
```

Open:

```text
http://<DK2500-IP>:8090/console
```

## Surfaces

| Path | Role |
| --- | --- |
| `/console` | 中文联调页面，适配 1024x600 和普通浏览器。 |
| `/api/health` | Console 自身状态和 runtime 文件存在性。 |
| `/api/state` | 聚合 console、`runtime/ws_state.json`、图像、音频、OpenClaw 和最近日志。 |
| `/api/latest-image` | 返回 `runtime/latest.jpg`，带 no-cache。 |
| `/api/visual/state` | 返回 Route A 的 OpenFace、Gate、异步 VLM 和 fusion 快照。 |
| `/api/visual/latest-image` | 返回带 OpenFace 标注的最新分析快照，带 no-cache。 |
| `/api/visual/trigger-image` | 返回当前 VLM 请求对应的触发帧，带 no-cache。 |
| `/api/audio-stats` | 返回 `runtime/audio_stats.json`，不存在时结构化失败。 |
| `/api/robot/*` | 通过 `/agent` 发已有机器人命令：表情、运动、本地音效、TTS。 |
| `/api/scenario/run` | step-by-step 安全场景脚本。 |
| `/api/tools/run` | 固定白名单工具，不接受浏览器 raw shell。 |
| `/api/logs/recent` | 最近 JSONL 联调日志。 |
| `/api/logs/export` | 导出当前状态和日志到 `runtime/integration_console/export_*.json`。 |

## Safety

- 默认不自动运动。
- 所有运动按钮在前端确认，`stop` 除外。
- 页面顶部常驻 `STOP ALL / 急停`。
- 后端也钳制 safe 参数：默认速度 `0.56`，距离不超过 `10cm`，超时不超过 `1200ms`，除非显式 bench。
- bench 模式需要高级开关，UI 标明“危险 / 仅空载测试”。
- 音频命令有保守 cooldown，避免 TTS 和 local sound 连续触发 speaker not ready。
- 工具执行只接受白名单 tool id。
- 日志不保存原始音视频、token、secret。

## Visual Trace

`tools/ops/run_ws_video_runtime.py` 默认以最多 2 FPS 发布控制台观测文件：

```text
runtime/integration_console/visual/latest_annotated.jpg
runtime/integration_console/visual/latest_state.json
runtime/integration_console/visual/vlm_trigger.jpg
runtime/integration_console/visual/vlm_state.json
```

这些文件是有界的运行期快照，不是历史记录。页面只展示正式 Route A 已经产生的 OpenFace、Gate 和 VLM 状态，不会再次执行 Gate。VLM 结果通过 `request_id` 和 `trigger_frame_id` 绑定触发画面。

本地模拟 `/video`：

```powershell
python tools/ops/run_ws_video_runtime.py --host 127.0.0.1 --port 8765 --no-agent --model-backend mock --vlm-backend fake --force-vlm --visual-trace-fps 1
python tools/probes/send_test_video_frame.py --url ws://127.0.0.1:8765/video --frames 3 --fps 1 --width 320 --height 240
```

模拟包会经过正式 WebSocket 解码路径，但不能证明 ESP32 摄像头、机器人网络或真实模型正常。

## Related

- [../../docs/runbooks/integration_console.md](../../docs/runbooks/integration_console.md)
- [../ws_server/server.py](../ws_server/server.py)
- [../dashboard/README.md](../dashboard/README.md)
