# 小安 (Xiao An) · 情感桌面陪伴机器人

基于 Intel Core Ultra 的桌面智能情感助理

## 架构概览

详见 [docs/protocol.md](docs/protocol.md)

```
Robot (ESP32-S3) 
  ↓ WebSocket (audio/video stream)
Base Station (Intel Core Ultra)
  ↓ OpenVINO inference + emotion sensing
Agent (OpenClaw)
  ↓ LLM call + skill execution
Robot (display/motion/TTS)
```

## 快速开始

### 机器人固件 (Robot Firmware)

```bash
cd robot/firmware
# 使用 PlatformIO 编译并上传到 ESP32-S3
pio run -t upload
```

### 基站服务 (Base Station)

```bash
cd base_station
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 下载 OpenVINO 模型
bash models/download_models.sh

# 启动 WebSocket 服务器
python ws_server/server.py
```

### 智能体 (Agent)

```bash
cd agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 初始化数据库
sqlite3 data/xiao_an.db < data/schema.sql

# 启动大脑
python core/brain.py
```

## 团队成员

| 成员 | 角色 | 职责 |
|------|------|------|
| 张子尧 | App & Integration | 前端/集成 |
| 郑斯悦 | AI & Deployment | 模型/部署 |
| 施宇灏 | Hardware & Firmware | 硬件/固件 |

## 分支策略

| 分支 | 用途 | 保护规则 |
|------|------|----------|
| `main` | 生产/发布 | ✓ PR review ✓ 测试通过 |
| `develop` | 开发主线 | ✓ PR review |
| `feature/*` | 特性开发 | 无限制 |
| `bugfix/*` | Bug 修复 | 无限制 |

## 文件结构

```
xiao-an-robot/
├── robot/              # ESP32-S3 固件
├── base_station/       # 边缘推理服务
├── agent/              # 智能体内核 + 技能
├── frontend/           # Electron GUI
├── docs/               # 文档
├── .gitignore
├── README.md           # 本文件
└── LICENSE
```

## License

MIT License - see LICENSE file
