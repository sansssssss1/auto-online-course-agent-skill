# 续跑提示词（2026-09-18 交接 · 课程③《Python语言基础与应用》）

> 本文件由 2026-09-18 凌晨会话固化。复制整段发给新会话即可。**课程②已全部完成，本提示词只针对课程③。**

---

任务：完成学习通课程 **③《Python语言基础与应用》** 的挂机（阶段二）；经我确认全完成后，
落成 skill 改进并向上游提 PR（阶段三）。本提示词承接 2026-09-17/18 的会话；
**动手前先读下面列的落盘文件**。

## 一、环境与仓库
- 仓库：`C:\Users\Sqxart\.zcode\workspace\default\auto-online-course-agent-skill`
  （origin = 我的 fork；upstream = 朋友仓库）；**分支必须是 `feat/locked-rate-optimizations`**
- 浏览器/运行形态：学习通 = ZCode 侧边 IAB **可见监督模式**，**面板必须保持可见**（无头会被风控切出）
- 截图通道：进入 studentstudy 后 `tab.screenshot()` 受限（`guest`）→ **取题走页面内 canvas 渲染**
- 登录：**本次账号与凭据开工时向我索取**（默认沿用 `credentials.local.json` 里的 main 账号）；
  **掉线自行重登，不用再问我**；凭据只写 `credentials.local.json`（已 gitignore）或临时环境变量

## 二、动手前必读（按顺序）
1. `SKILL.md` 全文（安全规则是硬约束；**第 3 条已升级为「尽量拿高分、重做自行推进」**）
2. `knowledge/chaoxing.md` §11（锁速课程场景）§11.7（IAB 前台红线）§11.8（重做口径）§12（字体混淆负结果）§13（跨源 iframe 配方）§14（自助重登）
3. `docs/field-notes.md` **最后 4 条**（尤其：静默暂停须跨帧点 `.vjs-play-control`、
   重做必须 `setExact` 精确设定、提交后 hidden 消失、阶梯 v2 的 120s 硬边界）
4. 仓库根 `state.json`（已 gitignore）：课程 ID、chapterId 全表（课程③ 69 行全在案）、断点
5. 仓库外台账：`C:\Users\Sqxart\.zcode\workspace\default\cx-ledger.txt`（尾部即断点）

## 三、安全红线（不得放宽）
- 只真实播放；**倍速被锁 → 接受 1x**，禁止任何对抗（不注入改播放器脚本、不碰进度接口）
- 锁速课程**禁止注入 `scripts/keepalive.js` v2.1**（会钉 2x）→ 只用 `scripts/keepalive.beacon.js`（只读信标）
- 跳页间隔 ≥4 秒；不拼直链绕开学生页包装层；**ckenc 一次性 → 必须从课程卡真实点击进入**
- **同一账号禁止多开**；挂机期间**不要在同一 IAB 会话开/认领别的标签**（会让视频标签停摆）
- 弹题必须**点 `input[type=radio]` 并校验 `checked`** 再提交；答错必须重答
- 出现日上限提示 / 验证码 → 立即停下汇报（重做修正除外）
- 未知页面结构：**最多试 2 种已知配方**，然后记 field-notes + 切 fallback（不连续探索）
- **阶段二禁止改代码**；阶段三等我确认课程③完成后再做

## 四、当前进度（2026-09-18 核对）
- 课程①《食品营养与食品安全》courseId=267014429 clazzid=154566739：**60/60 完成**，不用动
  （9.1 阅读 / 10.1 问卷两个 0 任务点行仍待我决定）
- 课程②《论文写作初阶》courseId=267014433 clazzid=154566929：**68/68 完成**（本轮从 36/68 跑到满分，
  全课小节均 100 分；9.1 阅读 / 10.1 问卷两个 0 任务点行待我决定）
- 课程③《Python语言基础与应用》courseId=**267014483** clazzid=**154567306** cpi=485077730：
  **0/67 未开始**。已侦察确认结构：**69 行 = 58 个视频/上机实践小节 + 9 个章节测验 + 10.1 阅读(0TP) + 11.1 问卷(0TP)**；
  **每行 1 个任务点**（视频与章节测验各自独立成节，与课程②「一节 2 任务点」不同）；
  各测验行 = `1.5/2.8/3.6/4.8/5.7/6.5/7.11/8.7/9.10`；全部 chapterId 已在 `state.json` 的 `courses[2].chapterIds`
- 课程③视频小节无配对观后题 → 单行流程更简单（1 视频 = 1 任务点；1 测验 = 1 任务点）

## 五、单行操作配方（本轮课程②实测固化，直接照抄）
1. **进课程**：个人空间 `i.chaoxing.com` 课程卡 → 用**页内** `a[href*=courseId=267014483].click()`
   （Playwright locator 会因链接在视口下方而超时）→ 新开 user tab → `browser.user.claimTab(info)` 接管
   → **关掉其余受控标签**（`(await tabs.get(id)).close()`，IAB 前台红线）
2. **目录页**：`playwright.frameLocator('#frame_content-zj')`（其 `contentDocument` 拿不到）；
   权威进度 = 帧内 `已完成任务点: N/67`；行 = `.chapter_item[onclick*=toOld]`（行尾数字 = 该行未完成任务点数）
3. **进小节**：`.chapter_item[onclick*="{chapterId}"].evaluate(el => el.click())`
4. **学习页注助手**（一次）：注入 `scripts/keepalive.beacon.js`（用 `new Function('try {'+IIFE+'; return "OK" }')`），
   再安装 `window.__cxDocs()`（遍历同源帧）/`__cxStart()`（帧遍历点 `.vjs-big-play-button`）/
   `__cxRenderQuiz()`（canvas 渲染题目为 PNG dataURL）/`__cxQuizInfo()`
5. **切小节**：顶层 `.posCatalog_select#cur{chapterId} > .posCatalog_name` 程序化 click = **页内切换**，
   信标与助手**整门课存活**
6. **巡检**：单次调用 `waitForTimeout` 到 ~115s（**120s 工具上限是硬边界**）→ 读一行信标
   `[cx]t=/|p=|e=|q=|r=|i=`；`p=1 且 i≥8` → **帧遍历**点 `.vjs-play-control` 就地恢复；
   `q=1` → 弹题流程；`e=1` → 同一调用内「核对 `ans-attach-ct.videoContainer` 的 `ans-job-finished`
   → 点 `#dct2` → `__cxRenderQuiz()` 存 PNG」（省一次调用）
7. **弹题**（若出现）：DOM 明文读题 → 点 `input[type=radio]` → 校验 `checked` → `a#videoquiz-submit`
   → 判据 `.tkTopic` 消失；答错重答
8. **章节测验**：读 PNG 题图 → `setExact(答案)` → 校验 hidden `input[name='answer{qid}']` →
   `a.btnSubmit` → 顶层 `.popDiv.Marking #popok` → 读明文「我的答案/正确答案」→
   **未满 100 就「重做 → 确认 → `setExact(正解)` → 提交」一次到满分**
9. **完成核对**：侧栏 `.posCatalog_select` 行尾数字清零（比 `icon_Completed` 更实时）；
   每完成一章更新 `state.json` + `cx-ledger.txt`；**每完成一门课按本模板再交接一次**

## 六、阶段三清单（**必须等我确认课程③完成后**再做）
1. 更新 `knowledge/chaoxing.md`（§11.8 重做口径、§12 字体映射负结果、阶梯 v2 的 120s 硬边界）
   与 `SKILL.md`（§0 安全规则第 3 条、§3.2 巡检阶梯 v2 改写、§3.3 恢复配方跨帧）
2. 在 `feat/locked-rate-optimizations` 分支追加提交 → push origin →
   向 upstream 提 PR（描述含：锁速场景、beacon 实战数据、阶梯 v2 修正的实测边界、
   fontmap 负结果、重做策略与 `setExact` 细节）
3. **不直接改上游、不 force push**
4. 收尾按安全规则第 12 条清理本地运行产物（真实课程配置、`state.json`、日志、题图）
