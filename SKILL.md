---
name: auto-online-course-agent-skill
description: Supervise safe, resumable completion of MOOC task points on 超星学习通 (Chaoxing) and 中国大学MOOC (icourse163) — real playback at ≤2x, adaptive account login (user hands over credentials; the agent logs in and re-logs in itself), background Runners that leave the user's computer free, and courses where the teacher has locked the playback rate (accept 1x, read-only beacon polling, in-video popup quizzes and post-video quizzes); the agent handles only exceptions. Use when the user asks to 刷课 / 挂机 / 刷网课 / 自动登录并完成学习通(超星)或中国大学MOOC(慕课/mooc/icourse163)的任务点, or to resume an interrupted course run.
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
3. **测验策略（2026-09-17 晚用户授权升级：尽量拿高分，自行推进）**：首次提交仍按
   「全部读完 → 全部作答 → 核对 → 提交」；**提交后若任务点未点亮或成绩明显不理想
   （错题已有已知正解），直接用平台「重做(剩余 N 次)」入口按错题台账修正，直到任务点点亮
   或重做余量用尽——无需逐次询问用户**。实测注意：**0 分提交可能不点亮任务点**（课程②样本，
   与课程①"提交即计入"不同）→ **任务点点亮与否以平台标记为准（`icon_Completed`/侧栏计数），
   不以提交动作为准**；重做余量用尽仍未点亮 → 记录 `wrongItems` 并汇报。
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
11. **凭据由用户交付、监督者自助登录（用户 2026-09-17 授权）**：开工前向用户索取**本次**
    账号与凭据（账密或扫码）；**用户交付后，监督者自行登录，登录态掉线时自行重登，
    不再逐次询问**。凭据只经环境变量或 `credentials.local.json`（本地、已 gitignore）传递，
    绝不入库/日志/打包/外发；**每次运行开始仍须向用户确认"本次用哪个账号"**，不复用上一次
    运行残留的凭据或推测；凭据失效且自助重登失败时才回问用户。
12. **课程即取即用（每次）**：调用时监督者必须先向用户询问**本次要看课程名**，据以临时
    建立课程配置（`courses/<真实课程>.json`，已 gitignore）；**任务完成或中止后立即清除**
    课程相关本地数据——真实课程配置、`state.json`、`runner.log`、调试/二维码/验证码截图
    全部删除，本地只保留 skill 本身、模板与登录态 profile。
13. **锁速课程（教师锁定倍速）**：`video.playbackRate` 恒为 1、倍速控件整体隐藏（`vjs-hidden`）
    → **接受 1x 真实播放，不对抗**；**禁止注入 `scripts/keepalive.js` v2.1**（它会把倍速钉成
    2 = 变相加速），只读巡检改用 `scripts/keepalive.beacon.js`（不写 rate、不调 play/pause，
    只发信标）。中途弹题与观后题流程见 §3.4 / §5.1 / §5.2。
14. **探索预算**：遇到未知页面结构，**最多试 2 种已知配方**（配方表见 knowledge/chaoxing.md §13），
    仍不通就记 field-notes + 切 fallback 继续推进；**禁止连续探索**——实测有会话在同一障碍上
    连试 4–5 次，纯烧上下文。

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
1. **询问账号与交付方式**：本次用哪个账号（学习通 / 中国大学MOOC 分别确认），凭据由用户交付
   还是改扫码。若该账号登录态（`edge-profile/` 或 IAB 会话）仍有效，告知用户"可直接续用，
   无需登录"，经确认后免登；用户要求换号或彻底不保留会话时，改用新 profile 或运行后删除对应
   profile 目录。
2. **用户交付凭据** → 经本次运行的环境变量传入，或写入 `credentials.local.json`
   （本地文件、已 gitignore，绝不入库/打包/日志；多账号用 `name` 区分 + `--account <name>`）。
   **获交付后监督者自行登录与自行重登**（安全规则第 11 条）：
   - **登录态自检**：进入课程前 + 每完成一章，做一次廉价检查（请求课程列表/目录页，
     看是否被重定向到登录页）；
   - **失效自愈**：用交付的凭据重新登录（学习通 = IAB 内个人空间/登录页表单或 passport 表单；
     icourse163 = Runner 自适应链，或 `npm run login` 扫码），**不打断用户**；
     自助重登失败（验证码/风控拒绝/密码错）才回问用户。
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
2. **主循环**（每个小节通常 = 页签「1 视频」+「2 章节测验」，即 2 个任务点）：
   - 打开播放页 URL（模板替换 `chapterId` 直达节点）；**新版布局的"下一节"是页内翻页**，
     不是旧版 `#prevNextFocusNext`（两代布局并存，按实际 DOM 判断）；
   - 在**顶层文档**注入巡检脚本（整页跳转后丢失，每次重注入）：
     - **锁速课程 → `scripts/keepalive.beacon.js`**（只读信标：不写倍速、不调 play/pause）；
     - 未锁速的旧布局课程才用 `scripts/keepalive.js` v2.1（它会钉 2x）；
     - 远程注入法：F12 → 控制台输入「允许粘贴」→ 粘贴执行；
   - **轮询信标（低成本）**：`document.title` / `localStorage['cx:beacon']` / `window.__cx`，
     格式 `[cx]t=秒/总|p=|e=|q=|r=|i=idle秒`；标题无 `[cx]` 前缀 = 需要重新注入；
   - **自适应巡检阶梯 v2**（2026-09-17 下午实战修正：调用总数由「单次调用上限 ~120s ÷ 播放时长」
     决定，**放大调用内探测间隔不减少调用数**——要省调用只能拉长轮间距）：

     | 观察到的信号 | 巡检策略 |
     |---|---|
     | 起始 / 任何异常后 | 单次调用内 **5.5 秒粒度**探测，预算 ~105–119s |
     | 连续 ≥2 轮干净（无 `q`、无停摆、`i` 正常归零） | **跳到 5–10 分钟一查**（信标持久化在 localStorage，回来读一行即知期间全貌；弹题未暂停视频时晚处理零成本；若暂停，代价是墙钟白等——可接受） |
     | `q=1`（未处理弹题） | 立即回短周期 → §5.2 作答 |
     | `p=1` 持续 / `idle` 持续增长 | 立即回短周期 → 验证式恢复（§3.4）+ 检查是否触发 IAB 前台红线（§3.3） |
     | `e=1` | 核对完成标记 → 翻到下一小节 |

   - 实测基线：剩余 10–20h 播放按 95–110s/轮需 **400+ 次调用**；拉长轮间距后可压到
     **~100–150 次**。
   - 每轮**只回一行**（信标串 + 台账追加），不回显 DOM/JSON（省 token；台账见 §6）；
   - `ended === true` → **先核对平台完成标记**（`icon_Completed`/目录 ✓；ended ≠ 已记录，
     实测有"假完成"）→ 尽快翻下一小节 → 重注入；
   - 连续 3 次无视频（约 24 秒）→ 测验/作业页转 §5.1；无任务点节点点下一节跳过；
   - 倍速被锁定 → **接受 1x 真实播放，不对抗**，弹题/观后题走 §5.2/§5.1。

### 3.3 环境注意（学习通）

- 无头 Runner 不受窗口最小化/熄屏影响；浏览器监督模式受焦点/熄屏/锁屏协议约束
  （见 knowledge/chaoxing.md §8.5），这正是 Runner 为默认形态的原因之一。
- **新版播放器（video.js v7，2026-09-16 实测）**：旧版的"无焦点暂停"**不适用**——
  `hasFocus()===false` 且 `visibilityState==='visible'` 时 1x 持续播放；但课程卡片明确要求
  「观看时长 ≥ 总时长的 90%（未完成任务点前不可拖拽、**观看时不可离开或将页面最小化**）」
  → **面板保持可见仍是硬前提**。
- **取题通道**：进入 studentstudy 后 IAB 截图面被破坏（`guest` / surface preparation timeout）
  → 一律走页面内通道（DOM 明文 / 字体映射 / canvas 渲染），不要反复试截图。
- **ckenc（`opencoursenewfy`）一次性**：拿列表页快照里的 ckenc 直接 goto → 404 错误页，
  必须从个人空间课程卡真实点击进入。
- 保活脚本 v2.1 原理（**仅用于未锁速的旧布局课程**）：定时器钉 muted/2x/play + video
  `pause` 事件监听立即重播（页面无焦点时 setInterval 被节流，事件监听不受影响）。
- **IAB 前台红线（2026-09-17 实测重大发现）**：同一 IAB 会话内 `claimTab`/切换标签 →
  视频标签退后台**停摆**（`t` 卡 0、paused 抖动，但 `readyState=4`、`error=null`、
  `visibilityState` 仍 `'visible'`）。**健康判据用 `t` 是否推进，不要用 `hasFocus()`**。
  恢复配方：`tabs.list()` 关闭视频标签外全部标签 → 激活视频标签 → 立即恢复。
  配套 API 坑：关标签必须 `(await tabs.get(id)).close()`（直接链式调用抛
  `close is not a function`）；信标注入必须
  `new Function('try {' + IIFE + '; return "OK" }')`（`return IIFE` 写法静默无效）。

### 3.4 锁速课程（倍速锁定 + 中途弹题 + 观后题）—— 2026-09-16/17 实测

结构：新版目录（`mooc2-ans` 的 `stu` 页）→ 学习页；**每个小节 = 页签「1 视频」+「2 章节测验」**，
即 2 个任务点。完整选择器与样本见 knowledge/chaoxing.md §11。要点：

- **倍速锁特征**：`div.vjs-playback-rate…` 带 `vjs-hidden`（display:none），内层
  `button[title="播放速度"]` 的 `aria-disabled` 仍是 false（锁的是控件可见性），
  `.vjs-playback-rate-value` 只显示「倍速」无数字，`video.playbackRate` 恒为 1
  → **不要试图解锁，接受 1x**（安全规则第 13 条）。
- **中途弹题**（`.x-container.ans-timelineobjects` > `.ans-videoquiz` > `.tkTopic`）：
  题面 **DOM 明文**（无字体混淆）→ 点 `input[type=radio]`（多选 checkbox）→
  校验 `input.checked === true` → `a#videoquiz-submit` → 判据 `.tkTopic` 消失 / 视频继续；
  **点 `li` 无效**（自定义 UI 不转发，提交空答案必判错）；答错必须重答直到答对。
  出现时可能暂停也可能不暂停，若暂停按下方"验证式恢复"处理。
- **观后题**：`.TiMu.newTiMu`，隐藏字段 `input[name='answer{qid}']` + `answertype`（0 单选/1 多选）；
  样本无倒计时/限时；**提交即计入任务点，与分数无关**；明细走 §5.1 流程。
- **读题优先级**：① `knowledge/cx-font-map.json` 自举映射解码 DOM 文本
  （`node scripts/fontmap-merge.mjs --decode <file>`）；② 页面内 canvas 渲染 PNG；
  ③ 截图（本环境通常不可用）。
- **验证式暂停恢复**（别乱点）：先确认当前是暂停态 → 单击一次播放键 → 3 秒后仍 `paused`
  才做 `pause()→play()`。识别特征：状态读回后 `t` 不增长。静默暂停 3–5 次/段属正常，
  单击播放键即恢复。

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

**学习通**（实测流程，2026-09-16/17 更新）：
1. 弹「当前章节还有任务点未完成」→ 调页面自身 `closeDeleteWindow()` 关闭
   （同名 `.popClose` 有多个，必须限定作用域）。
2. **读题优先级**：① `knowledge/cx-font-map.json` 自举映射解码 DOM 文本（最省；暖机后首选，
   解码命令 `node scripts/fontmap-merge.mjs --decode <file>`）；② 页面内 canvas 渲染 PNG
   （文本节点按 computed font `fillText` 后 `toDataURL`）；③ `aria-label` 通道（仅部分明文）；
   ④ 截图（IAB 进入学习页后通常不可用）。**提交后页面显示明文题干 + 我的答案 + 正确答案**
   → 立刻用 `scripts/fontmap-merge.mjs` 自举映射（越跑越省 token）。
3. 逐题读题、记录答案倾向；全部读完再统一作答（最内层 `#frame_content` 按题目索引点选项
   radio，校验 hidden `input[name='answer{qid}']`；`answertype` 0=单选 1=多选）。
4. 核对后点「提交」只提交一次：`a.btnSubmit` → 顶层 `.popDiv.Marking` 确认层的「提交」
   `a.jb_btn`；成功判据 = 「已完成 · 第N次作答 · 本次成绩X分」且 `a.btnSubmit` 消失。
   信心不足可用 `pyFlag="1"` 只保存不提交（人工核对后再交）。
   **观后小测（锁速课程）**：`.TiMu.newTiMu`，样本无倒计时，**提交即计入任务点、与分数无关**。
5. **答题口径**（实测，写入 `state.json` 的 `wrongItems` 台账）：
   多选**近义选项会同入键**、不同义项不入键；判断题按**课程自身立场**判（非学科常识，
   例如某课按科斯定理口径把"市场交易能保证资源有效配置"判为「错」）；
   每题分值 = 100/题量（3 题错 1 = 66.6）。
6. **重做修正（2026-09-17 用户授权默认开启）**：提交后核对任务点是否点亮
   （侧栏 `icon_Completed`/计数变化）；**未点亮或分数明显不理想 → 用测验页
   「重做(剩余 N 次)」入口按已知正解修正，直到点亮或余量用尽**（安全规则第 3 条）。
   注意 0 分提交可能不点亮任务点（课程②样本）；重做也按"读题→作答→校验→提交"全流程走。

**中国大学MOOC**（**流程未实测**，首遇按此执行并记 field-notes）：
测验通常**限次**，纪律更严——先查清限次/倒计时规则再动；
全部读题 → 拟答案 → **交用户确认** → 只提交一次。Runner 不自动做测验。

### 5.2 视频中途弹题

学习通（**2026-09-16 重大修正后的流程**）：
1. **检测**：信标 `q=1`——`.tkTopic` 可见且**不含「回答错误/回答正确」**
   （已答浮层会滞留 DOM，必须排除）；旧布局用 `__cx.quizPopup`。
2. **读题**：锁速课程的弹题题面是 **DOM 明文**（无字体混淆），无需截图。
3. **作答**：**点 `input[type=radio]`（多选为 checkbox）——点 `li` 无效**
   （自定义 UI 不冒泡转发，提交空答案必判错）→ 校验 `input.checked === true`
   → 点 `a#videoquiz-submit`。
4. **判据**：`.tkTopic` 消失 / 视频自动继续；**答错必须重答**（重答入口会重现，直到答对——
   用户观察：答错必须重答通过）。
5. **恢复**：出现时可能暂停也可能不暂停；若暂停，按 §3.4 的验证式重试恢复播放。

Runner 模式下 Runner 以 `quiz-popup` 停下（不代答），监督者按上述流程处理。
（icourse163 未观测到弹题。）

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

**探索预算（硬规则）**：未知结构最多试 2 种已知配方（配方表见 knowledge/chaoxing.md §13），
仍不通 → 记 field-notes + 切 fallback 继续推进，**不做第 3 次连续探索**。
实测教训：有会话在同一跨源 iframe 障碍上连试 4–5 次，纯烧上下文。

## 6. 状态文件

- **Runner 模式（默认，两平台一致，协议 v0.2）**：Runner 每次启动新建并覆盖
  `platforms/<platform>/state.json`，`paused` 为原因字符串或 null + `pausedDetail`，
  另有 `results`/`current`/`done`；**是进度报告不是续跑游标**——续跑 = 重跑 Runner
  （自动发现跳过已完成）。词表见 §3.1 / §4.4。
- **浏览器监督模式（学习通备选，协议 v0.3 —— 2026-09-17 实战版）**：监督者维护仓库根
  `state.json`（已 gitignore），字段：
  `mode`（`browser-supervision`）/ `paused` / `pauseReason` / `platform` / `accountNote` /
  `environmentNotes[]`（面板可见性、截图限制、倍速锁定等环境事实，新会话先读）/
  `courses[]`（`name` / `courseId` / `clazzid` / `cpi` / `taskPointsTotal` / `taskPointsDone` /
  `status` / `scores` / `wrongItems` / `chapterIds{}`）/ `currentNode`（续跑游标）。
  另配**进度台账**（每小节追加一行，如仓库外 `cx-ledger.txt`）——上下文压缩后精确续跑用。
  **续跑 = 读 `state.json` + 台账尾部 3 行 + `field-notes.md` 最后 3–5 条**，无需回读全文。
- **交接**：模板见 [docs/templates/continue-prompt.md](docs/templates/continue-prompt.md)；
  **每完成一门课主动交接一次**（别等上下文"很长"——实测两轮 rollout 已达 38MB/51MB）。
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
- ✅ **学习通·锁速课程场景（2026-09-16/17 新增）**：教师锁定倍速 + 中途弹题 + 观后题三段式已打通。
  《食品营养与食品安全》**60/60 任务点**（30 小节；30 节观后题全部一次提交，27 满分、
  1.1=83.3、6.3=66.7、7.1=66.6；**37 道中途弹题 36 道首答正确**、1 道重答通过；
  零验证码、零日上限、零进度异常）；《论文写作初阶》进行中（18/68 起）。
  本轮新增工具：`scripts/keepalive.beacon.js`（只读信标 + 自适应节奏输入）、
  `scripts/fontmap-merge.mjs`（字体映射自举 + 解码，自测通过）、
  `knowledge/cx-font-map.json`（映射表种子）、`docs/templates/continue-prompt.md`。
  **实战验证（2026-09-17 下午，课程② 28→35/68）**：beacon 信标全流程有效（整门课一次注入、
  ENDED/QUIZ/停摆自动识别、4.1 以 `t=1668/1668,p=1,e=1` 精准收尾）；自适应巡检假设被推翻
  （调用数由工具上限决定）并已修正为 v2 阶梯（拉长轮间距至 5–10 分钟）；字体映射自举判负
  （混淆按页随机，跨页复用命中 0/218，降级为页内辅助，不再投入）；测验策略升级为
  「尽量拿高分、重做自行推进」（用户授权，0 分不点亮任务点的课程②口径已入册）。
  新发现 **IAB 前台红线**（切标签停摆视频，`hasFocus()` 不可作判据）已入册 §3.3。
  待验证：巡检阶梯 v2 的调用数下降幅度（目标 400+ → ~100–150）。
- 多平台知识库：knowledge/chaoxing.md（全流程验证）、knowledge/icourse163.md（视频/文档验证）
- 新发现的坑一律进 `docs/field-notes.md`（只追加），这是本项目的测试用例库
