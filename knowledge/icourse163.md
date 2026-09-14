# 中国大学MOOC（icourse163.org）知识库

> 来源：2026-09-12 首轮实测（桌面《MOOC网课挂机-进度与上下文总结.md》+ 现场日志）。
> 验证课程：马克思主义基本原理（<某高校>）tid=<id>。
> 状态：视频/文档流程已全流程验证；课程按周发布，测验未发布，待续跑。

## 1. 平台与页面结构【实测】

- SPA + hash 路由，**切换视图不整页刷新**（注入脚本可存活；整页刷新后必须重注入）
  - 课件列表 `#/learn/content`；测验列表 `#/learn/testlist`
  - 单元详情 `#/learn/content?type=detail&id={unitId}&cid={contentId}`
- **播放器在顶层文档，无 iframe 嵌套**（与学习通相反，结构简单得多）
  - 链：`.m-learnunitUI` > `.j-unitctBox.unitctBox` > `.mooc-video-player` >
    `.ux-video-player` > `.u-edu-h5player` > `.u-edu-h5player-mainvideo` > `video`
- 视频流 MSE blob（vod.study.163.com），带令牌加密（`freeVideoDecryptByKey` /
  `getResourceTokenV2.rpc`）——**只真实播放，不碰解密**

## 2. 课件列表【实测】

- 章节块 `.m-learnChapterNormal` 默认**折叠**：程序化点击 `.titleBox` 展开
  （小节内容经 `CourseBean.getLessonUnitLearnVo` dwr 接口拉取渲染）
- 小节 `.u-learnLesson` > `h4.j-name`；任务点 `.sourceList > .f-icon.lsicon[data-cid]`（每节视频+文档并排）
- 类型 = 子元素 `.tag` 文本（视频/文档）；**完成标记 = lsicon 带 `learned` 类**
- 打开任务点 = 程序化 click 该 lsicon → hash 切到 detail 视图
- **课程按周发布**：未发布时测验页显示「老师还没有发布测试和作业，请耐心等待」

## 3. 播放器【实测】

- 倍速：`.j-ratebtn` → `.m-popover-rate li`，**6 档动态渲染**（首次只抓到 0.75~1.5 四档是陷阱），
  官方最高 2x；设置持久化（刷新后仍 2x）
- 自动连播：`input.j-autoNext` 默认 checked=true；播完 hash 自动切下一单元
- 播放控制：`.j-bigplaybtn` / `.j-playbtn`；**状态机脆弱——直接 `video.play()` 或合成点击会死锁**，
  恢复走播放器按钮事件序列或整页 reload；保活脚本只钉参数（rate/muted）+ 记录状态，绝不碰播放控制
- **SPA 复用 video 元素**：自动连播切单元后，旧 watchdog 会读到新单元的进度（无害）；
  watchdog 应以 hash 切换为准切任务，不依赖 video 元素存续

## 4. 环境约束（IAB vs Runner）【实测】

- **IAB 窗口不可见/最小化 → rAF 冻结 → 播放器停摆**（网络请求归零、一切点击无效、截图超时；
  `visibilityState` 仍报 visible，不可信；缓冲与 video.error 均正常——识别特征是 rAF 零帧）
  → 唯一可靠恢复 = reload 页面（自动续播、倍速/进度/静音保留）
- 无头 Runner 不受显示器/窗口可见性影响（虚拟渲染管线）——**长挂机用 Runner，IAB 只做侦察与交互**
- IAB 视口需 ≥1600×900（1280×720 时播放器溢出视口外不可点击）

## 5. 登录【实测】

- 新设备密码登录被平台拒绝（「为了您的账号安全，请设置登录密码」风控）
- 短信验证码登录触发**易盾滑块**（真实出现，250×125）——守约束不绕过
- **扫码登录可行**：登录弹窗底部「手机扫码，安全登录」；成功判定用 `window.webUser`
  （不能用登录按钮可见性判断）；二维码过期检测勿匹配裸「刷新」文本（常驻刷新按钮会误触发）
- 登录表单在 iframe 内，手机号/邮箱两面板的密码框 placeholder 相同 → 用 `:visible` 过滤
- 凭据原则：验证码/密码经环境变量与文件握手，**不写入脚本与状态文件**；登录态存 Runner 的 edge-profile

## 6. 反挂机检查【实测】

- 首查未发现每日上限/验证码/警告弹窗（比学习通宽松）
- 进度口径：任务点 lsicon 的 `learned` 类；整体进度接口 `mocCourseV2RpcBean.getMemberLearningRate.rpc`
- **learned 阈值偏宽**（视频部分观看即点亮、文档打开约 25 秒即点亮）——本项目仍坚持真实完整播放，
  不依赖宽口径
- 网传「点进视频马上退出即计完成」未采用；侦察阶段未发现平台风控，但不代表教师端无统计口径风险

## 7. Runner【实测，已收编】

- 仓库内位置：`platforms/icourse163/`（`runner.mjs` 主程序 + `qr-login.mjs` 扫码登录 +
  平台 README；原路径 `workspace/default/mooc-runner/` 保留，登录态 `edge-profile/` 在那边，
  **勿入库、勿外传**）
- 用法：`MOOC_PROFILE_DIR=<profile 路径> node runner.mjs [--course <file.json>]`；
  首次登录跑 `qr-login.mjs` 出 `qr.png` 扫码；课程配置示例 `courses/icourse163.example.json`
- **监督者运行手册（登录/监督循环/paused 词表处理表）见 SKILL.md §3**
- 任务来源：**自动发现**——扫描课件矩阵，跳过 `learned`，视频优先、文档其次
  （2026-09-12 收编时改进：原版硬编码 cid 清单会漏掉新周发布的内容）
- 已实现：展开折叠章节、跳过已 learned、2x 静音真实播放、看门狗（stall→reload ≤3）、
  播完回列表核对 learned、文档三轮打开、终态矩阵核对、正常退出（干跑验证通过）
- 待办：测验任务处理（发布后按 SKILL.md §4.1 从严执行）；state 协议已按实际实现文档化为
  architecture.md v0.1（`paused` 单字段保留，等 core/ 提取时再评估统一）

## 8. 待办（下一轮续跑）

1. 新周内容发布后 Runner 续跑，更新 data-cid 对照表与状态列
2. 测验发布后：先查清**限次/倒计时**规则（icourse163 测验通常限次，纪律从严）→
   全部读题 → 拟答案 → 用户确认 → 只提交一次；可参考 GinsMooc/题库 API 作第二意见，以自己读题为准
3. 有新平台行为（风控、结构改版）→ 现场日志追加，同步本文件
