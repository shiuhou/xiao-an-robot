# Integration Console Visual Trace Design

## 1. 目标

在 `base_station/integration_console/` 的相机页面中，以每秒 1-2 张分析快照展示真实 Route A 视觉链路：

```text
/video frame -> OpenFace observation -> cv_sample -> VLMTriggerGate
             -> async VLM -> fusion -> console visualization
```

页面必须展示真实运行时数据，不在浏览器中重新计算 OpenFace、Gate 或 VLM 结果，也不改变现有决策行为。

## 2. 第一版范围

### 分析画面

- 显示人脸检测框。
- 显示 STAR/WFLW 98 点 landmarks。
- 高亮眼睛和嘴部轮廓。
- 显示 `frame_id`、快照时间、数据年龄和实际发布频率。
- 闭眼或打哈欠证据命中时改变相关轮廓颜色。

### CV 和 Gate 状态

- 显示 EAR、MAR、face confidence、emotion、fatigue、observation quality 和 evidence codes。
- 显示 Gate 的真实规则值、阈值和命中状态。
- 显示正式 `gate_result.should_trigger` 和 `gate_result.reason`。
- 控制台不得再次调用 `gate.evaluate()`。

### 异步 VLM 状态

- 状态包括 `idle`、`running`、`done` 和 `error`。
- 每次调用绑定唯一 `request_id` 和 `trigger_frame_id`。
- VLM 运行期间，主 OpenFace 画面继续更新。
- 页面保留 VLM 触发帧，VLM 结果只显示在对应触发帧旁边。
- VLM 使用 single-flight 后台任务：同一时间只执行一个请求；VLM 忙碌时继续处理 CV/Gate 帧，但不排队或覆盖当前请求。

## 3. 非目标

- 不修改 OpenFace、Gate、VLM 或 fusion 的判断规则和阈值。
- 不在浏览器 Canvas 中重新绘制完整 landmarks。
- 不增加可编辑运行时阈值。
- 不实现复杂历史曲线或完整 AU 分析面板。
- 不长期保存摄像头人脸图片。
- 不以独立 probe 进程作为正式数据源。

## 4. 推荐架构

正式 Route A 增加一个失败可降级的只读 observer。Observer 接收同一次处理已经产生的 `frame`、OpenFace `obs`、`cv_sample`、`gate_result` 和异步 VLM 状态，限速后发布控制台快照。

运行期产物统一放在：

```text
runtime/integration_console/visual/
  latest_annotated.jpg
  latest_state.json
  vlm_trigger.jpg
  vlm_state.json
```

Integration Console 增加只读 API：

```text
GET /api/visual/state
GET /api/visual/latest-image
GET /api/visual/trigger-image
```

浏览器每秒轮询状态，通过变化的 `snapshot_id` 更新图片。文件超过规定年龄后显示 `STALE`，不得继续显示为实时在线。

## 5. 数据一致性

`latest_state.json` 使用版本化契约 `visual_console_v1`，至少包含：

- `snapshot_id`
- `frame_id`
- `timestamp_ms`
- `published_at_ms`
- 原始图像尺寸
- `observation`
- `cv_sample`
- Gate 阈值、规则状态和正式结果
- VLM `request_id`、触发帧、状态、耗时、结果和错误
- fusion 结果

图片和 JSON 必须携带或引用同一个 `snapshot_id`。所有正式文件先写同目录临时文件，再通过原子替换发布，避免读取半张 JPEG 或半段 JSON。

VLM 的完成回调必须核对 `request_id`。过期任务可以记录，但不能覆盖较新的活动请求状态。

## 6. 最小实施顺序

1. 运行相关单元测试，记录分支基线。
2. 测试驱动定义 `visual_console_v1` 和原子发布器。
3. 测试驱动实现纯 OpenFace 标注函数，先用合成 frame 和 landmarks。
4. 在正式 Route A 增加只读 observer，确保 OpenFace 和 Gate 每帧各只执行一次。
5. 使用模拟 `/video` 数据包尽早打通 WebSocket、OpenFace 和快照发布，暂不依赖真实 VLM。
6. 增加 Integration Console 只读 API 和缺失、陈旧、损坏文件处理。
7. 实现相机页面的画面、CV、Gate 和 freshness 展示。
8. 接入异步 VLM 生命周期和固定触发帧。
9. 使用真实机器人 `/video`、真实 OpenFace、真实 Gate 和真实 VLM 完成最终闭环。

## 7. 每步正确性门槛

- 每个行为变化先写失败测试，再写最小实现。
- 每完成一步，只运行该步骤的聚焦测试和直接相关回归测试。
- `/video` 模拟链路必须在页面开发前通过，避免最后才发现真实帧边界问题。
- Observer 的任何异常只能记录 warning，不能终止视觉 runtime。
- 快照发布限制为 1-2 FPS，不对每个输入帧执行磁盘写入。
- 页面只显示运行时正式 Gate 结果，不复制 Gate 决策逻辑。
- 最终完成声明必须有真实机器人 `/video` 闭环证据。

## 8. 精简验收场景

第一版只保留四个验收场景：

1. 正常人脸：landmarks 正确，Gate 不触发，VLM 为 idle。
2. 确定性触发：Gate 点亮，保存正确触发帧，VLM 从 running 进入 done。
3. VLM 错误：页面显示 error，OpenFace 快照继续刷新。
4. 真实闭环：真实机器人 `/video` 经过 OpenFace、Gate、真实 VLM 并在控制台正确关联帧和结果。

## 9. 临时文件和清理策略

### 允许的临时产物

- 自动化测试仅使用 `tempfile.TemporaryDirectory()`。
- 手工联调产物仅写入 `runtime/integration_console/visual/`。
- 若需要一次性本地测试图片，放在系统临时目录，不加入仓库。

### 禁止事项

- 不在 `tools/`、`tests/` 或仓库根目录创建一次性调试脚本。
- 不提交 JPEG、模型输出、JSONL trace、数据库或 runtime 状态。
- 不使用宽泛删除命令清理整个 `runtime/`。
- 不删除用户已有的 `runtime/` 其他子目录或文件。

### 完成前清理

1. 列出 `runtime/integration_console/visual/` 的确切内容。
2. 停止相关服务，避免文件仍被写入。
3. 只删除本功能拥有的四个正式产物及其已知临时文件。
4. 删除空的 `runtime/integration_console/visual/` 目录；父目录非空则保留。
5. 运行 `git status --short`，确认没有临时图片、JSON、日志或未跟踪脚本。
6. 运行目标测试和最终真实 `/video` 闭环验证。

运行期目录由 `.gitignore` 中的 `runtime/` 规则覆盖，但仍以最终清单检查为准。

## 10. 主要风险及控制

- **Landmarks 坐标错误**：复用并测试现有 probe 的 `face_bbox` 偏移逻辑。
- **98 点索引错误**：按当前 STAR/WFLW 输出和 EAR/MAR 实现确认眼睛与嘴部索引，不套用 68 点模型。
- **图片和状态错帧**：统一 `snapshot_id`、`frame_id` 和原子发布。
- **Gate 状态被控制台改变**：observer 只接收正式结果，禁止二次 evaluate。
- **VLM 结果贴到错误画面**：使用 `request_id + trigger_frame_id` 并保留触发帧。
- **观测逻辑拖慢主链路**：限速、最小复制、失败降级，不允许反向阻塞。
- **陈旧图片伪装实时**：API 返回 age，页面显示 live、stale 或 unavailable。
- **测试产物污染仓库**：集中目录、临时目录和完成前精确清单清理。

## 11. 完成标准

- Integration Console 每秒显示 1-2 张来自正式 Route A 的 OpenFace 分析快照。
- landmarks、人脸框、眼睛和嘴部轮廓与真实图像对齐。
- Gate 面板显示真实规则状态，并在正式 Gate 触发时点亮。
- 异步 VLM 结果与触发帧严格关联，错误不会停止 CV 更新。
- 控制台和快照发布失败不会改变机器人或视觉运行行为。
- 最终使用真实机器人 `/video` 完成端到端验证。
- 仓库中不存在本次开发遗留的临时脚本、图片、JSON 或 trace。
