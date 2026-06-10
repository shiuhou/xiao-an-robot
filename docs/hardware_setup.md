# Hardware Setup Guide

# robot design 
机器人本体的制作方案
整体分两部分：底盘 和 上半身。
底盘（负责移动）
结构：
┌─────────────────────┐
│   ESP32-S3 主板      │
│   电机驱动板         │  ← 3D 打印一个扁平底盘托住这些
│   锂电池            │
│   左轮    右轮       │
│   限位开关（前后各1）│
└─────────────────────┘
3D 打印一个约 12cm × 10cm × 3cm 的扁平底盘，两侧各固定一个 N20 电机，轮子外露。前后各装一个微动开关，用来检测是否进出 Dock。
上半身（负责表情和交互）
结构：
┌──────────────┐
│  TFT 表情屏  │  ← 正面，显示眼睛表情
│  OV2640 摄像头│  ← 嵌在头部，朝向用户
│  INMP441 麦克 │  ← 藏在内部
│  扬声器      │  ← 底部或侧面开孔
│  两个舵机    │  ← 控制"耳朵"摆动
└──────────────┘
上半身打印一个圆润的球形/蛋形外壳，参考设计图里小安的造型。

3D 建模建议
既然是原型，不建议从零开始画，太费时间。
推荐做法：找开源底座改
去 Printables 或 Thingiverse 搜：
2WD robot chassis N20 motor
mini robot body ESP32
找一个接近的底盘模型，下载后用 Fusion 360 或 TinkerCAD 改一下尺寸，加上你需要的安装孔位就行。上半身可以用简单的圆柱+半球组合，TinkerCAD 半小时就能搞定原型级外壳。

打印参数建议
参数建议值材料PLA（够用，便宜，好打）层高0.2mm（原型级，速度快）填充20%（轻量化，省料）外壳厚度2mm（够结构强度）支撑底盘不需要，上半身视造型而定

组装顺序建议
第一步：先不打印外壳，用面包板和胶带把所有硬件临时固定
         → 先把软件跑通，确认所有硬件工作正常

第二步：硬件全部验证没问题后
         → 量好每个元件的实际尺寸
         → 画外壳 + 打印

第三步：装进外壳，最终组装
千万不要先打外壳再买硬件。 尺寸一定会对不上，白打一次。


## ESP32-S3 Wiring
TODO: Add pin mapping table and wiring diagram.

## Intel DK-2500 Setup
TODO: Ubuntu 22.04 install steps, driver setup, NPU verification.

## Camera (OV2640)
TODO: Connection and test steps.

## Microphone (INMP441)
TODO: I2S pin config and test steps.
