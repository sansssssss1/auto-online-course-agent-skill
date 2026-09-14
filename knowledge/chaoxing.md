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
2. 测验选项先试 `aria-label` 通道，绕开字体解密；不行再截图读题
3. `pyFlag="1"` 只保存是测验提交的安全阀
4. 上游 RateLimiter 的节奏参数可直接移植为 Runner 的 wait 策略
5. 403 + 验证码是核心拦截点，设计成"暂停 + 监督者处理"而不是自动对抗
6. 弹题处理上游为零 —— keepalive 检测 + 监督者读题是本项目差异点之一
