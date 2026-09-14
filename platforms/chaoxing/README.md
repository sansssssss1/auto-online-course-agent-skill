# platforms/chaoxing — 超星学习通 Runner

无头真实播放 Runner（监督者-Runner 架构，见 [docs/architecture.md](../../docs/architecture.md)）。
**默认用本 Runner**：无头运行不占用电脑（不打断用户键鼠/前台）；浏览器监督模式
（SKILL.md §2.2）降级为备选。**MVP 状态：代码就绪、待真实课程实测**（同 icourse163
Runner 首轮的定位），跑出新异常按 HANDOFF 规则记 `docs/field-notes.md`。

## 安装

```bash
cd platforms/chaoxing
npm install        # 仅 playwright-core（驱动系统 Edge，无需下载浏览器内核）
```

## 登录（自适应，每次运行前由监督者询问用户本次账号）

账号获取（SKILL.md 安全规则第 10/11 条，**无历史记忆，不复用先前登录信息**）：

1. 监督者每次运行前先问用户：本次用哪个账号、给密码还是扫码；该账号登录态仍有效时
   经用户确认可直接续用
2. 用户给密码 → 环境变量 `CHAOXING_PHONE` / `CHAOXING_PASSWORD`（本次运行有效）
   或 `credentials.local.json`（用户明确要求才写，已 gitignore；多账号 `--account <name>`）
3. 用户不给密码 → Runner 自动走扫码通道：截图二维码到 `qr.png` 交用户扫

自适应登录链（自动执行）：1. **会话有效** → 直接用（登录态存本地 `edge-profile/`）；
2. **password**：在登录页自身表单填账号密码提交（AES 加密由页面 JS 完成，
   Runner 不碰加密、不伪造请求）；触发滑块 → 自动转下一通道；
3. **qr**：无头截图二维码到 `qr.png` → 监督者交用户用学习通 App 扫码
   （进程内等待 ≤5 分钟，过期自动刷新）。

## 挂机运行

```bash
cd platforms/chaoxing
CHAOXING_PROFILE_DIR="<profile 绝对路径>" node runner.mjs --course ../../courses/<name>.json
# 缺省不设 --course 时用内置空配置（仅有 catalogUrl 时可自动发现任务）
```

- 课程配置模板见 `courses/course.example.json`（`nodes[]` 提供 chapterId 则直接按表跑；
  留空 = 打开目录页后从 studentstudy 侧栏 `.chapter_item` 自动发现）
- 行为：逐节点 2x 静音真实播放 → `ended` 后核对 `mArg.attachments[].isPassed`
  （假完成防御，未 passed 自动重播一次）→ 文档/阅读打开等待 → 测验节点停下交监督者
- 验证码（403/9010）：自动截 `captcha.png` → 监督者读码写 `captcha-code.txt`
  → Runner 提交续跑（无第三方打码、不对抗）
- 每日上限（`jobCountDiv`）：检测到即 `paused=daily-cap` 收工
- 跳页节奏：节点间 ≥4 秒随机化（knowledge §8 红线），全程包装页直跳，不拼 knowledge 直链

## 状态与产物（已 gitignore）

`state.json`（协议见 architecture.md v0.2：`paused` 为原因字符串或 null）、`runner.log`、
`qr.png`、`captcha.png`、`captcha-code.txt`、`edge-profile/`

## paused 词表

`no-credentials | outside-active-hours | login-form-not-found(并入 login-failed 详情) |
login-failed | login-error | captcha | qr-wait | daily-cap | quiz | quiz-popup |
video-stuck | video-lost | completion-unverified | navigation-failed | error`

除 `captcha`（进程内等码）与 `qr-wait`（进程内等扫码）外，均为进程已退出——
处理完重跑同一条命令即续跑（会话与完成标记会自动跳过已完成部分）。
