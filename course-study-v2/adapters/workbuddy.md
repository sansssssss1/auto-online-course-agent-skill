# WorkBuddy 适配

明确选择 `course-study-v2` 后，在 WorkBuddy（Windows）按本页执行。通用边界（单执行器、不伪造心跳、
平台完成标记为准、测验/作业授权分级、登录接管）统一遵循 [SKILL.md](../SKILL.md)「全程保留的边界」。
本页只写 WorkBuddy 特有事实：**路径、工具面、运行时，以及本会话实际观测到的结论**。

> **首次探测（2026-11-07 15:13，北京时间）**：本页工具缺失记录是该次会话快照，恢复时需重新检查。
> **WorkBuddy 通道下没有任何学习通登录、播放、弹题、测验、提交或平台验收记录**。
> [豆包工作实战记录](../references/validation.md#豆包工作实战记录2026-11-06-至-11-07)属于另一宿主，
> 其成功结果一律不计入本页；Codex / ZCode / DSH 的记录同理。

## 1. 资源根、安装发现与独立运行目录

| 角色 | 路径 | 说明 |
|---|---|---|
| 维护源（Git，唯一更新来源） | `C:\<SOURCE_DIR>\course-study-v2` | 本轮改动在此提交 |
| 共享安装副本（release） | `%USERPROFILE%\.agents\skills\course-study-v2` | 带 `package-manifest.json` 白名单与 SHA-256 |
| 历史快照（**禁止**作为更新来源） | `D:\<OLD_DIR>\course-study-v2` | 仅用于确认存在，不读、不覆盖 |
| WorkBuddy 用户级技能发现根 | `%USERPROFILE%\.workbuddy\skills` | 会话启动时扫描 |
| WorkBuddy 项目级技能发现根 | `<workspace>\.workbuddy\skills` | 当前工作区下不存在 |
| 本次独立运行目录 | `runs\workbuddy-new-account-20261107\` | gitignored，与技能目录分离 |

- **本会话实测**：用户级发现根内只有 `zaohua-builder-usage`，项目级发现根不存在，
  因此 **WorkBuddy 本会话没有通过技能发现机制加载 `course-study-v2`**。本轮是显式读取维护源的
  `AGENTS.md` / `SKILL.md` / `references/` 后按文件执行，不是宿主自动加载技能的结果。
  报告「实际加载的技能路径」时应写这一事实，不能写成已加载 `.agents/skills` 副本。
- `scripts/dsh_probe.py` 的 `ROOT_ORDER` 是 `project-dsh / project-agents / custom / user-dsh /
  user-agents`，**不扫描 `.workbuddy\skills`**。本会话运行它得到 `winner = user-agents`
  （`%USERPROFILE%\.agents\skills\course-study-v2\SKILL.md`）、`harness = deepseek-harness`，
  这只证明 DSH 视角下的文件系统发现顺序，**不能证明 WorkBuddy 加载了正确副本**。
  判定 WorkBuddy 加载路径一律以宿主技能发现根与会话技能列表为准。
- 按技能名发现时，将 release 安装到 `%USERPROFILE%\.workbuddy\skills\course-study-v2`，
  共享 `.agents` 副本不能代替此步骤。目标不存在或为空时，在维护源运行：
  `python -X utf8 scripts/package_skill.py install --target "<WorkBuddy技能根>/course-study-v2"`。
  已有目标先备份，再按清单同步并核对哈希。使用本地 `install`；公开 `export` 的脱敏检查不是本地安装前置。
  安装后在 WorkBuddy「专家·技能·连接器 → 技能 → 已安装」检查启用状态；当前任务未刷新技能时，
  新建任务并显式选择本技能，再读取本次恢复摘要。安装目录存在与宿主实际加载分别验收。
- 运行材料（账号别名、课程配置、`state.json`、题面批次、字体、截图、证据、恢复摘要）只放本次
  独立运行目录；不写进技能目录，不继承其他账号的课程 ID、进度、测验尝试、答案、字体映射、
  登录态或浏览器句柄。`course-study-dsh` 与 `mooc-agent-skill` 保持独立，不在本版读写范围。

## 2. 工具面与运行时（首次会话快照）

本表保留15:13首次探测；安装浏览器组件后的能力已变化，恢复结果与实际接口见§3。

| 能力 | WorkBuddy 当前接口 | 结论 |
|---|---|---|
| 文件读写 | `Read` / `Write` / `Edit` / `Glob` / `Grep`，绝对路径优先 | 可用，已实测 |
| 命令执行 | `Bash`（Git Bash，`/usr/bin/bash`）；另有 `PowerShell`（Windows PowerShell 5.1） | 可用。**默认 Shell 是 Bash，不是豆包适配里的 PowerShell**，`env.ps1` 那套点源写法不适用 |
| Python | `%USERPROFILE%\.workbuddy\binaries\python\versions\<ver>\python.exe`，实测 3.13.14 | UTF-8 文本一律 `python -X utf8` |
| Node | `%USERPROFILE%\.workbuddy\binaries\node\versions\<ver>\node.EXE`，实测 v22.22.2 | 可用 |
| Typst | 实测 0.15.1 | 可用（作业 PDF 排版） |
| 网页抓取 | `WebFetch` / `WebSearch`：仅公开文本页 | 不能登录、不能保持会话、不能读课程 iframe，**不能替代浏览器通道** |
| 看图 | `ViewImage`：只能查看**本地已存在的图片文件** | 可用，但本会话无网页截图工具为其产出图 |
| 网页截图 / 下载 / 页面脚本 / 跨帧读取 / 登录接管 | 本会话无对应工具 | **缺失**，见 §3 |
| 浏览器通道 | `workbuddy-browser-use` 未出现在本会话可用技能列表；工具检索未发现 navigate / click / evaluate / screenshot 类接口 | **缺失**，见 §3 |

`scripts/doctor.py` 本会话实测结果：核心 `resources` 全部存在；**首次运行时可选依赖
`PIL` / `fontTools` / `rapidocr_onnxruntime` / `onnxruntime` / `pymupdf` / `pypdf` / `reportlab`
均未安装**，`render_ready=false`、`ocr_ready=false`。按本次任务已补装 Pillow 13.0.0 与
fontTools 4.68.0（字形渲染、图片拼合所需）并复跑 `doctor.py` 确认 `render_ready` 转为可用；
OCR 引擎与 PDF 检查库仍按需补齐，不沿用历史安装状态。
`doctor.py` 的 `browser.checked=false`，它不探测浏览器，也不代表浏览器可用。

## 3. 浏览器连接、跨帧、截图、下载与登录接管

- **优先使用当前受支持的浏览器通道**。启用后先读该通道自身的工具文档再操作；
  **不套用**豆包的 `aha_browser_use`（`bu.snapshot/css/read_all/js/screenshot/download`）、
  Codex 的 `mcp__cua_repl` / `playwright.evaluate`、DSH 的外部 Chrome/MCP 参数。
  不自行寻找隐藏调试端口、CDP 或其它宿主的 client。
- **首次会话实测缺口**：当时无网页导航、点击、输入、跨帧读取、页面脚本注入、网页截图、附件下载工具。
  替代方式只能覆盖公开文本页（`WebFetch`）与本地文件整理，**无法完成登录、读目录、起播、作答与验收**。
  该次平台闭环记为**未执行**；组件安装后的无账号网页验证见下方，课程闭环仍待执行。
- **内置浏览器恢复路径**：WorkBuddy「设置 → 智能体 → 浏览器操控 → 让 WorkBuddy 控制浏览器」
  点击「安装」。本机5.9.3首次检查时组件未安装，后经用户授权已安装v1.2.1并启用。安装后在任务中核实
  导航、页面读取、截图等实际工具；仅凭某个同名Skill是否出现，不能判定整个浏览器通道可用性。
  WorkBuddy内置浏览器无需Chrome/Edge/QQ扩展；仅当选择控制这些外部浏览器时安装对应扩展。
  依据：[官方浏览器说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Right-Sidebar)。
  新账号优先使用已确认隔离的内置浏览器会话；独立会话能力仍按实际工具核实，不能假定与日常浏览器共享登录态。
  iframe、页面脚本、元素截图、下载和等待需按启用后的接口逐项验证，再补写本页契约。
- **同一会话恢复验证（2026-11-07）**：原适配会话通过工具检索加载了官方浏览器工具，无需新建会话，
  已打开 `https://example.com` 并取得显示正文的视口截图。当前只证明基本浏览器通道恢复，
  不把无账号页面样本当作课程登录、跨帧或媒体控制验收。
- **官方接口入口**：先读取已安装的 `workbuddy-browser-use/SKILL.md`，按当前工具检索结果调用
  `mcp__browser__browsers_list` → `browser_info`。内置浏览器名称为 `WorkBuddy Browser`、
  类型为 `desktop`；每次使用实际返回的浏览器标识。新页用 `tabs_new`；已有页先 `user_open_tabs`
  再 `tabs_claim`，只接管当前会话提供的标签页。DOM读取使用 `dom_cua_get_visible_dom`，
  点击/输入使用 `dom_cua_click` / `dom_cua_type`；导航后重新获取节点标识。
- **正文与截图实测限制**：`dom_cua_get_visible_dom` 在 example.com 样本中仅返回交互元素，
  缺少段落不等于页面无正文。可用 `tab_screenshot` 的默认视口截图读取可见正文；
  整页截图请求被当前控制器拒绝后，改默认视口参数即成功，不重复请求同一不支持参数。
  本轮工具检索未提供页面JavaScript evaluate / innerText接口；不能把已能导航和截图解释为可执行采集脚本。
  URL与标题分别用 `tab_url` / `tab_title` 回读；本轮 `tabs_finalize` 已保留验证页。
- **登录接管**：需要扫码、短信或人工验证时，展示真实页面并等待用户完成，之后**重新读取账号身份**；
  不代输密码、不绕过验证、不打印含凭据的整页快照。新账号使用受支持的独立浏览器会话或配置文件，
  保留其他任务正在使用的会话；账号不符时先停下，不继续动作。
- **跨帧**：基本网页样本未验证 iframe。先确认同源/跨源帧的实际能力，再决定用 DOM 快照
  还是页面脚本；学习通目录、学习页、题目帧的选择器线索见 [学习通知识](../references/chaoxing.md)，
  现场表现优先于历史选择器。
- **截图与下载**：接收受支持通道返回的原生图片内容或文件。视口截图实测返回内嵌图片，
  未返回文件路径时记录 `path=null` 与图片尺寸；仅后续离线处理需要时才使用宿主支持的保存方式，
  无需为完成截图验收遍历缓存。文件形式再用 `ViewImage` / `Read` 查看。课程附件下载仍未验证。

## 4. 题面、列表及媒体状态采集

- 复用既有离线工具：`scripts/browser_payload.py` 生成 `(document, options)` 或 `(options)` 只读函数、
  `collect_questions.js` / `collect_task_list.js` 采集题面与列表、`inspect_tasks.py summary/diff`
  对比快照。页面采集函数仅在通道提供evaluate时执行；当前v1.2.1工具面不提供该接口。
  回退为读取DOM交互元素与真实截图，按同一数据格式整理题面、选项和列表，再使用离线工具。
  字体和图片材料无法取得时保留缺口，不把乱码或未读全的截图标成完整题面。
- 列表对比要求 `platform` 与整个 `scope` 一致。**账号别名、课程键未确定时不得填入其它账号的值**，
  空列表写 `authoritative=false`，不推断「全部完成」。格式见 [工具数据](../references/tool-data.md)。
- 混淆字体与图片选项按**当前题目批次**处理：`glyph_map.py` → 人工 mapping → `decode_batch.py` →
  `build_merge_manifest.py` → `merge_images.py`（先拼合、只读拼合图）。mapping 不跨批次复用；
  这些 CLI 依赖 Pillow / fontTools，补齐后才可运行，本会话无真实题面可验证。
  推断结果不得写成课程原文或字幕证据。
- **媒体状态回退（待课程单节点实测）**：当前通道不能读取JS `currentTime`，可用两次真实截图中的
  播放器可见时间和播放/暂停控件核对推进；先确认当前章节、视频部件与选中媒体一致，记录观测来源为可见控件。
  时间面板或媒体身份不可辨认时保留未知，不能用本地计时、等待命令或进程存活冒充播放观察。

## 5. 播放观察、超时恢复与会话续接

- 学习记录必须由**平台原生界面与播放器**产生：真实控件静音起播、锁速接受 1x、不写倍速、
  不伪造心跳或进度上报。健康判据是两次真实媒体观察间的播放时间推进；有脚本通道时读 `currentTime`，
  当前通道按§4核对可见时间控件。`readyState`、`visibilityState` 或工具调用成功不能代替播放推进。
- 观察超时后**先只读回读现场**；仍在播放就继续观察，**不重新起播**。暂停时先查弹题、解码错误、
  登录态、标签与视频身份，再做一次恢复并回读。
- **豆包参数一律不迁移**：`observe_loop` 的 `rounds`/`interval`、单单元格约 110–120 秒墙钟截断、
  「最多 3 轮×55s」、每单元格 `bu.` 动作数均值 ≥ 2.5、调用次数目标，都是豆包单元格环境的经验值。
  WorkBuddy 的轮数、间隔与超时须在浏览器通道启用后按该通道的实际工具文档与超时**重新确定**；
  未实测前本页不写具体数值，也不设调用次数目标。
- **会话续接**：先读运行目录的 `run-context.md`（恢复摘要）与 `state.json`（业务断点），
  再核对平台现场，不把历史完成声明当作现状。`scripts/sync_context.py` 是纯文件工具，
  可用于动作完成后同步状态与摘要；本会话未在任何真实平台节点上调用它。
- 同一账号同一时间只由一个执行器操作；切换执行器或浏览器方式前保存断点并确认旧执行器已停。
  后台、最小化、锁屏、进程退出是四种不同条件，须分别实测；无现场证据一律保留「未验证」。

## 6. 作业生成与交付

- **本次作业需求未定，未执行任何取题、解答、PDF 渲染或交付**，作业授权不从课程测验授权推导。
- 需要时按 [作业流程](../references/homework-flow.md) 与 [交付说明](../references/homework-output.md)：
  取题 → 解答 → 独立验算 → Typst PDF（本机 0.15.1 可用）→ 逐页渲染看图 → 用**真实 manifest**
  跑 `scripts/delivery_gate.py` 并保留原始 `GATE: PASS`。PDF 页数/文字层检查所需的
  `pymupdf` / `pypdf` / `reportlab` 本会话未安装，执行前按需补齐并复跑 `doctor.py`。
- 作业默认只提供**参考解答，由用户自行提交**；生成能力的 PS 或排版工具不能伪装成软件运行截图。

## 7. 已验证结果与尚未覆盖的条件

**首次会话已验证（均为本地事实，非平台结果；恢复后的浏览器能力见§3）**

- 维护源、共享安装副本、历史快照三者路径与角色；源码 `git status` 干净。
- WorkBuddy 用户级/项目级技能发现根的实际内容；本会话未通过技能发现加载本技能。
- `dsh_probe.py` 的发现顺序不覆盖 WorkBuddy 发现根；其 `winner` 结论不能迁移。
- Shell、Python、Node、Typst 的实际版本与路径；`doctor.py` 的资源与依赖清单。
- 当前工具面：文件读写、命令执行、本地看图、公开网页抓取可用；浏览器操作、跨帧读取、
  页面脚本、网页截图、下载与登录接管不可用。
- 离线脚本可解析运行（见本轮聚焦检查结果）；**离线测试通过不等于实战通过**。

**尚未覆盖 / 未验证**

- 学习通登录与账号身份回读、扫码/验证码接管；新账号独立建档的实际内容（别名与课程待补）。
- 课程目录、已发布任务初始清单、平台完成标记的任何一次读取。
- 视频起播、媒体身份核对、静音 1x 播放、时间推进、弹题处理、超时恢复与刷新后完成标记。
- 题面批次、混淆字体解码、图片选项拼合、选项真实标签与选中态核对，在 WorkBuddy 通道下的实战。
- 章节测验读题、填写、保存、单次提交与成绩/提交记录回读；作业 PDF 与 `delivery_gate` 实战。
- 网页截图、附件下载、跨源帧读写；后台、操作系统最小化、锁屏、进程退出后的运行能力。
- 中国大学 MOOC、Polymas、每日任务点上限触发处理。

**按依赖恢复**：先完成技能安装、浏览器组件配置和无账号页面的通道检查，这些步骤不依赖课程信息。
账号别名可新建为 `workbuddy-new-account`，待登录后绑定本次身份；不得用别名代替身份确认。
随后仅补齐目标课程与本次任务范围。视频按技能的平台策略，作业未指定时不启动作业任务；
测验填写与提交只影响对应步骤，授权未明确时保留只读，不阻塞已授权的视频或文档工作。
登录并只读核对账号身份、课程和初始清单后，先验证一个已授权节点，再继续范围内任务。
不把填写完全部模板字段作为环境修复、登录准备或离线工作的统一前置。
