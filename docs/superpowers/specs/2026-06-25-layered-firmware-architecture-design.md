# Xiao-An 分層式 Firmware 架構設計 Spec

日期：2026-06-25
狀態：供 review 的設計草案
範圍：ESP32-S3 firmware、DK-2500 integration firmware、未來可擴展方向

## 摘要

Xiao-An 目前的整體系統方向是合理的：ESP32-S3 負責 robot body，DK-2500/base station 負責通訊、感知和本地運算，Agent 負責推理和高層決策。真正的問題不是沒有架構，而是**架構邊界沒有穩定落到代碼邊界**。

現在很多功能以「一個 PlatformIO env 對一個大入口檔」的方式存在。這對硬件 bring-up 很安全，因為每條路線可以單獨 build、upload、看 serial log；但長期會造成產品功能難以組合、難以共用、也難以判斷哪段代碼是真正可用。

本 spec 的核心建議是：

```text
保留現有 bring-up env
  -> 把每個 env 逐步變成 thin app
  -> 把可用能力下沉到 services / hal / transport / protocol
  -> 先整理 /control + motion + status
  -> 再逐步整理 face / camera / audio / OTA / docking
```

## 現況判斷

目前 repo 已經有清楚的系統級分工：

- `robot/firmware`：ESP32-S3 robot-body firmware、硬件 bring-up、可複用硬件模組。
- `robot/mergetesting`：DK-2500/base-station integration firmware，負責 `/control`、`/video`、`/audio` 的整合燒錄路線。
- `base_station`：DK-2500 WebSocket server、perception、ASR、emotion runtime。
- `agent`：Agent brain、gateway、skills、memory/context。
- `shared`：protocol constants、schema、examples。

這個大方向不要推翻。需要改善的是 firmware 內部的代碼組織。

目前有價值的做法：

- 使用獨立 PlatformIO env 做硬件 bring-up。
- 使用 `build_src_filter` 避免不同測試入口互相干擾。
- `motor_cam_wifi_manual`、`face240_9expr_merged`、`voice_recognition_test`、`speaker_amp_test` 等路線可作為硬件驗證點。
- `robot/mergetesting` 已經從 `robot/firmware` 中分離出來，適合作為 DK-2500 demo/integration firmware。

目前的主要問題：

- 很多行為直接寫在 `*_main.cpp` 裡。
- 初始化、狀態、通訊、硬件控制、demo UI 混在一起。
- `robot/firmware` 和 `robot/mergetesting` 有相似但不完全一致的邏輯。
- 一個 env 裡能跑的功能，搬到另一個 env 時經常要複製大段代碼。
- 新功能容易改壞已經可用的 bring-up route。

## 設計目標

1. 保留目前已知可用的 bring-up env 名稱和驗證命令。
2. 讓 motor、display、camera、mic、speaker、OTA 等能力逐步變成可複用模組。
3. 讓 `*_main.cpp` 逐步變成 thin app，只負責組裝功能，不承擔大量業務邏輯。
4. 保持 `robot/firmware` 和 `robot/mergetesting` 的邊界：前者驗證 robot-body 能力，後者負責 DK-2500 integration 行為。
5. 優先穩定 `/control` 最小閉環，再擴展 `/video`、`/audio`、Agent 主動關懷。
6. 支持未來新增語音互動、視覺主動關懷、dock/limit switch、OTA config、operator UI、mock/simulation。

## 非目標

- 不把 `robot/mergetesting` 合回 `robot/firmware`。
- 不在硬件仍 bring-up 時刪除現有 env。
- 不一次性重寫 camera、audio、display、motor、Agent。
- 不讓 ESP32-S3 承擔重型 AI inference。
- 不把 WiFi 密碼、真實 logs、SQLite database、model binaries、`.pio`、venv、`node_modules` 放進 Git。

## 設計原則

1. **Thin env, reusable modules**：每個 env 保留，但入口要越來越薄。
2. **先驗證，再共用**：功能先在 `robot/firmware` 的獨立 env 裡驗證，再最小化同步到 `robot/mergetesting`。
3. **穩定路線優先**：已經能跑的 camera stream、motor manual、face test 不在第一階段大改。
4. **協議比隱式調用重要**：ESP32、base station、Agent 之間用明確 message type 和 payload。
5. **狀態顯式化**：robot state 要明確包含 expression、motion、camera、audio、docked、busy、network、last error。
6. **安全下沉**：motor boot-safe、deadman stop、pin low、emergency stop 應該在 driver/service 層，不散落在 app 裡。

## 目標系統形狀

```text
User / environment
  -> sensors and commands
  -> ESP32-S3 robot body
  -> DK-2500 base station
  -> Agent layer
  -> robot commands and feedback
```

ESP32-S3 的責任：

- 安全執行 motion。
- 顯示 face/status。
- 捕獲 camera frame。
- 串流 mic/audio data。
- 播放 local speaker feedback。
- 回報 state、ack、error。

DK-2500/base station 的責任：

- 管理 WebSocket `/control`、`/video`、`/audio`。
- 處理 camera/audio stream。
- 執行 OpenVINO、ASR、VAD、fatigue/emotion、VLM gate。
- 把 raw perception 轉成結構化 event。

Agent layer 的責任：

- 接收結構化 context。
- 決定高層 action。
- 透過 gateway 發送 `display.expression`、`motion.execute`、`audio.play_*`、`config.update` 等 command。

## Firmware 分層模型

推薦分層：

```text
apps/
  PlatformIO env 的薄入口：setup、loop、profile selection

services/
  可複用 robot 行為：motion、face、camera、audio、status、safety

hal/
  硬件 driver：motor、display、camera、mic、speaker、OTA、pins

transport/
  通訊：WebSocket、HTTP AP、serial、OTA、stream adapters

protocol/
  message type、payload parser、message builder、schema alignment

config/
  feature profile、board profile、pin map、ignored local config hook
```

### apps 層

apps 層只做組裝：

- 選擇 feature profile。
- 初始化 driver/service/transport。
- 在 `loop()` 裡調用 tick。
- 不直接擁有可複用的 motor、camera、WebSocket、display 邏輯。

目標例子：

```text
robot/firmware/src/apps/main_robot_body_app.cpp
robot/firmware/src/apps/motor_manual_app.cpp
robot/firmware/src/apps/motor_cam_wifi_manual_app.cpp
robot/firmware/src/apps/face240_app.cpp
robot/firmware/src/apps/ota_bootstrap_app.cpp
```

### services 層

services 層負責產品語義和狀態：

- `RobotState`：expression、motion、camera、audio、docked、busy、WiFi、WebSocket、last error。
- `MotionService`：`motion.execute`、busy guard、deadman stop、motion completed、final position。
- `FaceService`：expression rendering、face profile、display status rows。
- `CameraService`：camera mode、JPEG capture、frame metadata、stream throttle。
- `AudioService`：local tone、TTS 階段性播放策略、mic stream control。
- `StatusService`：heartbeat/status snapshot、error report、command ack。
- `CommandRouter`：把 protocol command type 映射到 service 方法。
- `SafetyService`：boot-safe pin hold、emergency stop、watchdog hooks。

### hal 層

hal 層負責硬件細節：

- `MotorDriver`：DRV8833。
- `DisplayDriver`：ST7735/ST7789。
- `CameraDriver`：OV2640。
- `MicDriver`：INMP441。
- `SpeakerDriver`：MAX98357A。
- `OtaDriver`：ArduinoOTA wrapper。
- `BoardPins`：current wiring、legacy wiring、feature-specific pin profile。

services 可以調用 hal，但 hal 不應該知道 WebSocket message type 或 Agent semantics。

### transport 層

transport 層只負責搬運資料：

- `WsTransport`：`/control`、`/video`、`/audio`、reconnect、heartbeat timing。
- `HttpManualControl`：AP UI、`/cmd`、`/status`、`/jpg`、`:81/stream`。
- `SerialControl`：WASD、mock ASR、硬件測試命令。
- `OtaTransport`：OTA setup/loop。

transport 不應該直接操作 motor/display。它應該把 command 交給 service。

### protocol 層

protocol 層負責 firmware 和 `docs/protocol/protocol.md`、`shared/protocol` 對齊：

- `robot_protocol.h`
- `command_types.h`
- `message_builder.h`
- `payload_readers.h`

protocol 層不放業務邏輯。

## 目標目錄形狀

這是漸進式目標，不是一次性搬遷：

```text
robot/firmware/src/
  apps/
  config/
  hal/
  protocol/
  services/
  transport/
  experiments/
  archive/

robot/mergetesting/src/
  app/
  integration/
  adapters/
  reused/
  config/
```

`robot/firmware/src/experiments/` 用來放仍在探索的源碼。

`robot/firmware/src/archive/` 用來放歷史源碼，不應被 product env build。

`robot/mergetesting/src/reused/` 用來放從 `robot/firmware` 驗證後最小同步過來的模組。

## PlatformIO Env 策略

第一階段不改 env 名稱，因為 docs、handoff、硬件操作習慣都依賴這些名字。

### Product / Integration

- `esp32-s3-devkitc-1`：robot-body baseline，未來可變成 thin product-body app。
- `mergetesting`：DK-2500 integration baseline。
- `mergetesting_display_only`
- `mergetesting_face240_only`
- `mergetesting_cam_only`
- `mergetesting_mic_only`
- `mergetesting_base64_video`

### Bring-Up / Hardware Validation

- `motor_manual`
- `motor_bench_once`
- `motor_wifi_manual`
- `motor_cam_wifi_manual`
- `camtesting`
- `serialqrservo`
- `redtracker`
- `serialredtracker`
- `display_test`
- `face240_roboeyes`
- `face240_wiretest`
- `face240_integrated`
- `face240_9expr_merged`
- `tftprobe_hybrid_rawinit`
- `voice_recognition_test`
- `speaker_amp_test`

### Recovery / Operations

- `ota_bootstrap`
- `ota_bootstrap_wifi`

長期來看，`build_src_filter` 應該從「選一個大 main + 幾個 cpp」逐步變成「選一個 app + 多個共用 module」。

例子：

```text
motor_manual
  apps/motor_manual_app.cpp
  hal/motor_driver.cpp
  services/motion_service.cpp
  transport/serial_control.cpp
  config/board_profile.cpp
```

## Command 和 Data Flow

### `/control` 最小閉環

```text
ESP32 -> device.hello -> base_station
base_station -> system.welcome -> ESP32
ESP32 -> device.status -> base_station
Agent/base_station -> motion.execute -> ESP32
ESP32 -> command.ack + motion.completed or error.report -> base_station
ESP32 -> device.status -> base_station
```

規則：

- `action_id` 必須從 `motion.execute` 保留到 `motion.completed`。
- busy 狀態要由 `MotionService` 統一管理。
- unsupported command 走 `error.report` 和 `command.ack error`。
- `device.status` 是 expression、motion、camera、docked 的同步點。

### Video Loop

```text
CameraDriver
  -> CameraService
  -> WsTransport /video binary JPEG or base64 fallback
  -> base_station video source
  -> perception event
  -> Agent decision
```

規則：

- `motor_cam_wifi_manual` 的 AP/MJPEG route 保留為已知可用 camera+motor bring-up 路線。
- `/video` integration 先走 `mergetesting_cam_only`。
- QR、face、fatigue 不應改壞主 stream；新功能先走獨立 endpoint、mode 或 base-station side processing。

### Audio Loop

```text
MicDriver
  -> AudioService
  -> WsTransport /audio PCM
  -> VAD/ASR/emotion on DK-2500
  -> Agent text event
  -> command response
```

規則：

- `voice_recognition_test` 仍然是 INMP441 electrical/RMS validation，不是完整 ASR。
- 真正 ASR/VAD 在 DK-2500。
- speaker 先支援 local tone / local sound，再接 TTS playback。

### Face Display Loop

```text
display.expression command
  -> CommandRouter
  -> FaceService
  -> DisplayDriver
  -> status update
```

規則：

- `face240_9expr_merged` 是 2.4-inch product face 的重要基準。
- 128x160 ST7735 和 2.4-inch ST7789 不必第一階段強行合成同一 driver。
- 先統一 service API，再整理底層 driver。

## 遷移計劃

### Phase 0：設計基準

交付本 spec。此階段不改 firmware 行為。

完成條件：

- spec 已在 repo 中。
- 明確說明哪些東西不在第一階段移動。
- 明確指出第一個實作切片。

### Phase 1：State、Motion、Command Routing

先建立最小可複用 product slice：

- `RobotState`
- `StatusService`
- `MotionService`
- `CommandRouter`

優先套用到：

- `robot/mergetesting/src/main.cpp`
- 之後才評估 `robot/firmware/src/main.cpp`

不先碰：

- `motor_cam_wifi_manual_main.cpp`
- camera stream
- audio stream
- face240 大檔案

建議驗證：

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only

cd ..\firmware
pio run -e motor_manual
pio run -e motor_cam_wifi_manual

cd ..\..
git diff --check
```

### Phase 2：Motor 和 Safety HAL

抽出 motor/safety 共用能力：

- DRV8833 pin setup。
- boot-safe low state。
- motor direction constants。
- deadman stop。
- command failure stop。
- docked/final-position helpers。

套用目標：

- `motor_manual`
- `motor_bench_once`
- `motor_wifi_manual`
- `motor_cam_wifi_manual`
- `mergetesting_display_only`

新增驗證：

```powershell
cd robot\firmware
pio run -e motor_bench_once
pio run -e motor_wifi_manual
```

### Phase 3：Face Display Service

抽出 face/display service API：

- `setExpression(expression, intensity)`
- `setConnectionStatus(text)`
- `setCameraStatus(text)`
- `setMotionStatus(text)`
- `tick()`

保留 128x160 和 2.4-inch profile 差異。

建議驗證：

```powershell
cd robot\firmware
pio run -e display_test
pio run -e face240_wiretest
pio run -e face240_9expr_merged

cd ..\mergetesting
pio run -e mergetesting_face240_only
```

### Phase 4：Camera Service 和 Stream Adapters

拆分 camera 責任：

- `CameraDriver`：OV2640 pin/init/capture。
- `CameraService`：mode、frame metadata、capture throttle。
- `HttpManualControl`：AP MJPEG route。
- `WsTransport`：`/video` route。

`motor_cam_wifi_manual` 保留為 local AP camera+motor 基準路線。

建議驗證：

```powershell
cd robot\firmware
pio run -e camtesting
pio run -e motor_cam_wifi_manual

cd ..\mergetesting
pio run -e mergetesting_cam_only
```

### Phase 5：Audio Service

拆分 mic/speaker：

- `MicDriver`：INMP441 I2S capture。
- `SpeakerDriver`：MAX98357A tone/playback。
- `AudioService`：stream/playback decision。
- `/audio` adapter：PCM streaming。

建議驗證：

```powershell
cd robot\firmware
pio run -e voice_recognition_test
pio run -e speaker_amp_test

cd ..\mergetesting
pio run -e mergetesting_mic_only
```

### Phase 6：Product App Assembly

當前面 service 都穩定後，再組產品 app：

- state
- motion
- face
- camera
- audio
- WebSocket
- OTA hooks
- safety hooks

這條 product app 可以成為每日 demo route，但不替代 bring-up env。

## 未來可新增和優化的方向

### OTA 和 Config Management

方向：

- 保留 `ota_bootstrap` 作為 recovery bridge。
- product firmware 只在 motor boot safety 穩定後接 OTA。
- WiFi/base station/device config 放在 ignored local config 或 NVS。
- serial/status 顯示 IP、firmware version、OTA state、base-station IP。

### Docking 和 Limit Switch

方向：

- 先確定 final GPIO。
- 加 `DockService`。
- dock state 接入 `motion.completed.final_state`。
- 異常 switch transition 觸發 hard stop。

### Visual Active Care

方向：

- ESP32 只做低頻 JPEG stream。
- DK-2500 做 face/fatigue/head-pose/VLM gate。
- Agent 收 structured event，不收 raw frame。
- robot response 使用既有 command：expression、小動作、local sound、TTS。

### Voice Interaction

方向：

- ESP32 透過 `/audio` 傳 PCM。
- DK-2500 做 VAD、ASR、voice emotion。
- Agent 回 text 和高層 command。
- TTS 先用 local tone 或 base-station generated audio 過渡。

### Manual Control 和 Operator UI

方向：

- 保留 AP/manual route 作為硬件 recovery 工具。
- base-station UI 等 `/control` 和 status 穩定後再做。
- UI 顯示 robot state、stream health、last command、last error、firmware version。

### Simulation 和 Mocking

方向：

- 擴展 Python mock robot：busy、motion completion、camera metadata、audio staged behavior。
- 增加 protocol contract tests，比對 `shared/protocol` 和 firmware constants。
- Agent behavior 先用 simulation 驗證，再燒 firmware。

### Protocol Versioning

方向：

- `device.hello` 加 protocol version。
- capability flags 加 camera、mic、speaker、face display、motor、OTA、dock。
- 缺少 capability 是正常狀態，不直接當成錯誤。

### Build 和 CI Hygiene

方向：

- env-specific build 仍然是 firmware 真相來源。
- 建立 small critical env matrix 做快速檢查。
- full hardware env builds 保留手動或 nightly。
- env/source routing 改動後更新 docs/agents registry。

### Code Ownership

規則：

- `apps/` 可以 env-specific。
- `services/` 至少要有兩個使用者，或明確是 product app 需要的可複用能力。
- `hal/` 不知道 Agent、WebSocket message semantics。
- `transport/` 不直接控制 motor/display。
- `protocol/` 不放業務邏輯。

## 測試策略

### 文檔和靜態檢查

```powershell
git diff --check
python tools/generate_agent_registry.py
```

改 protocol、base station、Agent、test helper 時：

```powershell
python -m unittest discover -s tests -p "test_*.py"
python tools/check_runtime_env.py
```

### Firmware Build Checks

按變更範圍選 env，不跑 broad `pio run`：

```powershell
cd robot\firmware
pio run -e esp32-s3-devkitc-1
pio run -e motor_cam_wifi_manual
pio run -e face240_integrated
pio run -e face240_wiretest
pio run -e face240_9expr_merged
pio run -e voice_recognition_test
pio run -e speaker_amp_test
```

### Mergetesting Build Checks

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_face240_only
pio run -e mergetesting_cam_only
pio run -e mergetesting_mic_only
```

### 硬件驗證順序

- Motor：serial/manual -> one-shot bench -> integration。
- Camera：AP/JPEG preview -> `/video`。
- Display：wire/color test -> expression rendering -> integration。
- Mic：RMS/electrical test -> `/audio`。
- Speaker：local tone -> command-triggered playback。
- OTA：USB bootstrap -> wireless upload。

## 風險和控制

| Risk | Mitigation |
| --- | --- |
| refactor 改壞已可用硬件 demo | env 名稱穩定；一次只遷移一個 slice；跑 env-specific build。 |
| 共用模組過早抽象 | 只有兩個以上真實使用者，或 product app 明確需要時才抽。 |
| `robot/firmware` 和 `robot/mergetesting` 漂移 | 保留 migration map；只同步已驗證最小模組。 |
| camera/audio 改動影響 `/control` | `/control` 是 minimum loop，每次 stream 改動前後都先驗證。 |
| config refactor 泄露 secret | 真實 config 只放 ignored local file 或 NVS；Git 只放 example。 |
| `build_src_filter` 掩蓋壞檔案 | 更新 registry；按 env matrix build changed env。 |

## 成功標準

這次架構遷移成功的標準：

1. 現有 bring-up env 名稱仍可使用。
2. `robot/mergetesting` 仍是 DK-2500 integration firmware。
3. 至少一條 product behavior 使用 service，不再複製 app 邏輯。
4. `motion.execute` 走共用 busy guard、motor execution、ack、completion、status 路線。
5. camera、audio、face 後續能透過 service 組合，而不是複製整個 `*_main.cpp`。
6. docs 能明確說明每個硬件能力由哪個 env 驗證。

## 推薦第一個實作切片

第一步做 Phase 1：

- 新增 `RobotState`。
- 新增 `StatusService`。
- 新增 `MotionService`。
- 新增 `CommandRouter`。
- 先套用到 `robot/mergetesting/src/main.cpp`。

理由：

- `/control` 是目前 integration backbone。
- motion/status 比 camera/audio 更容易驗證。
- 不會先動 `motor_cam_wifi_manual` 這條已知重要 demo route。
- 成功後可以把同一模式複用到 face、camera、audio。

## Review Checklist

開始實作前，先確認以下設計決策：

- 第一階段保留所有現有 env 名稱。
- `motor_cam_wifi_manual` 暫時作為穩定 bring-up route，不作為第一個 refactor target。
- DK-2500 燒錄和 demo 走 `robot/mergetesting`。
- robot-body 模組驗證走 `robot/firmware`。
- 每個 slice 只 build relevant env，不跑 broad `pio run`。
