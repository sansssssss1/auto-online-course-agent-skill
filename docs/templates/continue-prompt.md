# 续跑提示词模板（复制整段、填 <> 占位符后发给新会话）

> 用途：会话上下文变长 / 进程中断 / 换会话时的标准化交接。**每完成一门课主动交接一次**，
> 不要等上下文"很长"才交接（两个已跑会话的 rollout 已达 38MB / 51MB）。
> 本模板由 2026-09-17 实战版（`continue-prompt-20260917.md`）固化而来。

---

任务：完成学习通课程《<课程名>》的挂机（阶段二）；经我确认全完成后，落成 skill 改进并向上游提 PR（阶段三）。
本提示词承接 <日期> 的会话；**动手前先读下面列的落盘文件**。

## 一、环境与仓库
- 仓库：`<仓库绝对路径>`（origin = 我的 fork；upstream = 朋友仓库；代理已配好/未配）
- 分支：`<当前分支>`
- 浏览器/运行形态：<学习通 = ZCode 侧边浏览器 IAB 可见监督模式（无头会被风控切出）；
  中国大学MOOC = 无头 Runner>
- **前提（学习通 IAB）**：视频只在面板可见时才走进度（新播放器实测 1x 播放不看焦点，
  但课程要求"观看时不可离开或将页面最小化"）；开工前确认我已切回本会话、面板保持可见
- 截图通道：进入 studentstudy 后 `tab.screenshot()` 受限（"guest"）→ **取题走页面内
  canvas 渲染 / DOM 明文（字体映射）**，不要反复试截图
- 登录：**本次账号与凭据由我现在交给你**（账密写进 `credentials.local.json` 或临时环境变量，
  或改扫码）。**掉线你自己重登，不用再问我**；账号信息只留在本地，不入库/不外发。

## 二、动手前必读（按顺序）
1. `SKILL.md` 全文（安全规则是硬约束）+ `knowledge/chaoxing.md`
2. `docs/field-notes.md` 最后 3–5 条 + 其中「锁速课程」相关条目
3. 仓库根 `state.json`（已 gitignore）：课程 ID、chapterId 映射、进度、断点、错题台账
4. `knowledge/cx-font-map.json`：已自举的字体映射（读题前先看它）

## 三、安全红线（不得放宽）
- 只真实播放；**倍速被锁 → 接受 1x**，禁止任何对抗（不注入改播放器脚本、不碰进度接口）
- 锁速课程**禁止注入 `scripts/keepalive.js` v2.1**（会钉 2x）→ 只用 `scripts/keepalive.beacon.js`（只读信标）
- 跳页间隔 ≥4 秒；不拼直链绕开学生页包装层；ckenc 一次性 → 必须从课程卡真实点击进入
- 观后题「全部读完 → 全部作答 → 核对 → 只提交一次」（放宽策略需我逐课程授权）
- 弹题必须**点 `input[type=radio]` 并校验 `checked`**再提交；答错必须重答（答对浮层才消失）
- 出现日上限提示 / 验证码 / 进度不点亮 → 立即停下汇报
- 未知页面结构：**最多试 2 种已知配方**，然后记 field-notes + 切 fallback 继续（不连续探索）

## 四、当前进度（<核对日期>）
- 课程①《<名>》courseId=<id> clazzid=<id>：<x/y 任务点>，成绩 <…>，断点 <…>
- 课程②《<名>》：<…>
- 课程③《<名>》：<…>
- 待定项：<例：9.1 阅读（0 任务点但计入成绩）、10.1 问卷 —— 等用户决定>

## 五、单小节操作配方（视频 + 观后题各 1 个任务点）
1. **进课程**：个人空间 `i.chaoxing.com` 课程卡 → 新标签页（带新 enc）→ `claimTab` 接管
2. **目录页**：`#frame_content-zj` 帧内 `.chapter_item#cur{chapterId}`（`title`=小节名，
   `onclick=toOld(...)`）→ **程序化 `el.click()`**；两代布局并存，`.posCatalog_select` 也试
3. **学习页**：顶层 `#iframe`(cards) → 播放器 iframe `.ans-insertvideo-online`；第 2 页测验在
   cards → `iframe[src*='ananas/modules/work']` → `#frame_content`
4. **注入** `scripts/keepalive.beacon.js`（只读信标）；起播 = 程序化 click `.vjs-mute-control`
   + `.vjs-big-play-button`
5. **巡检（自适应）**：单次调用内 5.5s 粒度探测，预算 ~105–119s；连续无异常则放大探测间隔
   （15s→30s）；`q=1`/`p=1` 持续/`idle` 增长/`e=1` → 立即回短周期处理
6. **弹题**：DOM 明文读题 → 点 `input[type=radio]` → 校验 `checked` → `a#videoquiz-submit`
   → 判据 `.tkTopic` 消失；答错重答
7. **观后题**：优先 `knowledge/cx-font-map.json` 解码 DOM 文本读题（其次 canvas 渲染 PNG）；
   作答 → 校验 hidden `input[name='answer{qid}']` → `a.btnSubmit` → 顶层 `.popDiv.Marking a.jb_btn`
   → 判据「已完成·第N次作答·本次成绩X分」
8. **提交后**：抓"明文题干 + 正确答案"→ `scripts/fontmap-merge.mjs` 自举映射（越跑越省 token）
9. **完成核对**：侧栏行 `icon_Completed` + 任务点计数变化；每完成一章更新 `state.json`

## 六、阶段三清单（**必须等我确认全完成后**再做）
1. 更新 `knowledge/chaoxing.md`（本轮新场景与新口径）、必要时 `SKILL.md`
2. 建分支（如 `feat/<主题>`）→ commit（说明写清依据）→ push origin → 向 upstream 提 PR
3. PR 描述含：场景说明、实测证据（引用 field-notes 条目）、改动文件清单
4. **不直接改上游、不 force push、阶段二禁止改代码**
