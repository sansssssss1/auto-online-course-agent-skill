# 架构

## 目标 / 非目标

**目标**

- 安全优先：低封号风险地完成 MOOC 任务点（真实播放、风控感知、节奏可控）
- Harness 无关：任何能执行命令、截图、在页面里执行 JS 的 agent 都能当监督者
- 断点续跑：任何中断（会话压缩、窗口关闭、日上限）都能从状态文件恢复
- 知识沉淀：页面结构与坑是本项目的核心资产，与代码分离维护

**非目标**

- 不伪造学习进度上报/心跳来"加速完成"（这是头部 CLI 项目的路线，封号风险高一档）
- 不做批量商业代刷、不绕过付费/权限控制

## 四层结构

```
┌────────────────────────────────────────────────────────┐
│ Adapter 适配层   SKILL.md / AGENTS.md / slash command   │  薄壳，只是格式
├────────────────────────────────────────────────────────┤
│ Supervisor 监督者   LLM agent                           │  只处理异常：
│  消费 pauseReason → 读题作答 / 关弹窗 / 停止 / 汇报       │  测验、弹题、验证码、
│                                                         │  日上限、意外报错
├────────────────────────────────────────────────────────┤
│ Runner 执行器    确定性脚本（Phase 2: Playwright +       │  播视频/静音/倍速/
│                  独立 Chrome profile）                   │  下一节/跳过无任务点
│                  MVP 前由 agent 手动 tick 顶替            │  循环，全程无模型
├────────────────────────────────────────────────────────┤
│ Knowledge 知识层  knowledge/<platform>.md                │  iframe 链、选择器、
│                  docs/field-notes.md                    │  接口、坑清单
└────────────────────────────────────────────────────────┘
```

Runner 与 Supervisor 之间用**状态文件**（`state.json`）+ **暂停原因**通信，
不需要长连接。这就是 harness 无关的根本原因：监督者不需要操控浏览器的
专用工具，只需要"读状态文件、跑脚本、处理异常"这三个任何 harness 都有的能力。

当前落地：两平台 Runner 均已就位（`platforms/icourse163/` 视频/文档实战验证；
`platforms/chaoxing/` 2026-09-14 新增、待实测），**默认无头运行，不占用用户电脑**，
登录自适应（凭据层见下）；浏览器监督模式保留为备选（SKILL.md §3.2）。

凭据层（自适应登录）：**每次登录前由监督者向用户询问本次账号（SKILL.md 安全规则第 11 条）**，
用户本地告知后经环境变量（`CHAOXING_PHONE/CHAOXING_PASSWORD`、`MOOC_PHONE/MOOC_PASSWORD`，
进程结束即失效）或 `credentials.local.json`（模板 `credentials.example.json`，已 gitignore，
多账号用 `name` 区分 + `--account` 选择）传入；用户不给密码则走扫码。登录通道按序降级
（会话 → 密码 → 兜底），**无历史记忆机制（login-hint 已移除）**。凭据绝不写入日志/状态/仓库，
账号相关运行数据只保留本地（SKILL.md 安全规则第 10 条）。

## 两根旋钮：模式 = 预设

用户想要的"省 token 慢速模式 / 多开效率模式 / 安全模式"实际上是两根独立的旋钮：

| 旋钮 | 取值 | 说明 |
|---|---|---|
| **介入度** intervention | `tight`（每步确认）/ `balanced`（异常+测验时介入）/ `loose`（仅无法恢复的错误） | 决定 token 消耗与"慢"程度 |
| **并发度** concurrency | 单账号单开（默认） / 多账号并行 | **同账号严禁多开**，是典型风控信号 |

预设（`courses/<name>.json` 里配置）：

- `safe`（默认）：loose + 单账号 + 真实 2x 播放 + 日上限检测 + 夜间不跑
- `token-saver`：loose + Runner 接管一切确定性工作（agent 几乎零参与）
- `efficient`：多账号并行，每账号独立 profile 与状态文件

> 注：`safe` 和 `token-saver` 在当前设计里高度重合——确定性工作下沉后，
> 省 token 与安全天然是同一件事。

**其他策略开关**（`courses/<name>.json` 的 `settings`，独立于两根旋钮）：

- `captchaPolicy`：`agent-first`（默认——监督者先自读验证码图，连续失败 2 次升级用户读码）/
  `user`（一律用户读码；模型无识图能力的 harness 必须设为 `user`）。取图统一走
  "页面内 fetch 图片转 base64"，不做第三方打码。
- `maxRate`：倍速上限（默认 2，即平台官方最高档）。
- `quizPolicy`：测验提交策略（默认 `read-all-then-submit-once`）。

## 状态文件协议（v0.2）

v0 草案设想统一的双字段（`paused` 布尔 + `pauseReason` 枚举）；两个 Runner 落地后按实现
修订为**两形态并存**。字段细节与词表以 SKILL.md §3.1/§4.4/§6 为准。

### 浏览器监督模式（学习通备选 — 监督者手写）

```jsonc
// state.json — 每账号/每课程一份；currentNode 是断点续跑游标
{
  "course": "courses/my-course.json",   // 静态课程配置（见 courses/course.example.json）
  "currentNode": 5,                      // nodes 数组下标
  "completed": ["<id>", "<id>"],
  "completedCount": 4, "totalCount": 65,
  "paused": true,
  "pauseReason": "quiz",                 // quiz | video-popup | captcha | daily-cap
                                         // | not-open | error | manual | done
  "pauseDetail": { "chapterId": "<id>", "questionCount": 5 },
  "updatedAt": "2026-09-11T15:00:00+08:00"
}
```

处理约定：写 `paused/pauseReason` 后停止动作 → 按 SKILL.md 异常手册处理 →
处理完写回 `paused=false` → 从 `currentNode` 继续。

### Runner 模式（两平台默认 — Runner 写）

```jsonc
// platforms/<platform>/state.json — Runner 每次启动新建并覆盖：进度报告，不是续跑游标
{
  "startedAt": "...", "course": "<课程名>",
  "current": { "lesson": "...", "cid": "...", "type": "video", "t": 123 }, // 正在播的任务+秒数
  "results": [ { "lesson": "...", "cid": "...", "type": "video", "result": "learned" } ],
  "matrix": [ { "lesson": "...", "type": "视频", "cid": "...", "learned": false } ], // 发现快照
  "paused": "video-stuck",               // 原因字符串或 null（不是布尔）
  "pausedDetail": "...",
  "ticks": 42, "done": false
}
```

- `paused` 词表（两平台 Runner，重跑即续跑，词表内注明例外）：见 SKILL.md §3.1（学习通）
  与 §4.4（icourse163）。除进程内等待类（`waiting-sms-code`、`qr-wait`、`captcha`）
  外，全部意味着 Runner 进程已退出。
- 处理约定：监督者读 `paused` → 按 SKILL.md 词表处理 → **重跑 Runner 即续跑**
  （任务自动发现会跳过已完成；不要手改 state.json 来"恢复"）。
- 与 v0 草案的偏差（`paused` 承担了 pauseReason 的角色、每次启动覆盖重建）记录在案；
  统一回双字段的时机 = 提取 core/ 引擎时（见 roadmap Phase 2）。

## 许可与知识来源

- 本仓库代码：MIT，独立实现。
- 接口/页面**事实知识**学习自 Samueli924/chaoxing（GPL-3.0）、ocsjs/ocsjs（MIT）等
  开源项目与自己的实测。事实（接口 URL、参数名、选择器）不受版权保护，但
  **未搬运上游代码**；若未来移植上游代码，相应文件须改按 GPL-3.0 授权。
- 参考克隆放在 `_ref/`（已 gitignore），永不并入本仓库。
