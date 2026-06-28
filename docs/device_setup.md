# 新设备部署 (Device Setup)

在一台新机器上从零跑起感知 + VLM 链路。代码和 OpenFace OV IR 随仓库 clone 即到位；
大块模型权重（Qwen2.5-VL、intel、hsemotion）不进 git，由脚本从公开的 Hugging Face 仓库下载。

## 0. 前置

- conda（或 venv），Python 3.10+
- git + git-lfs（`git lfs install` 至少跑一次）

## 1. 拉代码（含 OpenFace IR）

```bash
git lfs install
git clone <repo-url>
cd xiao-an-robot
git lfs pull          # 拉取 base_station/models/openface_ov/ 下的 IR（约 77MB）
```

`git lfs pull` 后确认 IR 已是真文件而非指针：

```bash
git lfs ls-files | grep openface_ov     # 应列出 retinaface/star/mtl 的 .xml/.bin
```

## 2. 环境依赖

```bash
conda create -n openface python=3.10 -y
conda activate openface
pip install -r base_station/requirements.txt -r base_station/requirements-vlm.txt
```

> `requirements-vlm.txt` 里的版本是**钉死**的，尤其 `transformers==4.57.6`。
> 这是 Qwen2.5-VL int4 包导出时的版本；装成 5.x 会在加载 processor 时因
> `fix_mistral_regex` 参数冲突直接崩。详见该文件内注释。

## 3. 下载模型权重

```bash
python tools/setup_models.py
```

脚本会把三类模型拉到正确路径并逐文件 sha256 校验：

| 模型 | Hugging Face 仓库 | 落地路径 |
|---|---|---|
| Qwen2.5-VL int4 | `ericzheng1/Qwen2.5-VL-3B-OV-int4` | `base_station/models/Qwen2.5-VL-3B-OV-int4/` |
| intel + hsemotion | `ericzheng1/xiao-an-base-models` | `base_station/models/{intel,hsemotion}/` |

两个仓库都是公开的，无需 token。常用选项：

```bash
python tools/setup_models.py --check          # 只校验本地、不下载
python tools/setup_models.py --only qwen_vl   # 只处理某一个仓库
python tools/setup_models.py --force          # 强制重下
```

## 4. 跑起来

```bash
# Windows / PowerShell 下建议先设：
#   $env:KMP_DUPLICATE_LIB_OK="TRUE"; $env:OMP_NUM_THREADS="1"
python -m base_station.monitor.emotion_runtime \
  --source opencv_camera --model-backend openvino \
  --enable-vlm-gate --vlm-backend vlm_face \
  --vlm-model-path base_station/models/Qwen2.5-VL-3B-OV-int4 \
  --fresh-db --verbose
```

> 真 VLM 首次加载 CPU int4 约 30s、单帧推理约 18s，属正常；调试时把触发频率/帧数压小。

---

## 附录 A：Qwen int4 包是怎么来的（可复现兜底）

部署默认走“下载成品”（第 3 步）。下面记录它**当初的导出方式**，以备需要从源头重建：

它是用 `optimum-cli` 从官方全精度 `Qwen/Qwen2.5-VL-3B-Instruct` 本地导出 + INT4
权重量化得到的（data-free，无标定集）。参数全是 `--weight-format int4` 的默认值
（group_size 128 / ratio 1.0 / 非对称），与成品 `openvino_config.json` 记录一致：

```bash
# 需要 requirements-vlm.txt 那套环境（optimum-intel / nncf）
huggingface-cli download Qwen/Qwen2.5-VL-3B-Instruct \
  --local-dir base_station/models/Qwen2.5-VL-3B-Instruct

optimum-cli export openvino \
  --model base_station/models/Qwen2.5-VL-3B-Instruct \
  --weight-format int4 \
  base_station/models/Qwen2.5-VL-3B-OV-int4
```

导出记录的版本：`optimum 2.1.0` / `transformers 4.57.6`。

## 附录 B：哪些进 git、哪些不进

- **进 git（普通）**：代码、`requirements*.txt`、`models_manifest.json`、本文件、`.gitattributes`、`.gitignore`
- **进 git（LFS）**：仅 `base_station/models/openface_ov/**/*.{xml,bin}`（单仓 Route A 的核心 IR）
- **不进 git**：`Qwen2.5-VL-3B-OV-int4/`、`intel/`、`hsemotion/`（由 `setup_models.py` 下载）
