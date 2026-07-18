# 屏幕情境理解 · 架构与进度

> 小安陪伴机器人(2026 英特尔杯 · 港科广团队)的一个子系统。
> 本文档是这条工作线的**单一事实来源**,记录目标、架构、分层、进度。改动请同步更新本文件。
> 最近更新:2026-07-16

---

## 1. 目标

在**本地**持续记录用户的屏幕活动轨迹并读懂"在做什么";当用户**主动**向 OpenClaw 求助时,把这段历史作为充分上下文,真正帮上代码/文书的忙,并能生成当日使用**日报**。

一句话:把"用户这一天在多个窗口里到底做了哪几件事"结构化沉淀下来,按需喂给 OpenClaw。

## 2. 铁律(不可动摇的约束)

1. **不主动介入** — 屏幕数据只在用户开口求助时才用,不做主动弹窗/提醒。
2. **轨迹级理解** — 不是单帧截图,而是把"多窗口随时间的操作序列"重建成一件事。
3. **隐私是红线 · 用户主导路由** — 用户标 OK 的内容走云端(效果好,给原始数据);不允许的留 Intel 本地走本地 LLM;疑似敏感但没标的,反问用户授权。
4. **键盘只记数量不记内容**(不是 keylogger)。"打了什么"靠读 UIA 文本**状态**,不靠按键。
5. **理解节奏 = 段边界触发**(切应用 / 内容大变 / ~10min 封顶),不是固定 60s。

## 3. 系统三层(物理部署)

```
ESP32-S3 机器人本体
        │  局域网
Intel DK-2500 基站 (Ubuntu 24.04) ── OpenClaw agent(有记忆, ContextBuilder, 日报)
        │  局域网(schema 上报)
Windows PC ── screen-tracker 常驻进程(本仓库)  ← 我们正在做的部分
```

## 4. 四层屏幕读取分类法(话术)

| 层 | 手段 | 拿到什么 | 本项目用法 |
|---|---|---|---|
| L1 | Win32 窗口元数据 | 前台 app / 标题 / 空闲 | ✅ 已用 |
| L2 | UI Automation(UIA) | UI 结构 / 可见文本 / 地址栏 URL | ✅ 主力 |
| L3 | 像素截图 + OCR/VLM | 任意画面 | ✋ 未用(重、隐私大) |
| L4 | 应用插桩(浏览器扩展 / VSCode 插件) | DOM 正文 / 文件路径 / 光标 / 诊断 | 🔜 后续项 |

## 5. 软件分层(逻辑架构)

```
采集层  window/input_meter/content  ──►  surface(判类型+定策略)
                                              │
提取层  ui_extract(按 surface profile 抽正文/元信息)   ← 当前完成度最高
                                              │
理解层  segmenter(段边界) + understander(本地/云 LLM) → 活动笔记   ← 未开始
                                              │
衔接层  store(SQLite) → schema 上报 → OpenClaw ContextBuilder / 日报   ← 未开始
```

### surface 类型 × 捕获策略

| surface | 触发 | 捕获策略 policy | 抽取内容 |
|---|---|---|---|
| browser_chat | 浏览器 + AI 站点域名 | full | 对话内容(取最新轮次) |
| browser_page | 浏览器 其他 | full | 标题 + main/article 正文开头 |
| im | 分类=communication(微信/QQ) | **meta_only** | 只记对象+时长,**正文不读** |
| sensitive | 银行/密码/投资 关键词 | **none** | 只留 app+分类 |
| os_shell | 终端/文件管理器 | full | 焦点缓冲区(命令/路径) |
| generic | 其余(VSCode/Word) | full | 焦点区域文档文本 |

## 6. 关键技术决策(提取层)

- **焦点锚定**:从 `GetFocusedControl()` 出发,只读用户光标所在的编辑区/文档,而非从窗口根 BFS(否则先撞菜单/侧栏)。终端/输入框近乎完美。
- **Chromium 无障碍树懒加载**:靠给渲染子窗口发 `WM_GETOBJECT` 唤醒 a11y 树,否则 UIA 读不到网页正文。
- **结构剪枝**:整棵跳过 菜单栏/工具栏/状态栏/Tab/文件树,以及 aria role ∈ {navigation,banner,complementary,contentinfo,toolbar} 的子树。
- **ARIA main/article 地标定位** + **段落优先排序**(截取时优先 ≥20 字的句子,而非先来先到)+ 包含去重(合并重复推荐卡)。
- **按需全篇**:每帧只截一小段(网页 500 / 对话 600 字);`full=True` 时放宽到 4000,留给"用户点名要总结"那条路。

## 6.5 理解层设计(已定案 2026-07-16)

把提取层的**帧流**(每 2–5s:app/title/url/正文片段/键鼠/读写模式)变成写进 `work_activities` 的**活动笔记**。

**三个定案**
| 决策 | 定案 | 含义 |
|---|---|---|
| 关联(缝多窗口成一件事) | **LLM 滑动状态缝合** | Understander 本身就是关联器,一次调用出 project_id |
| LLM 节奏 | **段边界即时调** | 每关闭一个原子段调一次 |
| MVP 后端 | **先接云端验效果** | 先不做本地,先看理解质量天花板 |

**结构**
```
帧流 → Segmenter(状态机: 切原子段 + 最小段时长闸)
          │ 段关闭即触发
          ▼
      Understander(云 LLM, 一次调用 = 关联+命名+分类)
          in : 新原子段 + 当前活跃任务列表(每条带 recent_trace 跨窗口轨迹)
          out: project_id(或 NEW) + activity_type + gist + 任务状态更新
          │
          ├─► 写 work_activities 一行
          └─► 更新滚动任务状态(追加轨迹 / 关闭超时任务)
```

**原子段(状态机产物,零 LLM)**:边界 = 切前台 app / URL 或标题大变 / idle 超阈 / 10min 封顶。字段:app、title、url、去噪正文片段、keys/clicks/dwell、读写模式、起止时间。可拿现有日志离线回放。

**LLM I/O 契约**
- 输入:`{new_segment:{app,surface,title,url,content,dwell_s,mode,keys,clicks}, active_tasks:[{project_id,title,activity_type,recent_trace:[{app,title,gist}],last_active}]}`
- 输出:`{assignment:{project_id|"NEW", new_task_title, activity_type, gist, confidence}, task_updates:[{project_id,status:active|closed}]}`

**prompt 灵魂**:系统角色是"重建用户工作叙事",判断新片段是**延续**哪条任务还是**开启**新任务,靠**窗口之间的关系**(编辑器↔知乎横跳=查资料改代码),而非单窗口标题。关系上下文靠 `recent_trace` 喂入。

**project_id 生命周期**:LLM 只说"归 t_001 / 还是 NEW",真 id 由编排器签发;关闭走两条路——LLM 标 closed 或状态机对"超 30min 无活动"自动关。活跃任务列表封顶 ~5 条防上下文膨胀。

**work_activities 映射**(零改 schema):event_id←段id,app_name/window_title←段,activity_type/project_hint(=task title)/project_id/confidence←LLM,duration_seconds←dwell,timestamp←段起点。

**护栏**
- 最小段时长闸(<8s 并入相邻,不触发调用)+ 回到"仍活跃任务"窗口走廉价状态更新,防 A-B-A-B 刷爆云。
- 云不可达/超时 → 段先落库、activity_type 用规则分类兜底、project_id 挂"未关联",绝不丢数据。
- **隐私**:云优先意味着正文离开本机。验证期只跑自己的屏幕,且跳过 `sensitive`/`meta_only` 段;白名单路由必须在跑到别人/敏感内容前就位(见 §8.2)。
- 云后端具体模型/家等写 `understander.py` 时定;接口做成 provider 无关。

**已落地(2026-07-17)**:provider = **通义千问 Qwen**(阿里),走 **OpenAI 兼容接口**(`openai` 库指向 DashScope,
换厂商只改 base_url+key);模型 **qwen-plus**;结构化输出 **JSON 模式**(`response_format={"type":"json_object"}`
+ 提示写字段说明 + `json.loads`+校验);密钥走 **config.json**(`qwen_api_key`)。红线在 `QwenUnderstander.ingest`
内部强制:`capture_policy != "full"` 的段直接走本地关联,正文物理不进 payload、不发网络。无 key/openai 未装/云挂
→ 自动降级 `RuleUnderstander`,段先落库不丢。

## 7. 当前进度

| 模块 | 状态 | 完成度 | 备注 |
|---|---|---|---|
| L1 采集(window/input_meter/content) | ✅ | 稳 | 键鼠只计数 |
| surface 分类 | ✅ | 稳 | 6 类 3 策略,路由表实测正确 |
| 提取层 · 终端/输入框 | ✅ | ~95% | focus 锚定读到真实缓冲区 |
| 提取层 · 普通网页 | 🟡 | ~70% | 正文出得来;推荐卡/热搜等长句噪声残留 ~30%(UIA 边际递减) |
| 提取层 · AI 对话 | 🟡 | ~75% | 输入框实时内容✓;历史多轮未专门验证 |
| 提取层 · VSCode generic | ⬜ | 待验证 | focus 改造后未测 |
| 提取层 · IM/敏感 | ✅ | 100% | 三轮日志红线零泄漏 |
| **理解层 · 帧落地(任务0)** | ✅ | 完成 | `frames.py` schema + `probe_trace --out`;JSONL 可回放 |
| **理解层 · segmenter(任务1)** | ✅ | 完成 | 帧→原子段,纯状态机;7 项合成测试全过。2026-07-17 修 2 bug:`_absorb` 跨窗口字段串味(chrome 段挂终端标题)+ 最小段闸误吞有正文短段(知乎搜索链);现只折叠"full 策略空正文瞬时切换" |
| **理解层 · understander(任务2)** | ✅ | 完成+云验 | Qwen(OpenAI兼容/JSON模式)+ Rule 兜底;**qwen-plus-latest + 国际站端点实测通过**;prompt 迭代到 v3(平衡:关联敢缝合 + gist 忠于内容);红线内建已验 |
| **理解层 · replay(任务3)** | ✅ | 完成+云验 | frames→段→笔记+日报草稿;rule 离线 + qwen 云端均跑通 |
| **衔接层** | ⬜ | 0% | store→schema→OpenClaw,未开始 |
| 脱敏 | ⬜ | 0% | 日志抓到过邮箱/私信数,入库前必做 |

**验收标准**:提取层不是"人眼看着干净",而是"**LLM 够不够料判断用户在干嘛**"——此标准已过线,提取层视为可冻结(补 VSCode + AI 对话历史两次顺手验证)。

## 8. 未决架构议题(与对谈子智能体的开场分歧,待深入)

1. **轨迹重建的责任归属**:跨窗口"缝成一件事"是状态机问题还是 LLM 问题?倾向引入显式 session/task 追踪层(以 project_hint 为锚),LLM 只负责命名而非关联。
2. **隐私判定时机(最紧要)**:采集是连续无人值守的,"疑似敏感反问"发生在求助时,但数据在入库那一刻已落盘。是否需要"捕获点前置分级",甚至第四态"读了但加密隔离、未授权永不进 ContextBuilder"?
3. **L4 优先级**:代码场景下 VSCode 插桩(文件路径/光标/诊断)信息密度碾压网页 UIA。第一块 L4 是否该押编辑器而非浏览器扩展?
4. 方向已确认对、别推翻:焦点锚定 + 结构剪枝 + 段边界触发;schema 复用 OpenClaw 的 `work_activities`。

## 9. 复用目标(OpenClaw 侧,勿重造)

- `work_activities` 表:app_name / window_title / activity_type / project_hint / project_id / confidence / duration_seconds …
- `ContextBuilder`:提问时自动注入 "work" scope。
- `daily_summary_builder`:日报生成。

## 10. 回退资产

- `tracker/ui_extract.py.bak`(浏览器路径之前的最初版)
- `tracker/ui_extract.py.mvp.bak`(profile MVP 之前)
- `tracker/ui_extract.py.profiles.bak`(去噪轮之前)
- `tracker/segmenter.py.bak`(2 bug 修复之前)
- 运行时 `kind="legacy"` 可强制旧走法。

## 11. 理解层第一刀 · 进度与下一步

离线回放垂直切片(任务0–3)已全部落地,`replay.py` 能把帧流跑成 work_activities 行 + 日报草稿。

**已验(2026-07-17)**
- 任务0 帧落盘 `frames.py`/`probe_trace --out`、任务1 `segmenter.py`(6 项合成测试全过)、
  任务2 `understander.py`(Qwen + Rule 兜底)、任务3 `replay.py` 全部完成。
- **rule 后端离线跑通**:`python -u replay.py frames.jsonl` → 7 帧→6 段→6 条笔记 + 按 project 聚合的日报草稿。
- **红线已验**(无网络):`QwenUnderstander.ingest` 对 `meta_only`/`none` 段绝不调用云(哨兵测试:
  故意让 client 抛错,非 full 段照常返回=未触发);full 段的正文才进 payload。
- **兜底已验**:无 key / openai 未装 → `make_understander('qwen')` 自动降级 rule,不报错。

**云端实测通过(2026-07-17)** —— 用一段 41 帧真实工作流(知乎搜港科广/红鸟 → GitHub xiao-an-robot/HKUST 仓库 → VSCode 改 ARCHITECTURE/report.py → 终端 SSH 连 Intel 板):
- **端点/模型踩坑**:`sk-ws-` 工作空间 key 属**新加坡区**,须用国际站端点 `dashscope-intl.aliyuncs.com`(北京端点报 401);`qwen-plus` 基础别名免费额度耗尽(403 FreeTierOnly),换 **`qwen-plus-latest`** 可用(各模型独立免费额度)。
- **缝合能力已证**:Qwen 把 GitHub 浏览 + VSCode 读码缝成一条"代码审查"任务(跨 chrome+Code),并认出"知乎搜港科广 = GitHub 搜 HKUST"是同一条研究线——rule 后端做不到的语义关联。
- **prompt 教训**:第一版关联强但 gist 略过度;加硬约束防"编造"后关联又变碎;**v3 分两个尺度**——"关联判断敢缝合"(放)+ "gist 忠于给定字段、不编造具体名词"(严)——两者兼得。
- **一次乌龙**:曾把终端 gist 里的"SSH/18789/Ubuntu"当幻觉,核对完整正文后发现**内容里真有** `ssh -L 18789... Ubuntu 24.04`,是提取准确、我看漏了预览。教训:判断幻觉前先看完整 content。
- **遗留**:①部分页面(知乎)提取残留热搜噪声,已用"以 title/url 为准"prompt 缓解;②终端正文把**内网 IP/用户名**发上了云——脱敏(§11 衔接层)必须覆盖终端与控制台类内容。

**再往后(衔接层,未开始)**:接实时 collector → 写 SQLite/schema → OpenClaw ContextBuilder / 日报;隐私脱敏(邮箱/私信数)入库前做。

> 未决架构议题(§8)保留;§8.2 隐私路由在"上云到非白名单/别人内容"前必须落地——当前云路径仅供用户在自己屏幕上验证。

## 12. 衔接层 · 进度 / 真实链路断点 / 阶段3联调清单

**已编码(单元/集成测试通过,2026-07-18)**
- 阶段0 `bridge.note_to_kwargs`(映射唯一真源)+ 单测。
- 阶段1 `work_activities.note` 列 + 幂等迁移 + `insert_work_activity(note=)` + `query` + `ContextBuilder` 求助注入。
- 阶段2 板子 `POST /api/work-activities` 写入口 + `bridge.post_note`(stdlib urllib)+ `should_transport` 红线 + `ActivityNote.capture_policy` + `config.board_base_url`。

**真实链路实跑(2026-07-18 · 真 Qwen · frames.jsonl 41 帧)**
- ✅ **提取→切分→理解(真云)连通**:`replay.py frames.jsonl --backend qwen` → 41 帧→12 段→12 条 note;跨窗口关联正常(知乎港科广+GitHub HKUST 缝成一条 researching;GitHub+VSCode 缝成一条 coding);日报草稿正常。
- ✅ **断点已修(理解层→衔接层落库打通)**:`replay.py` 加 `--store <db>` 最小落库步(每条 note 走 `bridge.note_to_kwargs`→`insert_work_activity`,无板子/无 HTTP/无去重)。`replay.py frames.jsonl --backend qwen --store data/xiao_an_local.db` → **12 条真 Qwen note 全部落本地 xiao_an.db**;真 `ContextBuilder.build_for_text("帮我看看我当前工作的进度")` 读回:**work scope 命中、5 条活动、note 均为真 gist**。**提取→切分→理解→bridge→落库→求助注入 全链真实贯通(本地,未接板子)。**
- ⛔ 落库→**跨机 POST→板子**:仍未验(板子未上线;`post_note`/写入口已编码,阶段3 联调时接)。

**输送逻辑待优化(判断,当前 `--store` 是最朴素落库,真实运行前要补)**
1. **幂等/去重**:重跑 replay 会重复插入同样的段(无去重键)。真实运行需幂等键(段指纹 / 已发送水位线),否则同一活动被反复入库。
2. **增量而非批量**:现在整份 frames 一次灌;实时应在**段闭合时逐条**发,并配**断线重试队列**(板子离线时本地缓存,恢复后补发)。
3. **project 跨会话稳定性**:`project_id=None`、任务身份靠 `project_hint` 文本;每次 replay 的 `t_00x` 重置,跨运行同一任务会被拆成不同分组。需稳定的 project 归并键(如按 project_hint 文本或语义归并)。
4. **两条 sink 策略统一**:本地落库无需过滤;一旦走板子 POST,**必须过 `should_transport`**(sensitive 不外发)。`--store` 与 `--post` 的红线策略要一致约定。
5. **失败/事务**:批量插入中途失败无回滚/续传;需事务或断点续传。
6. **时间戳来源**:note 用 `seg.start_ms`(真实发生时间)——正确,保留。

**HTTP 全链模拟(2026-07-18 · 本机 server,不接板子 · 真 Qwen)**
- 本机起真 `base_station.api.server`(板子同一套代码)→ `replay.py frames.jsonl --backend qwen --post http://127.0.0.1:8787` → **12 条真 Qwen note 经真 HTTP 落到 server 的 DB(0 失败,0 sensitive)**。
- 模拟求助:`POST /api/context/preview {"text":"帮我看看我当前工作的进度"}` → `scopes=['work']`、**5 条活动全带真 gist**——**这就是会拼给 OpenClaw 的 context**。链路打通到"给 OpenClaw 提供 context"为止(拼接+回答是 OpenClaw 内部的事,按约定不模拟)。
- 只新增 `replay.py --post`(复用 `bridge.post_note`);求助入口 `POST /api/context/preview`、`tools/send_frontend_message.py`(调 `XiaoAnBrain.handle_event`→ContextBuilder 读库)均为**仓库既有**,未重造。
- ⚠️ **新发现的限制(待优化)**:求助能否注入 work 上下文,由 `agent/core/context_policy.py` 的**关键词表**硬匹配决定(工作/项目/进度/在做什么/刚才/继续…)。**"在忙什么/最近忙啥"不在表里 → 不注入**。真实用户措辞多样,这个关键词门偏窄;优化方向:放宽关键词,或改由 OpenClaw 语义判断是否需要 work 上下文(而非本地硬匹配)。**属 OpenClaw/policy 侧,不在 screen-tracker。**

**阶段3 联调清单(A/B/C/D)**

A. 网络/环境
- [ ] PC 与板子(Intel DK-2500, Ubuntu)同一局域网;拿到板子 IP(`ip addr`)。
- [ ] 板子放行端口 8787(`sudo ufw allow 8787`)。
- [ ] PC `pc_screen_tracker/config.json` 填 `"board_base_url": "http://<板子IP>:8787"`。

B. 板子侧启动 API server(绑 0.0.0.0 才能跨机)
- [ ] `python -m base_station.api.server --host 0.0.0.0 --port 8787 --db-path agent/data/xiao_an.db --verbose`
- [ ] 首次用真实 xiao_an.db 打开 → 确认幂等迁移已补 `note` 列(`sqlite3 ... "PRAGMA table_info(work_activities)"` 含 note)。

C. 三级冒烟(先补 `replay --post` 发送端 / live runner,再跑)
- [ ] ①可达性:一条手造 note 走 `bridge.post_note` → 200 + 板子 `GET /api/work-activities` 可见。
- [ ] ②红线:`capture_policy="none"` 的 note → `post_note` 返回 `posted:False`,板子 DB 查无此条。
- [ ] ③全链:PC `probe_trace.py --out frames.jsonl` 采几分钟 → `replay.py frames.jsonl --backend qwen --post` → note 落板子。

**板子联调完成后的第一件事(用户已定,勿忘)**
- [ ] **前端加"今日工作轨迹/日报"面板**:`frontend/src/api/client.js` 目前没有 work-activities 调用(屏幕监控数据前端未接)。
  加 `listWorkActivities()`(GET /api/work-activities)+ 一个面板组件(参考既有 TasksPanel/MemoryPanel 范式),
  按 project_hint 聚合展示"几件事 + 每件事的 gist + 时长"——评委看得见的呈现主力。

D. 验收铁律(判据 3/4/5)
- [ ] 求助注入:板子 `POST /api/context/preview {"text":"帮我看看我当前工作的进度"}` → `context.work.recent_activities[].note` 含 gist。
- [ ] 不主动介入:灌数据全程 `GET /api/replies/latest` 恒 `available:false`,机器人不出声。
- [ ] 红线:板子 DB 无隐私软件正文,只有 full/meta_only 段的 gist 元信息。

## 13. 演示能力 · 可行性分析(2026-07-18 定稿)

### 13.1 杀手锏演示"指代消解"("刚才那个报错怎么回事"→ 不用贴报错,它已看见)——坑清单
1. **OpenClaw 延迟(最大坑,已证实)**:gateway 默认超时 90s;原仓库已有 `fast_demo_brain.py` + `docs/runbooks/fast_demo_mode.md` = 团队曾因 OpenClaw 慢给语音演示专造快速路。缓解:①延迟剧场化(等待期机器人 TTS"我看看你屏幕的记录…"+表情);②session 预热;③照 fast_demo 先例做"屏幕情境快速路"(超 N 秒切 Qwen 直接用 context 答,2-5s);④排练掐表>25s 默认走③。
2. **无 live 管线(隐蔽但致命)**:现在是离线两段式(采集→手动 replay);段"切走窗口/空闲"才闭合——人还停在报错窗口时该段未入库,问了=查无此事。演示动线必须"出错→切走→(理解入库)→再问";中期解 = **live runner(段闭合即理解即 POST),一切现场演示的前置件**。
3. **关键词门**:"刚才"可触发 work,但 policy 有"work 仅靠刚刚/刚才命中且他 scope 命中时丢弃 work"的规则——**演示台词逐句过 `/api/context/preview` 预检**。
4. **gist 未必含报错**(Qwen 概括概率性;<8s 停留被吸收;note 预览截 160 字)。缓解:固定动线(报错后停留 10s+),演示前实测。
5. **只注入最近 5 条**:报错后少切窗口、尽快问。
6. **演示日外部风险**:Qwen 免费额度(踩过 403)、现场网络、投屏画面被采集上云(脱敏未做)。缓解:付费/备用 key、干净桌面、脱敏突击。

### 13.2 日报/周报——可行性:高,几乎全现成件拼装
数据源已齐:app 级时长(`store.py` usage.db + `report.py`,含现成 `render_html`)+ 事件级(work_activities:任务/gist/时长/涉及 app/切换次数)。
日报结构(定稿):总在屏时长/最长专注/切换次数 → app 分布条 → "今天做了 N 件事"(标题+时长+涉及 app+gist 列表,隐私段标注"仅元信息")→ Qwen 一句话总结。
输出:Markdown/HTML(1-2 天量级);飞书=技术可行但需企业凭证+网络,**定为非必要**(讲"可推送",现场展示 HTML/前端面板);周报=每日数据落盘聚合,顺手。
**结论:当前性价比最高开发项(无板子依赖,评委共鸣强)。**

### 13.3 ⑤情境驱动执行 / ⑥灵感验证——可行性:机制已通,差工具
共同骨架 = 指代消解(✅已通)+ agent 工具执行。机制通路已有(`OpenClawDecision.tool_calls`→`ActionExecutor`);**缺的是工具本身**(manifest 只有机器人动作+note/task/reminder,无查资料/搜网页/写文档);且 agent 执行分钟级,不适合现场实跑。
最划算路径:打样**一个**工具 `report.generate`(对比表/资料摘要,底层可调 Qwen),同时服务⑤⑥,产出物为文档天然适合"预跑结果展示";现场只演"它听懂指令里的指代",执行成品放预跑。

### 13.4 开发优先级(定稿)
1. **日报生成器**(数据全现成,1-2 天,无板子依赖)→ 演示第一支柱。
2. **live runner**(段闭合即理解即入库)→ 13.1 坑2 的解,现场演示前置件。
3. **演示台词预检 + 延迟剧场化**(半天)→ 坑1/3 的解。
4. **执行工具打样 `report.generate`** → ⑤⑥最小可信证明。
5. **脱敏**(演示日风险项,可后置突击)。

## 14. L1-L6 优化迭代(2026-07-18,以 commit `946d795` 为回退点)

用户对六层各定一条优化愿景,逐层"定验收标准→实现→测→报告"迭代。每层结论如下(代码改动均已跑真实/合成测试验证)。

### L1 · 采集层:可度量正文质量(愿景:界定验收标准 + 自动 loop)
新增 `scripts/l1_quality_score.py`:按 browser/editor/shell/other 四类,量化 `content_coverage`(是否抓到内容)、`signal_ratio`(1-噪声行占比)、`relevance_hit_rate`(内容是否命中标题/URL 词)。
**基线(frames.jsonl,41 帧)**:browser 类 `coverage=0.68`(**32% 的浏览器帧 content 为空**,新发现,比噪声更该优先修)、`signal=0.84`;editor 类 `coverage=1.0 signal=0.97`(质量好);shell 类样本太少(2帧)。
**根因未深挖**:同一 GitHub 页连续 7+ 帧提取失败集中出现,疑似 `ui_extract.py` 的 UIA 提取在特定页面结构下失效——记为待办,需单独深挖,不在本轮改动范围。
**闭环自动调参 loop**(愿景的完整版)超出本轮范围,如实标注为下一轮工作,本轮交付的是"可执行的度量工具 + 基线",不是自动调参器。

### L2 · 段切分:语义漂移检测(愿景:合并逻辑还能再细)
新增：pass 1 之后加 `_split_drifted_runs` —— 同身份(app+url)运行中,若内容与"锚点帧"(第一个"足够丰富"的全文帧,内容量 ≥ 全场最大值一半,避免锚定在提取失败的劣质帧上)的 Jaccard 相似度持续走低(**需连续两帧确认**,防单帧噪声误判),判定话题真的变了,切一刀且标记为硬边界。
**过程中抓到一个真实误判并修正**:第一版单帧触发,把"同一 VSCode 窗口、frame0 只抓到标签栏文字+一条 Docker 通知(提取失败),frame1-4 抓到真代码"误判成话题漂移——本质是 L1 提取质量抖动,不是 L2 话题变了。改为"两帧确认+丰富度锚点选择"后消除该误判,真实数据仍保持 12 段基线。
新建 `tests/test_segmenter.py`(13 项,含 4 项漂移测试 + 1 项该误判的回归锁定测试)——此前该文件不存在,segmenter 此前只有"口头验证过"、无持久化测试。

### L3 · 理解层:task_closed 生效 + 任务状态持久化(愿景:触发/写库频率还能调)
**修了一个真实 bug**:`task_closed` 字段被 Qwen 输出、被 `_REQUIRED` 校验,但从未被读取/使用——任务只能靠 30 分钟空闲超时关闭,永远不会因"模型判断这件事做完了"而提前关闭。现已接上:`task.closed` 由模型判定写入,`_TaskState.active()` 排除已关闭任务。
**持久化**:`_TaskState`/`_Task` 加 `to_dict/from_dict/save/load`;`make_understander(state_path=...)` 可选加载,`replay.py --task-state <json>` 落盘。真 Qwen 三次连续运行实测:第二、三次运行**全部段落关联到已有任务 t_001-t_004,零新建**——证明跨进程重启同一件事不再被拆碎。
触发/写库频率本身(§14 愿景里的"多久调一次 Qwen、几次写一次库")维持"段闭合即调用即写"的现状,未改——这是节奏问题,任务状态持久化解决的是"节奏不变但记忆不丢"。
**代码审查后补修(发现1)**:延续判断 `if pid != "NEW" and state.get(pid)` 原本**不检查任务是否已关闭**——已关闭任务虽不出现在 active_tasks,但 JSON 模式下模型仍可能回显其旧 id(active_tasks 为空时猜 "t_001"),导致**已完结任务被复活、无关新片段套上其标题**,削弱了 task_closed 修复本身的价值。已改为"延续目标必须存在**且未关闭**",否则视同未知 id 开新任务;加回归测试 `test_closed_task_cannot_be_revived_by_stale_pid` 锁定。此修复只在异常路径生效,真 Qwen 正常全链仍是 12 段→12 note、行为零变化。

### L4 · bridge:幂等写入(愿景:落库会不会重复/占空间)
无法给 `work_activities` 加唯一约束(需再动 schema,超出本轮授权范围),改为**客户端去重账本** `DeliveryLedger`(`bridge.py`):以 `(timestamp_ms, source, app_name, window_title)` 做指纹,`post_note`/`replay.py --store` 均可选传入,已投递过的直接跳过。
**实测**:同一份 frames 用同一账本跑两次,第二次 `0 条新写入,12 条已投递过跳过`,库内行数保持 12(不是 24)。回答了用户"落库会不会很频繁占空间"——写入本就按段闭合触发、不按帧,频率不高;真正的风险是**重复写**,现已被幂等账本挡住。

### L5 · 存储层:去冗余 + 保留策略(愿景:评估精简 + 冷热策略;本轮定位=设计,非强制迁移)
**量化冗余**:一条 work_activity 写入产生两行——`work_activities`(约 426 字节/行)+ `memory_events`(约 297 字节/行,其中 **78%(232 字节)是与 work_activities 列完全重复的字段**:app_name/window_title/activity_type/project_hint/note/confidence/duration_seconds)。
**为什么本轮不强制精简**:`GET /api/memory/recent?event_type=work.activity` 是已上线的公开读接口,原样吐出 `payload_json`;仓库内没有消费方读这些重复字段(已 grep 确认),但**无法排除 OpenClaw 或评测工具在仓库外依赖它**——贸然删字段有破坏外部隐性契约的风险,这类判断超出我能核实的范围,故不擅自改,只给设计。
**设计建议(留给下一轮决策)**:
1. 精简路径:给 payload 加 `schema_version` 标记,新版本只保留非重复的补充字段(如有),重复字段留给调用方经 event_id JOIN work_activities 取,过渡期两个版本共存。
2. 冷热保留策略(分层):热(work_activities 原始行,保留 N 天,如 30 天)→ 温(按 project_hint 聚合的任务级摘要,保留数月)→ 冷(日报/周报文本,永久)。原始行到期后由日报归档替代,防止库无限增长。
3. 落地时机:建议与"日报生成器"(§13.4 优先级1)一起做,因为日报本身就是冷层数据的产出物,顺路。

### L6 · ContextBuilder:关键词门 → 更语义化匹配(愿景:能不能调库/ContextBuilder 能不能写给 OpenClaw)
`agent/core/context_policy.py` 的 `WORK_CONTEXT_KEYWORDS` 补充 14 个真实常见措辞("在忙什么/忙什么/在干什么/干什么/在干嘛/干嘛/在干啥/干啥/在弄什么/在搞什么/最近在干/最近在忙/我的屏幕/我在看什么"),并在类文档处正式记录长期待办——**关键词硬匹配终将不够用,真正的解应是交给 OpenClaw 语义判断这轮对话要不要 work 上下文**,本轮只做"扩大覆盖面"的低风险修补,不动架构。
新增回归测试(`tests/unit/test_context_policy.py`)锁定此前**真实翻车的原句**;既有 21 项测试全过,无回归。
**端到端实测**(起本机 board server,真实 POST 灌库):此前 `"帮我看看我最近在忙什么"` → `scopes=[]、0 活动`;修复后同一句 → **`scopes=['work']、5 条活动全带 gist`**——直接回答了用户"ContextBuilder 能不能写给 OpenClaw"的疑问:能,且现在覆盖的日常措辞明显更广。

## 15. L1-L6 迭代总结

六层全部按"定标准→实现→测→报告"跑完一轮,均有自动化测试或真实数据验证(无一条是"看起来对"就算过关)。**发现并修复 4 个真实 bug**(L2 segmenter 从未有测试文件、L2 锚点误判、L3 task_closed 校验了但从不生效、L3 已关闭任务可被旧 id 复活[审查发现1])、**新增 2 项可复用机制**(L3 任务状态持久化、L4 幂等投递账本)、**量化 2 处此前只有印象没有数字的问题**(L1 采集质量基线、L5 存储冗余占比)。

**代码审查留档的已知项(未修,供下一轮决策)**:
- 发现2 · L6 新增单字级关键词("干嘛/干什么/干啥")召回上去了但**误触发面变宽**:`"你在干嘛"`(问机器人自己)、`"这是干什么用的"` 也会触发 work 注入。后果无害(只多注入上下文、不触发动作),属"宽召回优先"的自觉取舍;根治靠 L6 长期解(OpenClaw 语义判断)。
- 发现3 · 账本/任务状态**只在 run 结束时落盘一次**:离线 replay 中途崩溃 → 已插库但账本未记 → 下次重跑会重复插。对离线影响小;**live runner 必须改成逐条/分批落盘**,跟着 live runner 设计走。
- 发现4(小)· 漂移锚点的 50% 丰富度门槛:若一段 run 里"短但真实"的话题A 字数 < 后续话题B 的一半,锚点会选到 B,A 段漂移漏检。合成边角情形,真实数据未见,影响低。
- 指纹不含内容:先 rule 跑占了账本 → qwen 重跑更好的 gist 会被当"已投递"跳过。使用约定=换后端前清 `--dedup-ledger`,或加"内容变化允许覆盖"路径,待定。

本轮**不做**、留给下一轮的:L1 自动调参闭环、L1 的 UIA 提取失败根因、L5 的 payload 精简迁移与冷热分层落地、L6 的语义判断(需 OpenClaw 侧配合)、以及上面 4 条审查留档项。
回退点:commit `946d795`(本轮迭代前)。本轮迭代 + 审查发现1 修复已由后续 commit 固化。
