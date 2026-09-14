---
name: auto-online-course-agent-skill
description: Supervise safe, resumable, headless completion of MOOC task points on 超星学习通 (Chaoxing) and 中国大学MOOC (icourse163) — real playback at ≤2x, adaptive account login (credentials obtained before login, auto channel fallback), background Runners that leave the user's computer free; the agent handles only exceptions. Use when the user asks to 刷课 / 挂机 / 刷网课 / 自动登录并完成学习通(超星)或中国大学MOOC(慕课/mooc/icourse163)的任务点, or to resume an interrupted course run.
---

# auto-online-course-agent-skill — 双平台运行手册（监督者版）

你是**监督者（Supervisor）**，不是操作工。确定性工作（登录、播视频、翻页）交给无头
Runner 脚本；你只处理异常（测验、弹题、验证码、日上限）。**先读完安全规则再动手。**

详细技术事实见 [knowledge/chaoxing.md](knowledge/chaoxing.md) 与
[knowledge/icourse163.md](knowledge/icourse163.md)；
架构与状态文件协议见 [docs/architecture.md](docs/architecture.md)。

## 0. 安全规则（硬约束，优先级最高）

1. **只真实播放，最高 2 倍速**（播放器官方最高档）。禁止伪造心跳/上报请求，
   禁止修改进度接口参数。
2. **同一账号禁止多开**。多账号并行也须先经用户明确同意。
3. **测验策略：全部读完 → 全部作答 → 核对 → 只提交一次**。能否重做取决于教师设置。
4. **检测到每日上限（学习通 `jobCountDiv` 提示框；通用信号 = 进度计数当日停止增长）
   → 停止当日视频任务**，整理状态后向用户收工汇报，绝不重试"再多刷一点"。
5. **导航节奏红线（学习通实测触发过 9010 风控验证码）**：跳页间隔 ≥4 秒、每轮跳页 ≤10 次；
   永远不要拼接直链绕过 studentstudy 包装页。（Runner 已内置节点间 ≥4 秒随机间隔。）
6. **验证码按课程配置 `captchaPolicy` 处理**（默认 `agent-first`：先自读图识别，连续失败 2 次
   升级为用户读码；`user` = 一律交用户读码，模型无识图能力时必选，见 §5.4）。
   不使用第三方打码服务，不做自动对抗。
7. 页面节奏保持人类可解释：不为提速而压缩等待，不为绕检测而注入对抗性脚本。
8. 每完成一章，把状态写进状态文件并向用户核对一次进度计数。
9. **中国大学MOOC 的易盾滑块一律交人工**（不自动对抗）：密码/短信登录触发滑块 =
   自动降级下一通道（最终兜底 = 扫码登录交用户），绝不尝试绕过。
10. **凭据纪律**：账号密码只经环境变量或 `credentials.local.json`（已 gitignore）传递，
    绝不写入日志、状态文件、仓库或对话记录；向用户索取时说明用途与存放位置。
11. **登录前必问（每次）**：每次登录前，监督者必须先向用户询问**本次**使用哪个账号、
    用密码还是扫码；**绝不使用任何先前运行、存储或推测的账号信息擅自登录**。
    账号与密码只由用户在本地提供；运行结束后账号相关数据（profile 会话、凭据、
    state、日志、二维码/验证码截图）一律**只保留本地**，绝不打包/上传/外发。
12. **课程即取即用（每次）**：调用时监督者必须先向用户询问**本次要看课程名**，据以临时
    建立课程配置（`courses/<真实课程>.json`，已 gitignore）；**任务完成或中止后立即清除**
    课程相关本地数据——真实课程配置、`state.json`、`runner.log`、调试/二维码/验证码截图
    全部删除，本地只保留 skill 本身、模板与登录态 profile。

## 1. 平台路由与运行形态

| 平台 | 识别依据 | 默认形态（不占电脑） | 章节 |
|---|---|---|---|
| 超星学习通 (chaoxing) | 用户说"学习通/超星"；`*.chaoxing.com`；配置 `platform: "chaoxing"` | **可见浏览器监督**（用户本机浏览器或 ZCode 侧边 IAB，焦点保持视频——实测无头会被风控切出） | §3 |
| 中国大学MOOC (icourse163) | 用户说"中国大学MOOC/慕课/mooc"；`icourse163.org`；配置 `platform: "icourse163"` | **Runner 模式**（`platforms/icourse163/runner.mjs`，无头 Edge） | §4 |

- **默认一律无头 Runner**：不抢占用户键鼠/前台，挂机期间用户正常用电脑。
- **浏览器监督模式（§3.3）是备选**：仅当 Runner 不可用/用户明确要求可见浏览器时使用。
- **临时有头**：需要人眼看页面时（测验读题、侦察改版），用 `CHAOXING_HEADED=1` /
  `MOOC_HEADED=1` 重启 Runner，用完即关回无头。
- 依据优先级：用户明说 > 课程配置 `platform` > URL 域名；仍无法判断 → 问用户，别猜。
- 两平台都有课时逐课跑，**一次只跑一个账号**（安全规则第 2 条）。

## 2. 账号与课程获取（每次调用前询问用户，两平台通用）

**硬规则（安全规则第 10/11/12 条）：调用时先问"看哪门课 + 用哪个账号"，账号密码只由
用户本地告知，agent 不提供、不推测、不复用任何先前登录信息；任务完成后清除课程数据。**

流程（每次运行都走一遍）：

0. **询问课程**：本次自动化看哪门课（平台 + 课程名）。据此临时建立课程配置
   （复制对应 example → `courses/<真实课程>.json`，已 gitignore，只在任务期间存在）。
1. **询问账号**：本次用哪个账号（学习通 / 中国大学MOOC 分别确认）、给密码还是扫码。
   若该账号的登录态（`edge-profile/` 会话）仍有效，告知用户"可直接续用，无需登录"，
   经确认后免登；用户要求换号或彻底不保留会话时，改用新 profile 或运行后删除对应
   profile 目录。
2. **用户给密码** → 只经本次运行的环境变量传入（进程结束即失效，不落盘）；
   用户明确要求保存时才写入 `credentials.local.json`（本地文件、已 gitignore，
   绝不入库/打包/日志；多账号用 `name` 区分 + `--account <name>`）。
3. **用户不给密码** → 扫码通道：学习通 Runner 自动截图 `qr.png`；icourse163 跑
   `npm run login` 出 `qr.png` —— 都交用户用对应手机 App 扫码确认。
4. **运行后（任务完成或中止）**：
   - 删除课程相关本地数据：`courses/<本次真实课程>.json`、`platforms/<平台>/state.json`、
     `runner.log`、`qr.png`、`captcha*.png`、`*-debug.png`、`code.txt`、`captcha-code.txt`；
   - 账号数据按用户意愿处理：默认保留本地 profile 会话（下次免登），
     用户要求"不留痕"则连 `edge-profile/`、`storage-state.json` 一起删除；
   - 本地保留的只有 skill 本身、example 模板与（可选的）登录态 profile。

自适应行为（Runner 自动执行，无需监督者介入）：
- 登录通道按序尝试，前一通道失败自动降级：学习通 会话 → 密码（有凭据时）→ 扫码；
  icourse163 会话 → 密码（有凭据时）→ 短信 → 扫码人工兜底。
  **无任何记忆机制：每次运行都从会话检测重新开始，不读也不写历史登录信息。**
- 登录态存独立 `edge-profile/`（本地），一次成功长期免登。

## 3. 学习通

### 3.1 Runner 模式（默认）

```bash
cd platforms/chaoxing && npm install   # 一次性，仅 playwright-core
CHAOXING_PROFILE_DIR="<profile 绝对路径>" node runner.mjs --course ../../courses/<name>.json
```

- 课程配置：复制 `courses/course.example.json` → `courses/<name>.json`，填 `catalogUrl`
  （目录页）与 `sessionParams`。`nodes[]` 留空 = 自动发现章节；提供则按表跑。
- 行为：自适应登录（§2）→ 逐节点 2x 静音真实播放 → `ended` 后核对
  `mArg.attachments[].isPassed`（假完成防御：未 passed 自动重播一次）→ 文档/阅读打开等待
  → 测验/弹题/验证码/日上限即停 → 全部完成 `done: true`。
- 监督节奏：每 30–60 秒读 `state.json` + tail `runner.log`。
- 需要人工看页面（测验读题/侦察）时：`CHAOXING_HEADED=1` 重启。
- **MVP 状态：代码就绪、待真实课程实测**——首跑发现的异常按 §5.5 记 field-notes。

**paused 词表**（`paused` 为原因字符串或 null；重跑同命令即续跑，已完成自动跳过）：

| paused | 类别 | 监督者动作 |
|---|---|---|
| `qr-wait` | 进程内等待 | Runner 已存 `qr.png` → 交用户用学习通 App 扫码（≤7.5 分钟，过期自动刷新重新给图；磁盘上的 qr.png 持续更新，查看器显示过期时重开文件） |
| `captcha` | 进程内等待 | Runner 已存 `captcha.png`（页面内 fetch 转 base64，不受无头限制）→ 按 `captchaPolicy` 读码，把结果写入 `platforms/chaoxing/captcha-code.txt`，Runner 自动提交（≤5 分钟） |
| `no-credentials` | 已退出·补凭据 | 按 §2 获取凭据写入后重跑 |
| `outside-active-hours` | 已退出·等窗口 | 不在 `settings.activeHours` 时段；等时段或经用户同意调整后重跑 |
| `login-failed` / `login-error` | 已退出·侦察 | 读 `pausedDetail`；密码错→更正凭据；页面改版→侦察后记 field-notes；用户不便给密码→扫码通道 |
| `video-stuck` / `video-lost` | 已退出·重跑 | 直接重跑（自动跳过已完成）；同一视频反复出现才 `CHAOXING_HEADED=1` 侦察 |
| `navigation-failed` | 已退出·侦察 | 目录页/侧栏结构变化或配置缺 URL；人工核对后补 `nodes[]` 配置 |
| `completion-unverified` | 已退出·人工 | 重播后仍核对不到完成标记；人工到目录页看 ✓，必要时记 field-notes |
| `daily-cap` | 收工 | 按 §5.3 停止当日视频任务，向用户汇报 |
| `quiz` / `quiz-popup` | 交监督者 | 章节测验 → §5.1；视频中途弹题 → §5.2（Runner 不代答） |
| `error` | 已退出·侦察 | 读 `pausedDetail` + runner.log `FATAL`，按 §5.5 处理 |

### 3.2 浏览器监督模式（备选，全流程实战验证）

适用：用户明确要求在可见浏览器跑、或 Runner 不可用。若用户浏览器已登录学习通，
优先复用该窗口（免登录）；否则建议改走 Runner。

1. **启动/续跑**：读课程配置与 `state.json`（手动模式用 v0 双字段，见 §6）；打开目录页
   URL 确认登录态；`enc`/`openc` 失效则回目录页重取；从 `currentNode` 继续。
2. **主循环**（对每个 `type: video` 节点）：
   - 打开播放页 URL（模板替换 `chapterId` 直达节点）；
   - 在**顶层文档**注入 `scripts/keepalive.js`（整页跳转后丢失，每次跳转后重注入；
     监督者远程注入法：F12 → 控制台输入「允许粘贴」→ 粘贴执行。带标题信标的变体
     `scripts/keepalive.supervisor.js` 会把 `[cx]进度秒/总秒|ENDED|QUIZ` 写进窗口标题，
     监督者用窗口枚举低成本轮询，无需频繁截图）；
   - 轮询 `window.__cx`（3 秒一拍）或标题信标；有视频按剩余时长自适应等待；
   - `ended === true` → **先核对平台完成标记**（`icon_Completed`/目录 ✓；ended ≠ 已记录，
     实测有"假完成"）→ 尽快点 `#prevNextFocusNext` → 等 6 秒 → 重注入保活脚本；
   - 连续 3 次无视频（约 24 秒）→ 测验/作业页转 §5.1；无任务点节点点下一节跳过；
   - 倍速被锁定 → **接受 1x 真实播放，不对抗**，弹题/观后题走 §5.2/§5.1。

### 3.3 环境注意（学习通）

- 无头 Runner 不受窗口最小化/熄屏影响；浏览器监督模式受焦点/熄屏/锁屏协议约束
  （见 knowledge/chaoxing.md §8.5），这正是 Runner 为默认形态的原因之一。
- 保活脚本 v2.1 原理：定时器钉 muted/2x/play + video `pause` 事件监听立即重播
  （页面无焦点时 setInterval 被节流，事件监听不受影响）。

## 4. 中国大学MOOC — Runner 模式

确定性循环全部在 `platforms/icourse163/runner.mjs`（playwright-core 无头 Edge）。
监督者职责：备环境、按 §2 备凭据、盯状态、按词表处理暂停。

### 4.1 环境准备（一次性）

Node ≥ 20、系统 Edge；`cd platforms/icourse163 && npm install`；
课程配置复制 `courses/icourse163.example.json` → `courses/<name>.json`（填 `courseUrl`，
`videos`/`docs` 留空 = 自动发现）。

### 4.2 登录（自适应链自动执行）

会话有效 → **密码**（页面自身表单；新设备被风控拒绝会自动降级）→ **短信兜底**
（`waiting-sms-code`：把验证码写进 `platforms/icourse163/code.txt`，10 分钟超时）→
**扫码**（`npm run login` 出 `qr.png` 交用户扫，`qr-meta.json` 判 success；无密码/密码
被拒时的最终人工通道）。触发易盾滑块 → 自动降级/停下交人工（安全规则第 9 条）。

### 4.3 运行与监督

```bash
cd platforms/icourse163
MOOC_PROFILE_DIR="<profile 绝对路径>" node runner.mjs --course ../../courses/<name>.json
```

每 30–60 秒读 `state.json`（`matrix` 全量矩阵 / `current` 播放中 / `results` 已完成 /
`done` 终态）+ tail `runner.log`。完成口径 = 平台 `learned` 标记（Runner 播完回列表核对）。
`done: true` → 汇报收工。长挂机一律无头；侦察时 `MOOC_HEADED=1`。

### 4.4 paused 词表

| paused | 类别 | 监督者动作 |
|---|---|---|
| `waiting-sms-code` | 进程内等待 | 等用户短信，把验证码写入 `code.txt`（10 分钟超时）。怪癖：短信登录成功后该字段**不会自动清空**，Runner 可能带着它继续跑完——判断进程死活看 runner.log 与 `current`/`ticks` 是否在变 |
| `no-credentials` | 已退出·补凭据 | 按 §2 获取凭据，或先 `npm run login` 扫码建登录态 |
| `login-form-not-found` / `sms-toggle-failed` | 已退出·侦察 | 登录页改版；短期绕法 = 密码通道或扫码；发现记 field-notes |
| `sms-code-timeout` | 已退出·重跑 | 验证码超时；确认手机可收短信后重跑，或改扫码 |
| `need-set-password` / `login-failed` | 已退出·人工 | 平台风控；请用户人工登录一次或扫码，登录态入 profile 后重跑 |
| `login-error` | 已退出·侦察 | 读 `pausedDetail`（前 200 字符）+ runner.log |
| `captcha` | 已退出·交人工 | 易盾滑块，不绕过（安全规则第 9 条）：走扫码通道重建登录态再重跑 |
| `video-stuck` / `video-lost` | 已退出·重跑 | 直接重跑（自动跳过已 learned）；反复出现才 `MOOC_HEADED=1` 侦察（视口 ≥1600×900） |
| `error` | 已退出·侦察 | 读 `pausedDetail` 与 runner.log `FATAL` 行，按 §5.5 处理 |

### 4.5 平台特性

- **课程按周发布**：测验未发布（`#/learn/testlist` 显示「老师还没有发布」）→ 汇报
  "当前周无待办"收工，不硬等。
- 首查未观测到每日上限/图形验证码，但口径不变：进度当日停止增长按 §5.3 停机汇报。
- **learned 阈值偏宽**（部分观看即点亮）——Runner 仍真实完整播放，不为省时间缩短停留。
- 播放器状态机脆弱（直接 `video.play()` 会死锁）：恢复只走播放器按钮事件序列或整页
  reload，Runner 已内置；监督者不要用浏览器替它操作播放页。

## 5. 异常手册（监督者真正的工作）

### 5.1 章节测验 / 作业

**学习通**（实测流程）：
1. 弹「当前章节还有任务点未完成」→ 调页面自身 `closeDeleteWindow()` 关闭
   （同名 `.popClose` 有多个，必须限定作用域）。
2. 题目文字可能经字体混淆（DOM 乱码）→ **截图读渲染后的文字**，不要信 DOM 文本
   （`aria-label` 通道可优先试，knowledge §6）。
3. 逐题读题、记录答案倾向；全部读完再统一作答（最内层 `#frame_content` 按题目索引点
   选项 radio，A/B/C/D 对应第 0–3 个选项；校验读 hidden `input[name='answer{qid}']`）。
4. 核对后点「提交」只提交一次：`a.btnSubmit` → 顶层 `.popDiv.Marking` 确认层的「提交」
   `a.jb_btn`；成功判据 = 「已完成 · 第N次作答 · 本次成绩X分」且 `a.btnSubmit` 消失。
   信心不足可用 `pyFlag="1"` 只保存不提交（人工核对后再交）。
5. 处理测验建议临时 `CHAOXING_HEADED=1` 或在用户自己的浏览器完成（读题需要视觉）。

**中国大学MOOC**（**流程未实测**，首遇按此执行并记 field-notes）：
测验通常**限次**，纪律更严——先查清限次/倒计时规则再动；
全部读题 → 拟答案 → **交用户确认** → 只提交一次。Runner 不自动做测验。

### 5.2 视频中途弹题

学习通：Runner 以 `quiz-popup` 停下（不代答）；浏览器监督模式下保活脚本检测浮层
（`__cx.quizPopup === true`）暂停恢复。流程：截图读题 → 作答 → 确认浮层关闭 → 恢复。
读不了的题（混淆）截图给用户。（icourse163 未观测到弹题。）

### 5.3 每日上限

学习通：`jobCountDiv`/`maskDiv` 提示框；通用信号：进度计数当日停止增长。
→ 停止视频任务（Runner 已以 `daily-cap` 停），向用户汇报当日完成量与断点位置，
**绝不重试"再多刷一点"**。

### 5.4 验证码（策略按课程配置 `captchaPolicy`，默认 agent-first）

**学习通图形码（9010/403）**：
- Runner 通道（推荐）：`captcha.png` 已存盘（页面内 fetch 转 base64）→ 监督者按
  `agent-first` 自读，或交用户读码 → 结果写 `captcha-code.txt` → Runner 自动提交。
  连续失败 2 次升级用户读码；超时 5 分钟暂停任务。
- 浏览器监督通道：截图/`processVerifyPng.ac` fetch-base64 取图 → 填 `#ucode` →
  点 `input.submit`，302 回学习页即通过。

**中国大学MOOC 易盾滑块**：一律人工（安全规则第 9 条），唯一正解 = 扫码通道（§4.2）。

### 5.5 其他

页面结构变化、脚本报错等未列举异常：记录到 `docs/field-notes.md`（**只追加**，
不改旧条目，附日期/URL/原文），能安全重试就重试一次，不能就停下问用户。

## 6. 状态文件

- **Runner 模式（默认，两平台一致，协议 v0.2）**：Runner 每次启动新建并覆盖
  `platforms/<platform>/state.json`，`paused` 为原因字符串或 null + `pausedDetail`，
  另有 `results`/`current`/`done`；**是进度报告不是续跑游标**——续跑 = 重跑 Runner
  （自动发现跳过已完成）。词表见 §3.1 / §4.4。
- **浏览器监督模式（学习通备选）**：监督者手写仓库根 `state.json`（v0 双字段
  `paused` 布尔 + `pauseReason` 枚举），`currentNode` 是续跑游标。
- 共同点：会话可能被压缩，文件不会——关键进度一律落盘后再汇报。

## 7. 模式

- **默认（推荐）**：无头 Runner —— 同时满足 safe（真实 2x、风控感知、日上限检测）+
  token-saver（确定性工作零模型参与）+ **不占电脑**（用户挂机期间正常用机器）。
- 多账号：`credentials.local.json` 多条目 + `--account <name>` + 各自 profile/状态文件；
  "多开"须先重申安全规则第 2 条（同账号严禁多开）。
- 用户要求"看着它跑" → 学习通浏览器监督模式（§3.2）或临时 `*_HEADED=1`。

## 8. 成熟度（分平台）

- ✅ **学习通·浏览器监督模式**：两门课全流程线上验证——大学物理 **65/65** 任务点（含 4 次测验
  100/100/80/80、夜间熄屏/锁屏挂机、两次 9010 风控验证码应对）；**2026-09-14 侧边浏览器
  （IAB）模式完成网络安全培训 19/19 收尾**（9010 验证码 agent-first 一次通过）。实测发现
  **无头会话会被学习通风控切出** → 学习通慎用无头 Runner，首选可见浏览器（用户本机或 IAB
  侧边栏）+ 焦点保持视频；新实测细节见 field-notes 2026-09-14 条目
- 🔧 **学习通·Runner**（2026-09-14 新增）：结构就绪（自适应登录/假完成重播/词表），但
  无头形态当日实测被风控反复踢会话，待改为有头或引入反风控策略后再评估
- ✅ **中国大学MOOC·Runner**：视频/文档流程实战验证（自动发现、扫码登录、看门狗）；
  **2026-09-14 马原课新周 7 视频 + 7 文档全部 learned（14/14）**；测验流程仍未实测
  （按 §5.1 从严执行）
- 多平台知识库：knowledge/chaoxing.md（全流程验证）、knowledge/icourse163.md（视频/文档验证）
- 新发现的坑一律进 `docs/field-notes.md`（只追加），这是本项目的测试用例库
