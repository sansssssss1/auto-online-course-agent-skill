# HANDOFF — 协作交接说明（面向协作者与其 agent）

> 交接时间：2026-09-12。本文写给将要接手协作的人 **和 TA 的 agent**：
> 先读本文，再按"阅读顺序"读仓库。本包不含任何账号凭据与登录态。

## 这是什么

**mooc-agent-skill**：安全优先、可断点续跑、由 AI agent 监督的 MOOC（网课）任务点完成工具。
定位是"刷得稳"而不是"刷得快"：真实播放、风控感知、异常才叫人——这是它在同类开源项目
（API 伪造心跳的 CLI、油猴脚本）中的差异化空位，也是不可妥协的底线。

一句话架构：**确定性工作交给 Runner 脚本，LLM agent 只处理异常**（测验读题、弹窗、验证码、
风控迹象）。两者靠状态文件 + pauseReason 通信，因此任何能跑命令、截图、执行页面 JS 的
agent（ZCode / Claude Code / Codex / OpenClaw…）都能当监督者。

## 阅读顺序

1. `README.md` — 定位、当前状态、免责声明
2. `docs/architecture.md` — 四层架构、两根旋钮、凭据层、状态文件协议（v0.2）、许可边界
3. `SKILL.md` — 双平台监督者运行手册（凭据获取 §2；学习通 Runner §3 / 浏览器监督备选；
   icourse163 Runner §4。其中的安全规则是硬约束，协作中不得放宽）
4. `knowledge/chaoxing.md`、`knowledge/icourse163.md` — 两平台实测知识库（最值钱的资产）
5. `docs/field-notes.md` — 现场日志（只追加不修改）
6. `platforms/icourse163/` — 已收编、干跑验证过的 Runner（可运行代码）
7. `docs/roadmap.md` — Phase 2–5 待办清单

## 当前状态快照（2026-09-12）

- **学习通（chaoxing）**：两门课程全流程验证完毕（大学物理 65/65 含 4 次测验
  100/100/80/80；网络安全培训）。监督模式（agent + 注入脚本）已实战充分验证。
- **中国大学MOOC（icourse163）**：视频/文档流程已验证；课程按周发布、测验未发布，
  处于待续跑状态。
- **Runner**：两平台就位——icourse163 版视频/文档实战验证（自适应登录：密码/短信/扫码）；
  chaoxing 版 2026-09-14 新增（MVP 待实测）；两版默认无头运行（不占用户电脑），
  临时有头 `CHAOXING_HEADED=1` / `MOOC_HEADED=1`。`core/` 通用引擎提取待两版实测收敛。
- 近期待实测：chaoxing 倍速锁定类视频（1x 锁死 + 中途弹题 + 观后题）、icourse163
  测验流程（限次 + 倒计时，纪律从严）。

## 协作规则（重要，agent 请视为硬约束）

1. **安全红线不得修改**：只真实播放、官方最高 2 倍速、不伪造上报/心跳、不使用第三方
   打码服务、同账号禁止多开、验证码识别失败即升级人工。这是项目定位，不是可选项。
2. `docs/field-notes.md` **只追加不修改**；新实测发现必须带日期、页面 URL、报错/弹窗原文。
3. **凭据纪律**：验证码/密码只走环境变量与文件握手（`credentials.local.json` 已
   gitignore），永远不写入仓库、日志、状态文件；登录前向用户索取凭据是监督者的职责
   （SKILL.md §2）。
   `edge-profile/`、`qr.png`、`code.txt`、`captcha-code.txt`、`state.json`、`runner.log`
   等运行产物已被 .gitignore 覆盖，新增同类产物时先补 ignore 再提交。
4. **许可边界**：接口/页面事实知识部分学习自上游开源项目（Samueli924/chaoxing，
   GPL-3.0）——学事实、不抄代码；参考克隆放仓库外，不并入本仓库（本仓库 MIT）。
5. 每完成一个可验证的里程碑就 commit，提交说明写清楚改了什么、为什么。

## 给协作者 agent 的实操说明

- **本包不含登录态与凭据**。要在你（协作者）的机器上运行 Runner：
  1. `cd platforms/<平台目录> && npm install`（仅 playwright-core，驱动系统 Edge）
  2. 凭据二选一：设 `CHAOXING_PHONE/CHAOXING_PASSWORD`（或 `MOOC_PHONE/MOOC_PASSWORD`），
     或复制 `credentials.example.json` → `credentials.local.json` 填入**你自己的测试账号**
     （多账号用 name 区分，`--account <name>` 选择）
  3. `CHAOXING_PROFILE_DIR=<你的profile目录> node runner.mjs --course <课程json>`
     （icourse163 用 `MOOC_PROFILE_DIR`；首次也可 `npm run login` 扫码建登录态）
  4. 强烈建议先拿低风险/小课程干跑（无待办时应发现任务 → 0 → 正常退出）
- **改代码前先读对应平台的 knowledge 文件**——页面结构、选择器、坑都在那里，别从零摸索。
- 跑出任何新异常：按 `docs/field-notes.md` 的模板追加条目（附 URL 与原文）——这份日志是
  本仓库最值钱的资产，也是协作的主要产出物之一。
- 与上游的关系：欢迎把通用性改进（如每日上限检测、弹题处理）日后提 PR 回上游，
  但先在本仓库内完成验证。

## 隐私说明（本包的打包原则）

由 `git archive` 从已提交内容导出：**不含** .git 历史（无提交者邮箱）、不含任何登录态、
凭据、运行产物。保留了课程的公开页面标识（课程页 URL / tid），因为它们是 Runner 的
运行参数与知识库上下文；如需进一步脱敏请提出，对应改造 Runner 的配置外置即可。

## 发布前脱敏检查（每次打包/推 GitHub 前执行）

1. **运行产物一律排除**：`state.json`、`runner.log`、`storage-state.json`、`edge-profile/`、
   `qr*.png`、`captcha*.png`、`*-debug.png`、`code.txt`、`captcha-code.txt`、`qr-meta.json`、
   `credentials.local.json`、`login-hint.json`、`node_modules/`。
2. **真实课程配置不入库**：`courses/<真实课程>.json` 只留本地且**任务完成后即删除**
   （SKILL.md 安全规则第 12 条：课程即取即用）；仓库只保留两个 example 占位模板。
3. **代码不内置真实课程**：Runner 缺省必须要求 `--course` 配置（2026-09-14 已移除
   icourse163 runner 的内置课程缺省）。
4. **文档正则脱敏**：enc/ckenc/openc 等 32 位十六进制、tid/courseid/clazzid/cpi/
   chapterId/cid/userId 等平台 id、学校与姓名、验证码答案、手机号 → 一律占位符。
5. 扫描验证：对导出树 grep 上述模式，**零匹配**才可打包推送。
