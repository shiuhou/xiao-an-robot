# OpenFace 3.0 AU 8维输出映射

## 1. 结论

当前 OpenFace MTL 模型 AU 输出为固定 8 维数组。

确认顺序为：

| Tensor index | AU | English name | 中文可观察动作 |
|---:|---|---|---|
| 0 | AU01 | Inner Brow Raiser | 内眉上提 |
| 1 | AU02 | Outer Brow Raiser | 外眉上提 |
| 2 | AU04 | Brow Lowerer | 眉部下压 |
| 3 | AU06 | Cheek Raiser | 面颊上提 |
| 4 | AU09 | Nose Wrinkler | 鼻部皱起 |
| 5 | AU12 | Lip Corner Puller | 嘴角上提 |
| 6 | AU25 | Lips Part | 双唇分开 |
| 7 | AU26 | Jaw Drop | 下颌下落 |

该映射可用于描述可观察面部动作，不可直接映射为焦虑、抑郁、压力等心理状态。

## 2. 来源追踪

### 上游项目

- 官方仓库：`CMU-MultiComp-Lab/OpenFace-3.0`
- 模型/工具版本：OpenFace 3.0
- 官方仓库地址：`https://github.com/CMU-MultiComp-Lab/OpenFace-3.0`

### 主要参考文件

| 上游文件 | 用途 |
|---|---|
| `demo2.py` | 确认 8 维 AU 的展示顺序和名称：AU1、AU2、AU4、AU6、AU9、AU12、AU25、AU26 |
| `model/MLT.py` | 确认多任务模型的 AU 输出路径，并检查 AU 输出是否额外执行 sigmoid |
| `model/AU_model.py` | 检查 AU Head 的内部计算结构 |
| `train_mix_au_dev.py` | 检查 AU 训练标签、损失和测试阈值，辅助判断输出更接近激活/检测分数，而非 FACS 0–5 强度 |

### 参考源码版本

本文档应记录一个可复核的上游参考 commit，但该 commit 只表示本次调查所参考的官方源码版本，不等于已经证明本地 OpenVINO IR 一定由该 commit 导出。

```text
上游参考分支：main
上游参考 commit：662a555a8566ae3aec8139cb8c72acf6d06e0eb3
查询日期：2026-06-20
本地 git ls-remote 查询结果：失败，原因：当前 Git/Schannel 环境无法完成远程仓库查询；该 commit 由官方 GitHub commit 页面复核。
```

### 本地模型制品边界

当前仓库调查尚未建立以下信息：

* 本地 `mtl.xml` / `mtl.bin` 对应的上游 commit；
* PyTorch checkpoint 哈希；
* OpenVINO IR 文件 SHA256；
* 模型导出脚本和导出参数；
* PyTorch 与 OpenVINO 的输出一致性记录。

因此，应区分：

1. 官方 OpenFace 3.0 源码定义的 AU 映射；
2. 当前本地 OpenVINO IR 的完整制品来源。

前者已确认；后者仍需后续补充模型 manifest 或导出记录。

## 3. 仓库数据流

```text
OpenVINO MTL 模型
→ 第三个输出 tensor
→ ov_out[2]
→ au_output[0]
→ list[float]
→ OpenFace observation["au"]
→ cv_sample["au_json"]
```

当前 AU 数值在运行时不进行：

* sigmoid
* softmax
* clip
* 阈值二值化
* 额外归一化

表情分类输出会执行 softmax，但 AU 输出不会。

## 4. 当前数值语义

统一称为：

```text
activation_score
```

暂时不正式称为：

```text
intensity
```

`activation_score` 表示模型输出的 AU 激活分数。当前未证明该数值是校准概率，也未证明它对应 FACS 0–5 强度等级。

原因是当前模型训练和测试实现更接近 Action Unit 检测，尚未证明其对应 FACS 0–5 强度等级，也没有证明其为经过校准的概率。

## 5. 人工动作验证

已通过实时摄像头可视化完成以下验证：

| 人工动作      | 主要观察维度                 | 结果    |
| --------- | ---------------------- | ----- |
| 皱眉        | AU04 Brow Lowerer      | 有明显响应 |
| 微笑        | AU12 Lip Corner Puller | 有明显响应 |
| 微笑并抬起面颊   | AU06 Cheek Raiser      | 有响应   |
| 双唇分开      | AU25 Lips Part         | 有响应   |
| 明显张嘴、下颌下落 | AU26 Jaw Drop          | 有明显响应 |

整体观察结果：8 维 AU 对动作的响应较准确。

AU25 和 AU26 在明显张嘴时可能同步变化，这是合理的动作共现：

* AU25 表示双唇分开；
* AU26 表示下颌下落；
* 明显张嘴通常同时包含上述两个动作。

因此不能要求 AU25 和 AU26 完全独立变化。

## 6. 已修正的可视化问题

旧实现错误地按数组位置显示为：

```text
AU01, AU02, AU03, AU04, AU05, AU06, AU07, AU08
```

正确显示顺序为：

```text
AU01, AU02, AU04, AU06, AU09, AU12, AU25, AU26
```

相关可视化测试应锁定完整 8 维顺序，防止回归。

## 7. 当前使用边界

现阶段允许：

* 在调试界面展示真实 AU 名称；
* 在日志和测试中记录 AU 及其可观察动作；
* 将 AU 作为 CV 层可观察证据保存。

现阶段禁止：

* 直接根据单个 AU 判断用户心理状态；
* 把 AU04 直接解释为焦虑；
* 把 AU12 直接解释为愉快；
* 把 AU 数值直接写成 FACS 强度；
* 未经合同评审就修改正式 emotion event；
* 未经评测就让 AU 参与 Gate 或疲劳分数。

## 8. 后续语义化建议

未来如需修改数据结构，建议采用：

```json
{
  "AU04": {
    "value": 0.62,
    "measurement": "activation_score",
    "description": "眉部下压"
  }
}
```

该格式目前仅为候选方案，尚未进入正式数据合同。
