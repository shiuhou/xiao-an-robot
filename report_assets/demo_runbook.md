# XiaoAn Demo Runbook

## 1. 离线证据生成命令
```powershell
python tools/prepare_xiaoan_care_report_assets.py --dataset-root C:\Users\Lenovo\Desktop\datasets\xiaoan_care_v1 --out report_assets
python tools/evaluate_xiaoan_care_policy.py --dataset-root C:\Users\Lenovo\Desktop\datasets\xiaoan_care_v1 --out report_assets
python tools/evaluate_xiaoan_care_clips.py --dataset-root C:\Users\Lenovo\Desktop\datasets\xiaoan_care_v1 --out report_assets
python tools/run_e2e_emotion_smoke.py --out report_assets --backend fake --all
```

## 2. fake/mock smoke 命令
```powershell
python tools/run_e2e_emotion_smoke.py --out report_assets --backend fake --all
```

## 3. 可选真实 camera runtime 命令
Optional only. Use when local model paths and camera are verified.
```powershell
python -m base_station.monitor.emotion_runtime --source opencv_camera --model-backend openface_ov --enable-vlm-gate --vlm-backend vlm_face --vlm-model-path base_station/models/Qwen2.5-VL-3B-OV-int4 --fresh-db --verbose --no-agent
```

## 4. 可选真实 robot / OpenClaw
- only run when endpoint verified
- not required for offline report evidence
- do not describe fake smoke as real robot execution

## 5. 推荐 demo 视频脚本
1. normal observe
2. yawn/fatigue trigger
3. cooldown
4. VLM observation shown as explanation only
