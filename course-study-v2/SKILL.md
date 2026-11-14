---
name: course-study-v2
description: 仅当用户明确选择 course-study-v2 或“新版课程助手”时使用。整合学习通、中国大学MOOC的网课续跑、任务巡检、读题与已授权测验，以及大学作业取题、解答、验算、PDF交付和存档；按ZCode、Codex、DeepSeek Harness、豆包工作、WorkBuddy或Trae当前工具选择操作方式。旧版技能继续独立使用。
---

# 新版课程助手

这是独立试用版。先确定本次任务，再读取所需流程与平台知识；不要一次加载所有参考文件。
本技能的安装目录是资源根，脚本和引用均相对它解析；运行数据另放本次任务目录。

## 开始与路由

1. 确认实际 harness 和可用工具：ZCode 读 [ZCode适配](adapters/zcode.md)，Codex 读
   [Codex适配](adapters/codex.md)，DeepSeek Harness 读 [DeepSeek适配](adapters/deepseek.md)，
   豆包工作桌面端读 [豆包适配](adapters/doubao.md)，WorkBuddy 读 [WorkBuddy适配](adapters/workbuddy.md)，
   Trae 读 [Trae适配](adapters/trae.md)。
   按当前会话实际加载的技能根判定宿主，不因磁盘上存在同名副本就假定已加载。
   以当前工具文档为准，不能仅因存在同名工具就假定接口相同。
   浏览器必须有可用、受支持的操作通道；缺少能力时按适配说明回退，不自行寻找隐藏调试接口。
2. 确定本次平台、课程、账号别名、任务类型和已有授权。续跑先读本次状态、当前平台和现有进程，
   已明确的信息及授权不用重复询问；新任务身份或范围不明时再补齐。
3. 根据任务只读必要材料：

   | 任务 | 流程 | 平台知识 |
   |---|---|---|
   | 看课、续跑、弹题、课程测验 | [网课流程](references/course-flow.md) | [学习通](references/chaoxing.md) / [中国大学MOOC](references/icourse163.md) |
   | 查看或下载作业、参考解答、验算、交付 | [作业流程](references/homework-flow.md) | 学习通共用同一份知识；智慧树另读 [Polymas](references/polymas.md) |
   | 有无新课件/作业/测验、截止时间 | 网课/作业流程的列表巡检 | 先停在列表；取题和开始测验是后续独立动作 |

4. 使用独立任务目录，记录账号别名、课程键、当前标签/执行器、已有授权、进行中的测验和证据。
   格式见 [状态与交接](references/state.md)。旧版断点可只读参考，不能替代平台核验。

## 全程保留的边界

- 同一账号一次只由一个执行器操作。切换新版、旧版或浏览器方式前保存断点并确认前一个执行器已停。
- 学习通正常播放，锁速接受1x；中国大学MOOC按该平台知识选择原生进度条或正常播放。
  不伪造心跳、学习上报或修改进度接口。静音优先，低音量回退只按学习通知识的短试流程使用。
- 课件完成要有平台保存的完成标记；视频到尾、旧状态或本地高分都不是课程完成证明。
- 网课测验按本次已有作答/提交授权执行；只看题或只给参考答案不自动扩展成开始计时、填答或提交。
  作业模式默认保留原作业流程的“参考解答、用户自行提交”边界，不套用网课的提交规则。
- 计时测验已经开始时优先完成或保存该次事务；结果不明先查平台记录，不重开尝试或重复提交来验证。
- 验证码、安全验证、付费或权限限制按平台与当前工具规则处理，需要用户接手时保留现场。
- 本机保留状态、材料与日志；密码不回显，登录态和私人运行数据不进入公开导出。

## 可复用工具

先运行 `python -X utf8 scripts/doctor.py` 确认实际解释器、可选依赖和资源。工具不是授权来源。

- [题面采集](scripts/collect_questions.js)：仅在当前工具允许页面脚本时，在已打开且已授权的题目帧读取DOM和内嵌字体。
- [离线读题](scripts/question_reader.py)：`doctor` / `render` / `ocr`；见 `--help`，只输出题面及复核材料。
- 字幕复用、逐选项原文预检和 OCR 漏题补读：遇到缺证据、混淆题面或反复取材时读 [证据与效率](references/evidence-efficiency.md)，不把词面命中当答案证明。
- [列表采集](scripts/collect_task_list.js)：只读当前已加载任务列表；不点击、导航、播放或提交。
- [采集函数生成](scripts/browser_payload.py)：生成 page/element evaluate 函数，通过显式参数传入来源与选择器，不写页面全局变量。
- [巡检对比](scripts/inspect_tasks.py)：`summary --input ...`、`diff --before ... --after ... --out ...`。
- [交付闸门](scripts/delivery_gate.py)：按 [交付说明](references/homework-output.md) 验证产物，不代替解题与视觉复核。
- [静音信标](scripts/keepalive.beacon.js)：可选、需工具允许注入；不写倍速、不调用播放。
- Codex 当前视频静音与播放控件操作见 [Codex适配](adapters/codex.md)，使用独立脚本；ZCode 保留自身原有播放与静音路径。
- Codex 续跑、紧凑观察与视口/最小化验证见 [Codex运行说明](references/codex-runtime.md)；观察只读，动作与平台完成分别验收。
- [Harness探针](scripts/dsh_probe.py)：`--tools` 读当前工具清单，报告技能发现根、安装副本漂移和浏览器候选；
  支持整包清单自检与 `--require-discovered/--require-winner/--require-clean`。只读文件系统，不联网、不打开页面；DeepSeek 外部浏览器通道与独立技能边界见 [DeepSeek适配](adapters/deepseek.md)。

题面和列表的采集函数不自动执行，调用方式及契约见 [工具数据格式](references/tool-data.md)。用新批次隔离题面和字体；
工具失败可回到当前明文、受支持截图或人工复核，不能把旧题图当成成功读题。

## 验收与回退

本次交付前分别说明：平台已确认什么、文件工具验证了什么、尚有哪些内容待人工或实战核对。
安装副本与源码是否一致用 `scripts/dsh_probe.py` 核对；该探针的发现顺序只覆盖 DSH 视角，
WorkBuddy 的实际加载路径按 [WorkBuddy适配](adapters/workbuddy.md) 核实。
缺少受支持浏览器通道时写明缺口和需要启用的能力，不宣称实战通过。
兼容状态见 [验证说明](references/validation.md)，本机来源与已有资料位置见 `local/`。

旧技能保持独立。本版失败时保存自身状态，核对平台是否已发生动作，再按
[回退说明](references/rollback.md) 交给旧版继续；不复制覆盖旧版状态，也不把两版同时挂起运行。
