# Roadmap

## Phase 0 — 实测数据采集（进行中）

在真实账号上用"agent 监督的浏览器手动模式"跑完一门真实课程（大学物理，65 任务点）。
产出：`docs/field-notes.md` 里的现场异常记录 —— 这些是后续一切开发的测试用例库。

规则：不超 2 倍速、不并发、不伪造请求；每章核对进度计数；日上限触发即收工。

## Phase 1 — 仓库骨架与知识库（本次完成）

- README / LICENSE / 架构文档 / 现场日志模板
- `knowledge/chaoxing.md`：浏览器侧实测知识 + 上游接口知识合并
- `SKILL.md` 运行手册（harness 无关）
- `scripts/keepalive.js` 保活脚本独立版（重构自实测 v2，待回归验证）

## Phase 2 — Runner MVP　【状态：icourse163 实战完成两门课；chaoxing 无头被风控切出，学习通以可见浏览器监督模式实战完成；核心优化已落地（只读信标 / 字体映射自举 / 自适应巡检 / 凭据自助登录）；core/ 提取待定】

> 2026-09-16/17 实战 + 优化轮（学习通**锁速课程**）：
> - **场景打通**：教师锁定倍速（接受 1x）+ 视频中途弹题 + 观后题三段式 ——
>   《食品营养与食品安全》**60/60 任务点**（30 小节；30 节观后题全部一次提交、27 满分、
>   1.1=83.3 / 6.3=66.7 / 7.1=66.6；**37 道中途弹题 36 道首答正确**、1 道重答通过；
>   零验证码、零日上限、零进度异常）；《论文写作初阶》进行中（18/68 起）。
> - **新增工具**：`scripts/keepalive.beacon.js`（只读信标：不写倍速、不调 play/pause，
>   锁速课程专用——v2.1 会钉 2x 故禁用）、`scripts/fontmap-merge.mjs`（字体映射自举 + 解码，
>   含 `--self-test`，离线自测通过）、`knowledge/cx-font-map.json`（映射表种子）、
>   `docs/templates/continue-prompt.md`（交接模板）。
> - **策略更新**：自适应巡检阶梯（architecture.md，不预设哪些小节纯视频，按信标动态切换）；
>   **凭据由用户交付、监督者自助登录与自助重登**（安全规则第 11 条修订，用户 2026-09-17 授权）；
>   探索预算（未知结构最多试 2 配方）；答题口径入库（近义项同键 / 判断题随课程立场 /
>   提交即计入完成与分数无关）。
> - **待实战验证**（下一轮跑课程②③时验证）：字体映射暖机后的读题 token 下降幅度、
>   自适应节奏的调用数下降幅度。
> - **PR 时机**：本轮优化建议先由下一轮实战验证，再向 upstream 提 PR（避免把未验证的
>   参数调优当成果推出去）。

> 2026-09-14 实战结果：
> - **icourse163 马原课**：Runner 新周 7 视频 + 7 文档全部 learned（14/14），done 正常退出。
> - **chaoxing 网络安全培训**：无头 Runner 反复被风控切出会话（三次扫码登录均失效）→
>   改用 ZCode 侧边浏览器（IAB，可见+焦点在视频）监督模式完成 1.10–1.19 共 10 节收尾
>   （19/19），期间 9010 反爬验证码由监督者 agent-first 一次通过。新实测 7 条已入
>   field-notes（enc 轮换/侧栏懒渲染/完成记录传播延迟/icon_Completed 权威标记等）。
>   chaoxing 无头 Runner 结论：**不可用（被切出）**，后续方向 = 有头 Runner 或可见浏览器
>   监督模式固化为学习通标准形态。

> 2026-09-12 进展：
> - icourse163 首轮运行中按本架构落地原型（`workspace/default/mooc-runner/`，playwright-core
>   无头 Edge + 扫码登录），视频/文档阶段全流程验证通过；
> - **已收编**至 `platforms/icourse163/`（runner + qr-login + 平台 README），并改进两处：
>   任务来源从硬编码 cid 清单改为**自动发现**（扫描课件矩阵、跳过 learned，原版会漏掉新周
>   内容），登录态路径支持 `MOOC_PROFILE_DIR` 指向外部 profile；干跑验证通过（真实登录态 →
>   发现 0 待办 → 正常退出）；
> - 原路径保留可用，下周续跑两边皆可。
> - **SKILL.md 双平台化**（同日）：skill 改名 `auto-online-course-agent-skill`，新增平台路由 + icourse163
>   Runner 运行手册（登录/监督循环/paused 词表处理表），补 `courses/icourse163.example.json`；
>   state 协议修订为 v0.1（如实记录学习通监督者手写与 icourse163 Runner 写两形态）。
> - **自适应登录 + 不占电脑**（2026-09-14）：
>   - 新增 `platforms/chaoxing/runner.mjs`——学习通无头 Runner（MVP，待实测）：自动发现
>     章节、真实 2x 播放、`mArg.isPassed` 假完成防御重播、日上限/弹题/验证码即停；
>   - 两平台凭据自适应：**每次登录前监督者向用户询问本次账号（安全规则第 11 条）**；
>     凭据经环境变量（本次运行有效）或 credentials.local.json（用户明确要求才写，本地已
>     gitignore）传入；登录通道自动降级（学习通 会话→密码→扫码；icourse163
>     会话→密码→短信→扫码人工）；**无历史记忆（login-hint 已移除）**，账号数据只保留本地；
>   - icourse163 Runner 增加密码通道（页面自身表单，风控拒绝自动降级短信）；
>   - **无头 Runner 成为两平台默认形态**（不占用户电脑），浏览器监督模式降级备选；
>     临时有头开关 `CHAOXING_HEADED=1` / `MOOC_HEADED=1`（测验读题/侦察用）；
>   - state 协议修订为 v0.2；新增安全规则第 9/10 条（滑块不绕过、凭据纪律）。
> - core/（平台无关引擎）暂不提取：目前只有一个 runner 实现，过早抽象是投机；等 chaoxing
>   runner 落地后从两个实现中提炼真正的公共部分（watchdog/pauseReason/凭据握手）。

- Playwright 驱动真实浏览器 + 独立 user-data-dir（登录一次持久有效）
- 实现状态文件协议（见 architecture.md）与确定性循环：
  播视频 → ended → 下一节 → 跳过无任务点节点 → 遇异常写 pauseReason 停下
- 保活逻辑从"注入脚本"改为 Runner 原生控制
- ~~验证策略：先拿第二门课程（非当前主力课）实测~~ → 已按此执行（icourse163 马原课），视频/文档阶段验证通过

## Phase 3 — 模式配置化

- intervention / cadence（自适应巡检阶梯，2026-09-17 新增旋钮）/ concurrency 三旋钮 +
  safe/token-saver/efficient 预设
- 多账号：多 profile、多状态文件、汇总面板
- 节奏模拟参数化（随机等待、每日时段窗口、日任务量上限）

## Phase 4 — 产品线扩展

- 油猴/浏览器插件版（从 knowledge/ 生成选择器，复用 keepalive 逻辑）
- 其他平台（智慧树、雨课堂…）：每平台一份 knowledge 文件 + 在 SKILL.md 平台路由表中
  增加一行（学习通与中国大学MOOC 已按此模式接入，无需每平台单拆一份 SKILL.md）

## Phase 5 — 发布

- private 仓库打磨 → 补足免责声明与风险文档 → public
- 把日上限检测等新发现提 PR 回上游（Samueli924/chaoxing），积累社区信誉
