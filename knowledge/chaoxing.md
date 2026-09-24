# 超星学习通（Chaoxing）知识库

> 条目按来源标注：
> - **【实测】** 2026-09-11 真实账号浏览器自动化实测（详见 docs/field-notes.md）
> - **【接口】** 学习自 Samueli924/chaoxing（GPL-3.0）源码的接口**事实**。事实不受版权保护，
>   本仓库未搬运其代码；如需引用其代码，先读 docs/architecture.md 许可一节。
>
> **安全路线声明**：本项目走"真实播放"路线。接口知识用于理解平台机制、验证行为与
> 排障，**不用于伪造上报**。凡属"伪造进度"的技法一律不收录。

## 1. 会话与 URL

**【实测】**
- 入口目录页：`mooc2-ans.chaoxing.com/mooc2-ans/mycourse/stu?courseid=&clazzid=&cpi=&enc=`
- 播放页（旧版学习页，一切自动化的现场）：
  `mooc1.chaoxing.com/mycourse/studentstudy?chapterId={id}&courseId=&clazzid=&cpi=&enc=&mooc2=1&hidetype=0&openc=`
  - 只需替换 `chapterId` 即可直达任意节点
  - `enc` / `openc` 是**会话级**参数，登录会话内可复用；失效则回目录页重取

**【接口】**
- 登录：POST `passport2.chaoxing.com/fanyalogin`，密码 AES-CBC（key=iv=`u2oh6Vu^HWe4_AES`）后 base64
- Cookie 可持久化复用，失效自动重登；二维码登录上游未实现
- 课程列表：POST `/mooc2-ans/visit/courselistdata`；章节树：GET `/mooc2-ans/mycourse/studentcourse`
  （解析 `chapter_unit` → knowledgeid / jobCount / 完成标记）

## 2. 播放页结构

**【实测】iframe 链**（全部同源 mooc1.chaoxing.com，可跨层访问）：

```
顶层文档
├─ #iframe → knowledge/cards 知识卡片页
│   ├─ iframe.ans-insertvideo-online → 视频播放器（内含 <video>）
│   └─ iframe[src*='work'] → 作业模块加载器
│       └─ iframe#frame_content（mooc-ans/api/work）→ 真实测验页（.TiMu / .questionLi）
```

> **2026-09-14 增补（新版 mooc2-ans 目录页）**：新版课程目录（任务/章节页签布局）**没有**
> `toOld`/`.chapter_item`，章节树在 `studentcourse` iframe 内，行结构 =
> `.posCatalog_select#cur{chapterId}` > `.posCatalog_name`（onclick=getTeacherAjax）；
> 完成标记 = 行内 `.icon_Completed`（权威，实时），`.posCatalog_name` 可程序化点击跳章。
> 旧 `.chapter_item`/`toOld` 结构仅适用于旧版页面。另：`enc` 每次进入课程都轮换，
> 失效页显示「无效的参数」，重取路径 = 个人空间 i.chaoxing.com 课程卡片
> （opencoursenewfy 链接）。详见 docs/field-notes.md 2026-09-14 条目。

**【实测】关键 DOM**
- 「下一节」`#prevNextFocusNext` /「上一节」`#prevNextFocusPrev`（顶层文档）；点击后**整页跳转** → 保活脚本需重新注入
- 目录节点 `div.chapter_item#cur{id}`，onclick=`toOld(...)`，被透明 `<a>` 遮罩覆盖 → 必须程序化 `el.click()` 冒泡，常规坐标点击会失败
- **【接口】卡片页内 `mArg={...}` JSON 的 `attachments` 就是任务点数组**
  （type: video/document/workid/read/live，`isPassed=true` 已完成）——比解析 DOM 稳，优先读它

## 3. 视频任务

**【实测】**
- `preload="none"` 的视频必须显式 `play()` 一次才开始加载；"等 readyState 再 play"会死锁
- 2 倍速静音真实播放，进度被平台正常记录（目录 ✓ 实证）；2 倍速是播放器官方最高档
- **`video.ended` ≠ 任务点已记录**：出现过 ended 但完成心跳未发的"假完成"（9.15–9.22 实测）——
  每个任务点完成后必须核对平台侧完成标记（播放器 `icon_Completed` / 目录 ✓），缺了就重播
- ended 后播放器可能自动从头重播 → ended 后尽快点「下一节」
- 视频偶发卡住（paused、time 不走、无 error、缓冲正常）→ `pause()→play()` 强推可自愈；
  识别特征：tick 间隔内 time 零增量
- **【预警·待实测】部分视频倍速锁死 1x、禁止快进**，且通常带中途弹题 + 观后题目
  （用户手机客户端经验，本账号暂未出现，预计近期出现）：遇到 `playbackRate` 设不上去就
  **接受 1x 真实播放，不对抗**；中途弹题走弹题流程，观后题按测验流程处理
- 自动循环与保活逻辑见 `scripts/keepalive.js`（v2.1 = 保活 + 事件驱动恢复，见 §8.5）

**【接口】（理解机制用，浏览器路线原生播放器自行完成上报）**
- 视频元数据：GET `/ananas/status/{objectId}?k={fid}&flag=normal` → dtoken/duration/crc/key
- 进度上报：GET `/mooc-ans/multimedia/log/a/{cpi}/{dtoken}`（playingTime/duration/clipTime/dtype 等）
- 请求带 `enc` 校验参数（md5 拼接串 + 固定 salt，详见上游 `api/base.py`）；**浏览器路线无需复算**
- 服务端倍速钳制 1.0~2.0；上报限流 2s+random(0~2)s；心跳间隔 30~90s 随机

## 4. 文档 / 阅读 / 空章节【接口】

- 文档：GET `/ananas/job/document?jobid&knowledgeid&courseid&clazzid&jtoken` → HTTP 200 即完成
- 阅读：GET `/ananas/job/readv2?jobid&knowledgeid&jtoken&courseid&clazzid`
- 空章节：GET `/mooc-ans/mycourse/studentstudyAjax` 访问一次

## 5. 测验 / 作业

**【实测·浏览器路线】**
- 题目文字经字体混淆（`font-cxsecret`），DOM 乱码 → **截图读渲染后的文字**；
  旁路技巧：公式选项是普通 `<img>`（按 src 尾部区分选项），混淆汉字可按上下文建小映射解码
  （实测例：弨=的、弤=球、妶=径、廲=电、彚=两）
- 选项元素：每题 4 个 `li onclick="addChoice(this)"`，选项字母在 `span.num_option` 的 data 属性；
  作答 = 对目标 li 程序化 `.click()` → 答案写入 hidden `input[name='answer{qid}']`（value=字母）；
  **校验只读这些 hidden input，无需截图验证**
- 进测验节点可能弹「当前章节还有任务点未完成」→ 调页面自身 `closeDeleteWindow()`
  （页面共存 8 个同名 `.popClose`，必须限定作用域）
- 提交流程：最内层 `a.btnSubmit`（「提交」）→ **顶层文档**确认层 `.popDiv.Marking`
  （`#popcontent` 文本「确认提交？」）→ 点其中文字为「提交」的 `a.jb_btn`（勿点取消）
- 成功判据：页面显示「已完成 · 第N次作答 · 本次成绩X分」且 `a.btnSubmit` 消失
- **只提交一次**；实战战绩 1.4=100、2.6=100、3.5=80、4.6=80

**【接口】**
- 取题：GET `mooc-ans/api/work`（api=1&workId&jobid&knowledgeid&…），解析表单隐藏字段 + 题目列表
- 提交：POST `/mooc-ans/work/addStudentWorkNew`，字段 `answer{id}` / `answertype{id}` / `answerwqbid` / `pyFlag`
- **`pyFlag` 是天然安全阀**：`""` = 直接提交，`"1"` = 仅保存不提交 —— 信心不足时只保存，人工核对后再交
- 判分：GET `/mooc-ans/work/record-list` + `/work/record-detail`（解析"我的答案/正确答案"），
  上游据此做错题反馈重做（默认 3 轮）——可移植为浏览器路线的自动改错
- **【实测】上游没有任何视频弹题处理** —— 我们的 keepalive 弹题检测 + 监督者读题是差异点

## 6. 字体混淆（重要）

**【接口】上游完整解法（`api/cxsecret_font.py` / `api/font_decoder.py`）：**
- 题目页含 `<style id="cxSecretStyle">` 内嵌 base64 TTF 字体
- 用 fontTools 读 glyf 表，对每个 `uniXXXX` 字形轮廓坐标+flag 序列算 MD5，
  到预采集映射表反查真实字符，再做康熙部首替换
- 解出对象：题干 + 选项
- **选项可优先走 `aria-label` 属性通道，直接绕开解密**

**对浏览器路线**：截图读题已验证可用；`aria-label` 通道更省 token、更准，值得优先试。

## 7. 验证码【接口】

- 触发：视频进度上报返回 403 或响应含"验证码/validate"
- 上游解法：GET `processVerifyPng.ac` 取图 → ddddocr 识别 → GET `/html/processVerify.ac?ucode=xx`，302 即通过；无 OCR 则人工
- **浏览器路线原则：验证码 = 暂停 + 人工/监督者截图处理，不做自动对抗**

## 8. 风控相关（本项目差异化的依据）

**【实测】**
- 隐藏提示框 class `maskDiv jobCountDiv`：「今日视频任务点完成数已达上限，您可以观看视频，
  但无法完成任务点」→ 平台级每日上限；触发即停止当日视频任务
- 顶层文档弹窗家族（自动分类处理用）：`jobFinishTip`（任务点未完成 → closeDeleteWindow）、
  `jobCountDiv`（每日上限 → 停）、`popDeleShowHide`（笔记未保存）、`Marking popDiv`（提交确认）
- 平台存在行为监测端点 `detect.chaoxing.com/api/monitor`【接口】
- **【实测】9010 验证码门禁**（两次触发）：① 在成绩账号直接拼接 knowledge/cards 直链
  （绕过 studentstudy 包装页、参数不全 + 异常访问模式）；② 90 秒内连点 27 次「下一节」。
  **解决流程（可复用）**：验证码图（`processVerifyPng.ac?t=...`，同源）用页面内
  `fetch(src,{credentials:'include'})` 转 base64 → 用户读码 → 填 `#ucode` →
  点 `input.submit`（GET `processVerify.ac`）→ 302 回学习页。锁屏截图不可用时，
  fetch-base64 是唯一把验证码图拿出来的通道；读码由谁做（agent 自读 vs 用户）按课程
  `captchaPolicy` 配置，见 SKILL.md §3.4
- **【实测】导航节奏红线**：跳页间隔 ≥4 秒、每轮跳页 ≤10 次；页面卡在 empty 超过 ~2 分钟
  就等待/刷新包装页——**永远不要拼直链绕过包装页**

### 8.5 焦点 / 熄屏 / 锁屏（播放存活协议）【实测】

- 页面无键盘焦点（`document.hasFocus()===false`）时播放器**主动暂停**（play 后 3ms~2.5s 即 pause，
  或 5~8 秒周期），且保活脚本的 setInterval 被浏览器重度节流 → 纯定时器方案失效
- **事件驱动恢复**：video 挂 `pause` 监听 → 立即重播（1.5 秒限流；ended/弹题让行）——
  事件监听不受节流影响，实测 ~0.2x 恢复到 2.0x；**onboard 必须同时装保活 + 事件恢复**
  （已合并进 scripts/keepalive.js v2.1）
- 熄屏（显示器关、未锁屏）：事件恢复仍有效（~1.97x）；夜间截图会拿到过期帧（合成器冻结）→
  截图前 setViewportSize 微调强制重绘（顺序=滚动→重绘→截图）；滚动容器是顶层文档 html 元素；
  CUA 滚轮/键盘熄屏下 30 秒超时，别用
- 锁屏（Win+L）：原生层毫秒级暂停，页面脚本无法对抗 → 唯一有效 = 监督者侧 3.5 秒高频踢循环
  （~1.91x），或不锁屏挂机
- 锁屏下渲染器对远程指令挂起（子框架不加载、注入无效）时：**请用户在电脑前真实点击一次
  目标节点即可恢复**——真实点击能触发子框架加载，远程操作不能（网络安全课 1.19 实测）

**【接口·上游的节奏参数，可照抄为 Runner 的等待策略】**
- 普通接口 0.5s；视频上报 2s + random(0~2)s；元数据刷新 random(≤0.2s)；章节间 random(≤0.2s)
- 心跳 30~90s 随机；403 恢复等待 random(2~4)s
- 上游会向 monitor 端点发 JSONP 心跳伪装浏览器行为——本项目**不做**（对抗性伪装超出保守路线）

## 9. 生态参考【接口】

- 题库 provider（上游 answer.py 注册表）：言溪（tk.enncy.cn）、TikuGo（q.icodef.com）、
  TikuLike（app.datam.site）、自建 Adapter、任意 OpenAI 兼容 AI、SiliconFlow（默认 DeepSeek-V3）、手动输入
- 组合方式：`provider=A,B` 顺序回退；答案过题型校验 + 本地缓存；AI 支持错题反馈重试
- 通知 provider：ServerChan / Qmsg / Bark / Telegram
- 并发：上游线程池默认 4 章节并发 —— 本项目保守路线默认 1，并发属 Phase 3

## 10. 对浏览器路线的启示（策展版）

1. 任务点识别优先读 knowledge/cards 页的 `mArg` JSON，比 DOM 解析稳
2. 测验读题四条通道按序试：① 自举字体映射解码 DOM（§12，最省）；② 页面内 canvas 渲染 PNG；
   ③ `aria-label`（仅部分明文）；④ 截图（IAB 下多不可用）
3. `pyFlag="1"` 只保存是测验提交的安全阀
4. 上游 RateLimiter 的节奏参数可直接移植为 Runner 的 wait 策略
5. 403 + 验证码是核心拦截点，设计成"暂停 + 监督者处理"而不是自动对抗
6. 弹题处理上游为零 —— keepalive 检测 + 监督者读题是本项目差异点之一

## 11. 锁速课程场景（倍速锁定 + 中途弹题 + 观后题）【实测 2026-09-16/17】

> 验证课程：《食品营养与食品安全》（60/60 完成）、《论文写作初阶》（进行中）。
> 原始样本见 docs/field-notes.md 2026-09-16/17 条目。

### 11.1 结构与完成口径
- 新版目录：`mooc2-ans.chaoxing.com/mooc2-ans/mycourse/stu` → 章节 iframe `#frame_content-zj`
  → 行 `.chapter_item#cur{chapterId}`（`onclick="toOld('courseid','chapterId','clazzid',0)"`，
  小节名在 `title` 属性）；**两代布局并存**，旧布局为 `.posCatalog_select`，两者都要试。
  点击一律程序化 `el.click()`。
- 学习页：`mooc1.chaoxing.com/mycourse/studentstudy?chapterId=…`；**每个小节 = 页签
  「1 视频」+「2 章节测验」**（2 个任务点）；"下一节"是新版**页内翻页**（不是旧版
  `#prevNextFocusNext`）。
- 完成口径（cards 页原文）：「观看时长需 ≥ 总时长的 90%（未完成任务点前，当前视频不可拖拽、
  观看时不可离开或将页面最小化）」→ **时长制，页面必须保持可见**。
- 侧栏行 `icon_Completed` + 任务点计数（2→1→0）是可靠的分任务点完成信号。

### 11.2 倍速锁定的 DOM 特征
- 外层 `div.vjs-playback-rate.vjs-menu-button.vjs-menu-button-popup.vjs-control.vjs-button`
  带 **`vjs-hidden`**（display:none）；内层 `button[title="播放速度"]` 的
  `aria-disabled` 仍为 false——**锁的是控件可见性，不是 disabled**；
  `.vjs-playback-rate-value` 只显示「倍速」无数字；`video.playbackRate` 恒为 1。
- 拖拽锁提示：`#tipDiv .toolTipBox1`（默认 display:none）——「该视频教师已设置限制：
  未完成任务点前无法拖动或定位进度，完成任务点后即可拖动复习。」
- **处置：接受 1x，不对抗**（禁注入会写 `playbackRate` 的 keepalive v2.1；
  只读巡检用 `scripts/keepalive.beacon.js`）。

### 11.3 中途弹题（`.tkTopic`）
- 容器：`.x-container.ans-timelineobjects`（z-index 101）> `.ans-videoquiz#videoquiz-*`
  > `.tkTopic` > `.tkTopic_con.tkScroll`；选项 `li.ans-videoquiz-opt > label > span.tkRadio
  > input[type=radio][name='ans-videoquiz-opt']`（多选为 checkbox）；按钮
  `a#videoquiz-submit` / `a#videoquiz-submitting` / `a#videoquiz-continue`。
- **题面 DOM 明文**（无字体混淆），无需截图。
- **正确流程**：点 `input[type=radio]` → 校验 `checked===true` → `a#videoquiz-submit`
  → 判据 `.tkTopic` 消失 / 视频继续。**点 `li` 无效**（自定义 UI 不转发，提交空答案必判错——
  曾有 3 次误判为"平台答案键与教材相反"，实为选项没选上）。
- 答错必须**重答直到答对**（重答入口重现）；弹题判定不影响任务点与观后题成绩。
- 出现时**可能暂停也可能不暂停**；已答浮层滞留 DOM → 探测须排除含「回答错误/回答正确」的文本。
- **【2026-09-18 补充】答错层滞留 + 自动续播 = 静默漏答风险**：首答判「回答错误」后浮层
  滞留可见、`a#videoquiz-submit` 仍可用（w≈92），视频**自动继续播放** → 只探测"未处理弹题"
  的话，答错会被当已处理而漏掉。处置：① 信标 v1.1 起单独上报 `qw=1`（答错滞留层），
  巡检见 `qw=1` 必须重答；② 重答很简单——直接重选对的 `input[type=radio]` → 校验 checked
  → 再点同一个 `a#videoquiz-submit`，判定层消失。
- **【2026-09-18 新配方】任务点完成后可合法 seek，用于补答漏网弹题**：弹题若在切节后才
  冒出（信标 q=1 但人已在下一节），直接重进该节——任务点已点亮 → 拖拽锁解除（平台提示
  「完成任务点后即可拖动复习」）→ **seek 到结尾 30 秒内即可重触发弹题**，作答通过即闭环。
  实测：6.2 漏网弹题经此配方补答通过（重进后 t=0 未加载也无需等待，直接 seek）。

### 11.4 观后题（章节测验）
- cards → `iframe[src*='ananas/modules/work']` → `#frame_content` → `/mooc-ans/api/work`；
  `.TiMu.newTiMu` × N，隐藏字段 `input[name='answer{qid}']` + `answertype`（0 单选/1 多选）。
- 样本**无倒计时/限时**；`audioLimitTimesTip` 是音频附件模板，与测验无关。
- 提交流程：选项 click → 校验 hidden value → `a.btnSubmit` → 顶层 `.popDiv.Marking a.jb_btn`
  → 判据「已完成·第N次作答·本次成绩X分」。**"提交即计入任务点"不普适**：课程①样本成立，
  **课程②实测 0 分提交不点亮任务点**（平台要求重做才给）→ 一律以平台标记
  （`icon_Completed`/侧栏计数）为准；页面另给「重做(剩余 10 次)」入口。
- 读题：字体混淆只存在于**待作答态**；页面内 canvas 渲染（按 computed font `fillText`
  → `toDataURL`）可绕过截图限制。

### 11.5 答题口径（实测）
- 每题分值 = 100/题量（3 题错 1 = 66.6）。
- 多选：**近义选项会同入键**（如"对主流的问题提出反思"与"对主流问题进行反思"同键 = AC），
  但语义更远的项不入键。
- 判断题按**课程自身立场**判，不按学科常识（样本：按科斯定理口径，平台键把
  "市场交易能够保证资源的有效配置"判为「错」）。
- 弹题（`.tkTopic`）与观后题成绩互不影响。

### 11.6 环境事实
- 新版播放器**无焦点暂停行为**：`hasFocus()===false` 且 `visibilityState==='visible'` 时
  1x 持续播放（旧版 §8.5 的协议不适用）；但完成口径要求页面可见 → 面板仍需保持可见。
- 进入 studentstudy 后 IAB 截图面被破坏（`guest` / surface preparation timeout）→
  取题走页面内通道。
- `ckenc`（opencoursenewfy）**一次性**：拿快照 ckenc 直接 goto → 404 页，必须从个人空间
  课程卡真实点击进入。
- 静默暂停 3–5 次/段属正常；恢复用**验证式重试**（先确认 paused → 单击播放键 → 3 秒后
  仍 paused 才 `pause()→play()`）；识别特征 = 状态读回后 `t` 不增长。

### 11.7 IAB 前台红线与标签管理【实测 2026-09-17，重大】
- **同一 IAB 会话内 `claimTab`/切换标签 → 视频标签退后台停摆**：`t` 卡 0、paused 抖动，
  但 `readyState=4`、`error=null`、`visibilityState` 仍 `'visible'`——三件套全正常，
  **唯一可靠健康判据 = `t` 是否推进**（`hasFocus()` 不可用）。
- 恢复配方（实测立即生效）：`tabs.list()` 列出全部标签 → 关闭视频标签外的所有标签 →
  激活视频标签。
- API 坑：关标签必须 `(await tabs.get(id)).close()`（直接 `tabs.get(id).close()` 抛
  `close is not a function`）；信标注入必须 `new Function('try {' + IIFE + '; return "OK" }')`
  （`new Function('return ' + IIFE)` 静默无效）；`enc` 拼直链 goto 必报「enc校验失败」，
  必须页内点击由页面生成 enc+openc；`.popDiv` 家族全部 `display:block` 滞留 DOM，
  可见性判断用 `getBoundingClientRect().width > 0`。

### 11.8 重做与分数口径（2026-09-17 用户授权：尽量拿高分，自行推进）
- **0 分提交可能不点亮任务点**（课程② 3.7 样本：唯一判断题答错 → 0 分 → 未点亮，
  平台要求重做才给）；课程①"提交即计入"的口径不普适。
- 重做入口：测验页「重做(剩余 N 次)」；按已知正解/`wrongItems` 台账修正，
  **直到任务点点亮或余量用尽，无需逐次询问用户**；重做也走完整
  "读题 → 作答 → 校验 hidden → 提交"流程。
- 收益实证：课程② 4.1（7 题）4.2（5 题）首轮全对即满分——口径入库后首答正确率显著提升。

### 11.9 杂项配方（2026-09-18 收官轮）
- **图形选项题**：选项是图片时，页内 fetch 各选项 `img`（credentials:'include'）→ 画到
  合成 canvas 排成 2×2 网格 → `toDataURL` 出**单图** → vision 一次读四选项
  （9.10 期末实测，首提满分）。比逐图读省 vision token，也避免选项错位。
- **err=3 解码错误**：与 err=2 同配方（帧遍历 `video.load()` + muted + `play()`），
  代价同为整集重播（seek 有锁速风控风险，不做）。
- **提交卡「提交中」+ 掉登录**：整页刷新到 passport2 → 用交付凭据自助重登 → 回学习页，
  视频从服务器心跳位置续播（**凭据自助登录的实战验证**，零人工介入）。
- **sleep 模式定稿**：Bash sleep 540–570（工具上限 600s）+ 醒来单次读信标；全课
  ~450–480 次调用 vs 纯轮询估算 670+（省 ~30%）；"5–10 分钟一查"单会话不可行
  （120s 工具上限未变），但模型侧等待 token 近零。
- **【2026-09-18 重要修正】重做可用性因课程而异，提交后必须探测而不是假设**：
  - 课程②型：结果页**明文列出每题正解** + 「重做(剩余 N 次)」按钮 → 重做修正到满分；
  - **课程③型（6.5 实测）**：结果页**无明文正解、无重做按钮**（HTML 无 redo 标记），
    retest 接口返回「作答状态或作答次数已变化」→ **重做通道死路**；
  - 及格线可能是 0（页面 JS `passingStandard="0"`）→ 低分照样点亮任务点。
  处置：提交后先探测有无明文正解/重做入口 → 有则按重做流程修正到满分；
  无则记录 `wrongItems` 后**接受成绩推进**（任务点已点亮），把"是否人工重做"留给用户决定。

## 12. 字体混淆：明文通道与映射表自举【实测 2026-09-17】

- **明文通道（关键发现）**：字体混淆只在**待作答态**；**提交后**页面明文显示全部题干 +
  我的答案 + 正确答案（含讲解）→ 这是自建字库的免费来源。
- 自举流程（工具 `scripts/fontmap-merge.mjs`，纯 Node、无依赖、含 `--self-test`）：
  1. 作答前取 `.TiMu` 的 `innerText`（乱码）存 `obf.txt`；
  2. 提交后取同一批题目明文存 `plain.txt`（行序、行数一致）；
  3. `node scripts/fontmap-merge.mjs --obfuscated obf.txt --plain plain.txt`
     → 逐行逐字符对齐、投票合并进 `knowledge/cx-font-map.json`（冲突会打印供复核）；
  4. 暖机后：`node scripts/fontmap-merge.mjs --decode <乱码文本>` 直接得到明文。
- 效果：读题从"每张截图约 1–1.5k vision token"降到"文本解码 ~50 token/题"；
  **两门课已累计 120+ 张题图**，是本项目最大的 token 开销来源。
- 备注：`aria-label` 通道仅部分明文（同一页 Q1 明文、Q4 混淆），只能辅助。
- 合规：属"自己积累的知识"，不改倍速、不碰进度接口。
- **【实战判负 2026-09-17】混淆是按页随机的**：同一个"题"字在 3.6 页映射为「嶋」、
  3.7 页为「戮」；3.6 页自举 +30 条（5→35）仅页内有效，跨页复用命中 **0/218**
  → **全局映射路线不成立**，工具降级为"页内辅助"（同页重读/重做场景仍省），
  不再投入跨页方向。
- **【canvas 逐字符渲染配方（2026-09-18 实测修正，1.5 十题首答满分）】**：
  混淆字符在**独立 span** 里（多选选项 class `num_option_dx`、判断题选项带 `data=true/false`）
  → 不能整段 `fillText`，必须**逐文本节点取 computed font、逐字符绘制**；
  canvas 建在 **TiMu 所在帧文档**（@font-face 只在帧内）；先填白背景再 `fillStyle='#111'`
  （透明底 + 深色字会不可读）。此配方 + 课程立场口径 → 1.5 首答即 100 分，未用重做。

## 13. 跨源 iframe 定位配方与探索预算【实测】

| 配方 | 写法 | 适用/判据 |
|---|---|---|
| A（首选） | `playwright.frameLocator("#frame_content-zj").locator("body").evaluate(...)` | 实测可用；学习页 `#iframe`(cards) 与 `.ans-insertvideo-online` 同为 frameLocator 链 |
| B（fallback） | `domSnapshot()` 读整棵 DOM | 另一环境下唯一通道；**输出巨大，只在 A 失败时用，用完即弃** |
| C（页面内） | 帧内 `el.click()` / canvas `fillText` → `toDataURL` | 点击与取题一律走它（播放器按钮 actionability 超时；截图通道受限） |

**探索预算**：同一障碍连续失败 2 次即停手 → 记 field-notes + 用 fallback 继续推进。
实测教训：有会话在同一跨源障碍上连试 4–5 次，纯烧上下文。

## 14. 登录自持：凭据交付与自助重登【2026-09-17 用户授权】

- 策略（安全规则第 11 条）：开工前向用户索取**本次**账号与凭据（账密或扫码）；
  **获交付后监督者自行登录、掉线自行重登，不再逐次询问**；凭据只经环境变量或
  `credentials.local.json`（本地、gitignore），绝不入库/日志/外发；每次运行开始仍确认账号。
- 自检节奏：进入课程前 + 每完成一章，做一次廉价检查（请求课程列表/目录页，看是否被重定向到
  登录页）。实测教训：登录态曾在半途失效并被重定向到 `passport2.chaoxing.com/login`，
  直接卡住整轮任务。
- 重登通道（学习通）：IAB 内用交付的账密走登录表单；若出现滑块/验证码 → 按 §7 取图交用户
  （或按 `captchaPolicy`）。icourse163：Runner 自适应链（会话 → 密码 → 短信 → 扫码）。
- 自助失败（密码错/风控拒绝/验证码超时）才回问用户；**绝不复用上次运行的残留凭据**。
- 登录健康判据（2026-09-17 修正）：学习页顶层**不显示用户名**，不能以"找不到用户名"判失效；
  用页面骨架判断（host=`mooc1.chaoxing.com` 且当前非登录页 = 正常）。曾发生探针误报一次。

## 15. 章节测验（观后题）批量自动化全流程【实测 2026-09-23/24，四门课 174 节】

> 场景：教师锁速课程，视频任务点之外**每节还有 1 个「章节测验」任务点**（平台总任务点 = 视频数 × 2），
> 目标是逐节把测验做完并点亮（不是替用户拿高分，而是把任务点做掉）。
> 实测规模：人工智能与创业智慧 42 节 / 三国志导读 56 节 / 5G与人工智能 43 节 / 东南亚文化 33 节
> = **174 节**，全部提交成功，四门课平台计数随后补齐到 84/84、112/112、86/86、66/66。

### 15.1 定位与打开
- 页签在顶层文档：`li[id^='dct']`，文本形如「3章节测验」（有的节是「2章节测验」——**按文字找，别按 id 序号**）。
- 点它之后测验在 `iframe#iframe`（cards）→ `iframe[src*='ananas/modules/work']`
  → 内层 `#frame_content`（或再嵌一层）里的 `.TiMu`。轮询 ~14 s 等 `.TiMu` 出现。
- 若弹出「当前章节还有任务点未完成」→ `window.closeDeleteWindow()`（**只在点提交之前调**，见 15.4）。

### 15.2 读题：用 canvas 把整段题面渲染成图（关键配方）
题面字体混淆（`font-cxsecret`）**按页随机**，逐字建映射表跨页命中率极低（§12 已证），截图在
IAB 内常不可用。最省的做法是**用页面自己的混淆字体把「题干+选项」整段画到 canvas**，读出来的就是
通顺中文——不需要任何映射表：

```js
await fc.fonts.ready;
const fam = getComputedStyle(fc.querySelector(".font-cxsecret")).fontFamily;
const lines = [];   // 每题的题干和每个选项各占一行，手工拼
const cv = fc.createElement("canvas"); cv.width = 1000; cv.height = 1400;
const c2 = cv.getContext("2d");
c2.fillStyle = "#fff"; c2.fillRect(0, 0, cv.width, cv.height);
c2.fillStyle = "#000"; c2.font = "24px " + fam;     // ← 用混淆字体家族
lines.forEach((ln, i) => c2.fillText(ln.slice(0, 42), 10, 30 + i * 28));
const png = cv.toDataURL("image/png");               // 落盘后交给视觉读图
```
- 画布 1000×1400 够放 4~6 题；把 `canvas.toDataURL()` 存文件（`Buffer.from(b64,'base64')`）再读图。
- 同一张图里题干+选项都有，**判分依据（选项文字）与题面同屏**，避免选项错位。

### 15.3 作答：选项字母「显示值 ≠ 内部值」（本轮最大坑）
- 选项行结构：`li > label > span.num_option_dx[data="X"]`（**显示**字母）`+ a`（选项文字）；
  同时 `li[aria-label="X …选择"]` 带**内部**字母。**两者可能不一致**（平台有意打乱：
  实测见过显示「B」而 `data="C"` 的行）。
- 结论（已交叉验证 174 节）：
  - 人/视觉读到的是**显示字母** → **按显示字母找 li 并点它**（`x.querySelector(".num_option_dx").textContent.trim() === 'B'`），
    平台会按该行自己的内部字母记录；
  - `input[name='answer{qid}']` 的值是**内部字母**（判断题是 `true`/`false`），
    所以「hidden 值和你点的字母不一样」是正常现象，**不要据此判断点错了**；
  - 结果页「我的答案」显示的是**显示字母**，与你的意图一致 → 用它复核。
- 校验：点完读 hidden 是否非空；**同一次调用里读到的值可能是暂态**（异步渲染），
  最终以结果页/下一次读取为准。判断题点 `A`（对）后 hidden 会变成 `"true"`。
- 多选题计分：`得分 = (选对 − 选错) / 正确总数 × 分值`（部分分；全错为 0）。
  实测本课多选常见 2 项，选错会抵消选对 → 只选有把握的。

### 15.4 提交（两步、别抢）
1. `a.btnSubmit`（「提交」）→ 等 ~2.5 s；
2. 顶层 `.popDiv` 里文本含「确认提交」且 `getBoundingClientRect().width > 0` 的那层
   → 点其中**文本以「提交」开头**的 `a.jb_btn`（勿点「取消」）。
- **不要在这两步之间调 `closeDeleteWindow()`**：它会把确认层一起关掉，提交静默失败
  （实测第一次就踩：页面仍停在作答态、答案还在，「已提交」是错觉）。
  任务点提示弹窗要在**点提交之前**关。
- 成功判据：出现「已完成 · 第N次作答 · 本次成绩X分」，且 `a.btnSubmit` 消失/不可见。

### 15.5 结果页口径（课程③型：无正解、无重做）
- 本课系结果页**只给「我的答案 + 每题得分」，不公布正确答案，也没有「重做」入口**
  （HTML 里无 redo 标记）→ 交完就定了，**不要试图修正**；低分也照常点亮任务点
  （实测最低 40 分也点亮）。
- 每题分值 = 满分 / 题量（5 题 → 每题 20）。

### 15.6 「一次机会」：附件打开次数限制
- 有节次的测验附件带**打开次数上限**，第二次进会弹「此附件仅支持打开 N 次，你已打开 N 次，
  不能再次打开」——也就是说**每节只有一次机会**。
- 处置：**先把题全部读完（15.2 出图）再开始点选项**，绝不提交空卷；一旦弹了这个框本节就废了
  （留到补分轮或报告用户）。

### 15.7 平台计分口径（验收用）
- 每做完 1 节测验，平台「已完成任务点」**+1**；四门课实测：42 视频 + 42 测验 = 84/84、
  56+56 = 112/112、43+43 = 86/86、33+33 = 66/66 —— 即**总数 = 视频数 × 2**，
  章节测验与视频各占一半。
- 章节树每行的「N个待完成任务点」在该节测验做完后**不会因此减少**（它只反映视频任务点），
  所以「树计数」不能用来验证测验，**验证一律看平台总数**。

### 15.8 抛题节奏与工具上限（工程细节）
- 单次 browser 工具调用约 **32 s 上限**：定位+打开+出图 ≈ 25 s 可以一次完成；
  「标记 + 点提交」与「点确认」要拆成 1~2 次**短调用**（等待用 500 ms 级）。
- 超时不等于失败：先复查状态（`a.btnSubmit` 是否还在、确认层是否可见、hidden 值），
  再决定补哪一步，**不要盲目重提交**。
- 节与节之间用左侧章节树 `document.querySelectorAll(".posCatalog_name")[idx].click()` 顺序推进最稳。

## 16. 补分扫描：白名单 `forceIdx`（树计数会骗人）【2026-09-24 实测】

- 背景：补分场景里某节的**测验先做完了、视频还没计分**，此时章节树该行显示「**1** 个待完成任务点」
  → 若按「计数 ≤1 即视为视频已完成、跳过不重播」的判据，这节的视频会被**永久跳过**。
- 处置：给 watcher 加**白名单**——`window.__CX_CFG__.forceIdx = [19,25,28,31]`，
  白名单内的节即使树计数 ≤1 也强制播放视频；播放完该节计数变 0 即完成。
  ```js
  if (!forced && pend !== null && pend <= 1) { /* 跳过 */ }
  if (!forced && pv && pv.passed >= pv.total) { /* mArg 已通过，跳过 */ }
  ```
- 判据分层（推荐顺序）：
  1. `forceIdx` 白名单（人工指定，最高优先）；
  2. `mArg.attachments[].isPassed`（平台权威，但对「视频在后续部件」的节是空附件列表）；
  3. 章节树「N个待完成任务点」（2=视频没看必须播；1=视频已完成）——**只在正常扫描时用**，
     补分场景会误判（见上）。

## 17. 弹题与视频计分的关系：能答就答，且题库必须真的命中【2026-09-24 观察】

- 观察（同一课程、同样整节播完）：
  - 弹题**出现即被答对**的节（6.1、7.1）→ 章节树计数 1→0，**视频计分成功**；
  - 弹题**挂着没答/答得太晚**的节（同批 8.1 首轮）→ 播完计数仍是 1，**该节不算**；
  - 补看重播、这次答上了 → 计数变 0。
  → 结论：**弹题没答上的节有较大概率白播**，补分/补看时必须保证「出现即答」。
- 自动化的两个前提：
  1. **题库命中**才自动答（`cx_quiz_answers`：题干 → 选项索引，判断题 0=对/1=错）；
     没命中的题 bridge 不猜，留给巡检人工判断后入库。
  2. **bridge 不能"让位"给旧模块**：旧 `cx-quiz.js` 用 `.tkItem_title` 取题面，
     对「题面直接写在 `.tkTopic`」的新版弹题取不到题 → 若 bridge 见旧模块在场就 `return`，
     结果是**两个模块都不答**（实测躺了 9 分钟直到人工答掉）。修法：**先查题库、命中就自己答**，
     只有题库没有时才让位：
     ```js
     const idx = bank()[title];
     if (idx === undefined) { if (legacyFinds()) { pending.skipped = "legacy"; return; } return; }
     pending.answered = await submit(quiz, idx);
     ```
- 巡检侧的兜底：信标 `q=1`（未处理弹题）/`qw=1`（答错滞留）→ 立刻读 `pending.q`/`.opts`
  判断并 `answer(i)`，随后把 `题干→i` 写回题库，这样下一轮重播就是 2 s 内自动答上。
