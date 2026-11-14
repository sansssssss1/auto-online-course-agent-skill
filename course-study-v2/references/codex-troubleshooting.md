# Codex 操作适配

已初始化后的续跑与紧凑巡检读 [Codex运行说明](../references/codex-runtime.md) 和本轮状态；本文件的历史案例按故障分支查阅，避免每次巡检重读全文。

旧版作业在 Codex 与 ZCode 都实战过；旧版网课只在 ZCode 实战，用户报告 Codex 可能存在问题。因此这里提供能力分支和验证步骤，不宣称 Codex 网课已全流程可用。

## 识别环境与资源根

- 依据 Codex 会话上下文与实际工具清单识别环境；环境变量或电脑上安装过 ZCode 不能替代识别。
- 本次实际加载 `course-study-v2/SKILL.md` 所在目录为 `skillRoot`。脚本和 references 都从此解析，不能把工作目录、旧版路径或 `ZCODE_PLUGIN_ROOT` 当根。
- Codex 可由用户级或项目级 skill 发现；安装后检查实际名称与实际加载路径，避免一份入口指向旧目录而误以为新版生效。
- 读取本次配置的 `local/` 私有数据，不自动探测凭据位置。旧版状态只读参考，新版保存到独立目录。

## 先选择当前受支持的浏览器能力

1. 看当前工具清单与浏览器技能文档，确认存在的能力：标签、DOM 快照、截图、定位点击、跨帧、脚本执行、文件导出。
2. 优先用当前提供的浏览器工具。若有 `mcp__cua_repl`，按其首次调用限制初始化：已有指定标签按 mention/URL 获取，否则按任务 URL 获取或创建受支持标签；首次调用只执行该一个入口。
3. 读入口返回的文档后，才调用其中列出的 API。会话压缩后按该工具要求恢复文档，不把其他 harness 的 API 名称套过来。
4. 如需 Windows 原生界面且当前环境允许，先读当前 `computer-use` 的完整说明及其要求的 guidance/confirmations，再使用文档规定的入口。

能力由当前会话决定。原生控制被禁用时继续用可用浏览器表面；没有受支持浏览器通道时，能做离线取题、解题和文档整理，但需报告实时页面操作尚未完成。

**不导入 ZCode 的 `browser-client.mjs`，不调用 `agent.browsers` bootstrap。** 不为填补某个缺失 API 而连接隐藏调试端口、复用其他工具内部 client 或伪造未提供的方法。

## 页面与跨帧操作分支

| 当前支持能力 | 做法 |
|---|---|
| DOM snapshot + locator | 从当前快照定位课程、列表、题号和按钮，动作后回读状态。 |
| 受支持的 frame/iframe 定位 | 按平台知识识别真实帧，在目标帧读取或点击；同源关系不预设。 |
| 只提供扁平 DOM | 用快照中的标签、文本和当前工具支持的定位方式；不猜不存在的 frameLocator。 |
| 只有截图及点击 | 查看可见内容、滚动取完整题面，按画面操作；跨页后重新截图并核对身份。 |
| 明确支持页面脚本 | 才可运行新版采集或观察脚本，使用文档支持的执行方式。 |
| 页面脚本未提供 | 使用 DOM/截图；离线读取用户已保存的 HTML、TTF 或题图，不声称采集了页面内字体。 |

- 查询到的选择器只是当前页面证据，学习通和 MOOC 旧选择器只是线索。跨源读取受限时换受支持通道，不经主文档拼接跨源访问。
- 列表巡检停在列表，不能为了补齐内容打开可能生成作答记录的详情。任务身份和截止时间不足时保留未知状态。
- 动作前确认当前课程与任务；动作后核对实际变化。工具调用完成不证明页面点击或保存成功。
- 本轮窄 IAB 面板中，页面最小内容宽度大于可视区，目录侧栏遮住部分播放器；DOM 的 visible
  不等于控件在当前可点击画面内。先检查截图，必要时通过平台原有目录收起开关移除遮挡。
  取整页证据可用当前支持的 fullPage 截图；不因只见到局部画面就判题面缺失。
- 本轮侧栏小节节点在只读 DOM 中唯一且可见，普通 locator.click 仍报目标不可用。已核对具体节点后，
  可在当前公开且允许写页面的 CDP Runtime.evaluate 中，对同一唯一 DOM 节点调用 click()；
  不调用猜测的平台函数，不重复提交。之后重新读取章节、部件与媒体身份，click 返回值仅作动作记录。
- “下一节”实测先从视频进入同章的已完成测验回顾，顶层 chapterId 未变；不能把它固定当作下一视频。
  按当前部件分流：视频、文档、已完成回顾、测验介绍或进行中测验。没有本次开始授权时不启动新尝试。
- REPL 重建或中断后先列实际标签并重新绑定；本轮原测试标签曾消失，正常课程入口仍保持登录。
  保存的标签 ID 仅是线索，标签不存在就从正常课程卡片恢复，不直接重放旧会话链接或提交动作。
  需要跨轮保留的测试页按当前 API 重新标记 handoff；标记是本轮有效，不能只标一次就假定永久保留。

## 取题、附件与本地工具

- 明文可由当前 DOM 通道读取，图片用截图/支持的资源导出。新题面需与课程、题号和首题对应，不能读取缓存旧图继续作答。
- 有受支持页面执行能力时，在已打开的真实题目帧调用 `scripts/collect_questions.js` 只读函数，返回当前题面与字体的采集包；不是 Node CLI。用 `scripts/browser_payload.py` 生成 page/element 函数，以显式 options 参数传入来源与选择器；不向页面写配置全局变量。无此能力时不尝试绕过工具限制获取 TTF。
- `scripts/question_reader.py` 是本地离线工具：已取得的当前字体与文本可逐字混排渲染，可选 RapidOCR 行级识别；缺少依赖时使用明文/题图并标复核项。
- CLI 参数看各 Python 工具 `--help`，数据格式见 `references/tool-data.md`，当前验证范围见 `references/validation.md`。运行采用当前可用运行时；不要把 ZCode runtime 当成本地脚本依赖。
- 有受支持页面执行能力时可用 `scripts/collect_task_list.js` 只读当前列表，提供 platform 与 scope；否则由当前 DOM/截图采集同一快照格式。`scripts/inspect_tasks.py summary` / `diff` 纯离线比较，不能代替真实列表采集。
- 本地命令可整理已经取得的文件、OCR、计算和生成交付物；登录页面的浏览器操作仍通过所选受支持浏览器通道完成。
- 附件走平台正常下载、受支持导出或已观察到的附件真实链接。403、登录 HTML 或空文件需识别为失败，不能只因扩展名正确便交付。
- 需要 PDF/Word 等交付时读当前相关 skill，优先查其运行时说明；完成后渲染或打开核对排版与题目完整性。

## 2026-10 Codex IAB 实测与限制

本轮在已完成的学习通课程验证了正常登录、目录读取、进入正确小节和读取媒体状态。
完整播放、计分、续跑和测验仍须各自验证，不能从这次导航成功推定。

- 当前 `playwright.evaluate` / locator.evaluate 是只读作用域，可读取 DOM 和媒体属性。
  不能用它注入静音信标、设置 muted、调用 play 或执行 DOM 点击；正常动作使用 locator 控件。
- 在门户页 `#frame_content-zj` 中可读 DOM，但帧内点击和键盘动作曾失败。实测可读取该 iframe
  当前真实 src，解析为绝对地址，在本次测试标签顶层打开该目录，再点已观察到的 `a.clicktitle`。
  学习页地址由平台点击生成；不猜测或拼接 studentstudy、计时作答或提交地址。这只是该目录样本的回退，
  其他页面必须重新确认身份、权限和导航后状态。
- 恢复轮次中普通标题点击仍可能无效；在上述真实目录顶层对唯一标题节点用公开 CDP `.click()`
  成功恢复了学习页。门户 iframe 的 contentDocument 若不可读，不能从顶层强行穿透；以当前可用
  frame 通道或该实际目录回退处理。
- 课程卡片打开新标签后，标签清单可能稍后才更新；先核对清单和实际页面，再决定是否重试。
  调用超时不证明动作没发生，不重复登录、点课或创建标签。
- 本轮部分读取约需 21 秒，选取标签含初始快照可超过 30 秒。按当前工具允许范围给调用足够预算，
  每次只安排一两个耗时操作，避免批量调用超时后丢失 REPL 绑定。
- 本轮起播前媒体 `muted=false`，静音按钮尚隐藏，播放器 `m` 键无效。普通只读 evaluate 不能设置
  静音；后续通过当前工具公开的 CDP 接口仅将本视频设为静音，再点击平台播放按钮成功。
- CDP 的一次实际调用约需 42 秒，早先 30 秒外层预算导致误判为不可用。读取当前能力文档，
  给外层工具调用足够预算（本轮 60 秒）；CDP 参数 timeoutMs 不包含全部通道准备耗时。
  超时后先检查媒体与页面实际状态，不把超时等同于未执行。

### Codex 当前视频静音分支

先核对当前课程与章节，再检查 `tab.capabilities` 是否提供 `cdp` 并读取其文档。
只有该公开接口允许 `Runtime.evaluate` 写页面状态时，才执行 [Codex静音脚本](../scripts/codex_mute_video.js)。
它是 Codex 专用的可写通道函数，不能传给只读的 playwright.evaluate；也不替代 ZCode 原有静音/信标路径。
默认 `action:"mute"` 仅静音。已获起播/暂停授权时可显式传 `action:"play"` 或 `action:"pause"`，
脚本在同一次调用中核对身份、静音，再点击该视频文档内的唯一平台播放/暂停按钮。
本轮普通跨帧“播放视频”点击之后实际从 1.2 跳到 1.3，因此这些播放器动作使用此专用分支，
不在静音后再额外发一次普通跨帧 click。

```js
const fs = await import("node:fs/promises");
const source = await fs.readFile(muteScriptPath, "utf8");
const cdp = await tab.capabilities.get("cdp"); // 先读当前 documentation()
const response = await cdp.send("Runtime.evaluate", {
  expression: "(" + source + ")(" + JSON.stringify({
    expected_chapter_id: verifiedChapterId, expected_object_id: verifiedObjectId,
    action: "mute" // 本次已授权起播/暂停时才改成 play/pause
  }) + ")",
  returnByValue: true
}, {timeoutMs: 10000});
const result = response.result?.value;
```

`muteScriptPath` 是本 skill 脚本的绝对路径；`verifiedChapterId` 来自已经核对的任务身份，
`verifiedObjectId` 来自本节实际视频附件的 data.objectid，换节时与上一媒体对照，不复用旧值。
此脚本只支持当前已验证的学习通 `/mycourse/studentstudy?chapterId=...` 布局；
核对顶层章节、内层 cards 文档 knowledgeid、唯一 `#iframe`、视频 iframe 的附件 objectid、唯一 video，
以及当前媒体源路径中的同一 objectid；任一错配先失败，不扩大 DOM 搜索。返回 media_key 供状态保存，
不输出带签名参数的源 URL。缺少身份信息时核对真实页面或用正常控件，不直接跳过检查。
只设置当前 video 的 muted/defaultMuted；显式 play/pause 只点击该视频的实际平台控件，
不直接调用 video.play/pause，不改系统音量、其他标签、volume、倍速或进度。
对跨源帧读取失败按失败处理，不绕过同源限制。检查 result.ok、after.muted、media_key；
发生控件点击时还需 identity_verified_after=true。外层再次回读身份与时间推进，异步动作不能仅凭返回成功验收。
当前已播放/已暂停时不重复点击。超时或失败先回读，不能盲目重放同一控件动作。

实战通过静音起播、两次时间推进、平台暂停和恢复播放。最后保持静音并暂停。
跨节实测新视频 muted/defaultMuted 恢复为 false，且保持暂停、autoplay=false。因此每次新小节、
导航或媒体重建后都重新核对并静音，再起播；当前脚本没有自动覆盖后续视频，也不承担后台保活。
本轮公开 CDP 不支持 Page.addScriptToEvaluateOnNewDocument，未安装跨导航静音注入。
不要仅因存在 CDP capability 就假定所有协议方法可用。遇新视频自动播放时先暂停并静音，再核对身份。
缺少 CDP 能力时尝试当前平台可用的静音控件；仍不能可靠静音时保留暂停并说明具体阻碍。
这次未验证低音量分支，不因只读通道受限就切换有声播放。

本地生成 payload 后，下面的调用形态已在真实目录验证。示例假设 `directoryTab` 已按当前文档绑定，
并已确认该 iframe 就是当前课程目录；文件读取和函数解析仅发生在 REPL 本地：

```js
const fs = await import("node:fs/promises");
const vm = await import("node:vm");
const collect = vm.runInNewContext(await fs.readFile(payloadPath, "utf8"));
const snapshot = await directoryTab.playwright
  .frameLocator("#frame_content-zj").locator("body")
  .evaluate(collect, {
    platform: "chaoxing",
    scope: {account_alias: "account-a", course_key: "course-a", view: "content"},
    loaded_scope_confirmed: true
  });
```

`payloadPath` 是本次新生成的 element payload 绝对路径。只解析本 skill 生成并已检查的本地文件。
页面脚本字符串与函数对象的执行契约不同，返回 undefined 时先核对调用形态，不能当成无任务。

### 已完成回顾页的取题结构

只在当前页面已明确显示完成/历史结果时读取，不为测试而新开作答。
本轮实际帧链为 `#iframe` → `iframe[src*="ananas/modules/work"]` → `#frame_content`，
页内 `.TiMu` 共 3 题；回顾页选项没有作答页的 onclick/input，默认采集曾漏掉全部选项。
在该已核对结构上，questions payload 显式传以下选项；这不是所有学习通页面的通用默认：

```js
{
  batch_id: freshBatchId,
  source: {platform: "chaoxing", course_key: verifiedCourseKey, view: "completed-review"},
  option_selector: "ul.Zy_ulTop > li",
  option_label_selector: "i.fl"
}
```

标签按实际显示原文保存，且从选项正文排除。保存前对照页面题量与每题可见选项数；
不能因为返回 questions 非空就认定读全。题干/选项仍按本批次字体、图像和复核规则处理。
可选 selector 不改变共享采集器的旧默认，也不替换 ZCode 的实战读题方法。

## Codex 网课分阶段验证

首次使用先做短任务验证：

1. 登录态可复用或按授权正常登录，列表能识别目标课程与任务。
2. 能打开本节正确视频部件，核对附件/媒体身份，排除上一节残留播放器。
3. 能在静音下通过平台控件起播，两次观察时间推进；不先假定后台和锁屏可用。
4. 能在媒体结束后刷新/重新读取平台完成标记。没有完成证据就记待核验。
5. 再验证断点恢复、跨节切换、弹题和已授权测验。测验提交独立验收，播放成功不代表提交可用。

未验证的分支继续标待验证。若工具不支持脚本观察，可通过平台可见状态与截图核对；不把缺少信标等同于无法正常播放，也不能宣称已具备旧版后台保活能力。

## 提交、等待与回退

- 网课测验和作业按各自流程的当前授权处理。共享知识不扩大权限；旧版个人授权不作为新版公共默认。
- 提交结果不明先检查平台记录、结果页与剩余次数；不要切换脚本/旧版重复提交来排障。
- 等待用当前提供的 wait/sleep 机制与其限制，保持必要进度更新；不得照搬 ZCode 旧版 shell 长睡眠参数。
- 低音量短试仅在支持可靠操作和收尾时采用，共享知识的 60 秒边界不变。当前工具无法可靠恢复静音时保留默认静音并换其他排障步骤。
- 需要回退旧版时，先停新版同账号执行者、保存当前任务身份和未决事务，再到旧版核对平台实际状态后继续。旧版文件与凭据保持原样。
