# ZCode 操作适配

旧版网课与作业都在 ZCode 实战过。2026-10-18 的新版 preview.4 运行记录已支持两个未完成节点的播放、弹题、章节测验和读题流程；其他范围仍按实际任务验证。先看当前会话工具说明，下面的历史 API 仅在当前版本支持时使用。

## 识别环境与定位资源

- ZCode 客户端上下文、当前可用 browser-use 运行时和工具文档优先于目录名。仅有 `ZCODE_PLUGIN_ROOT` 环境变量不足以证明当前会话属于 ZCode。
- 新版资源根是本次实际加载的 `course-study-v2/SKILL.md` 所在目录；将其保存为本次会话的 `skillRoot`，全部脚本和 references 相对这里解析。
- `ZCODE_PLUGIN_ROOT` 只用于定位 ZCode 浏览器插件自己的 runtime，不作为本 skill 根目录。
- 使用独立本地数据目录，指向当前 `local/` 配置；旧版状态只读参考。新版不会扫描或重写旧 skill 的凭据、断点及代码。
- 安装后检查 Settings → Skills 或 Skills 菜单里实际发现的新名称与路径。ZCode 多个发现根可能有同名遮蔽；以实际加载路径验收，不仅检查文件存在。
- 本机 ZCode 指南对发现顺序存在版本差异；需要诊断时读当前客户端附带的 `diagnosing-skills`，不通过改旧版名称解决新版安装问题。

## 浏览器初始化

先读当前浏览器插件的 `SKILL.md` 和 API 文档。旧版本曾通过 `mcp__node_repl__js` 使用下列 bootstrap；当前文档要求每次重新初始化时，每次工具调用都重新执行：

```js
const { join } = await import("node:path");
const { pathToFileURL } = await import("node:url");
const { setupBrowserRuntime } = await import(
  pathToFileURL(join(process.env.ZCODE_PLUGIN_ROOT,
    "scripts", "browser-client.mjs")).href
);
await setupBrowserRuntime({ globals: globalThis });
const browser = await agent.browsers.getForUrl("https://i.chaoxing.com/");
```

该示例不是 Codex 初始化方式。环境变量缺失、插件路径不符或 API 已变时回读当前文档，不在磁盘搜隐藏调试接口来拼接替代客户端。

## 标签与跨帧

- 先列已有标签，复用与当前课程匹配者。课程卡片可能开新标签，按当前 API 认领实际目标，再确认 URL 和课程标题。
- 旧 API 曾需 `await browser.tabs.get(id)` 后再 `.close()`；对象或方法以当前文档为准。
- 正在播放时避免无谓切标签；旧版 IAB 认领其他标签曾让视频退后台，时间不推进而可见性字段仍正常。
- 为恢复播放可激活目标标签；关闭额外标签时只处理本次任务创建且不再需要的标签，保留用户其他页面。
- 学习通跨帧先用当前支持的 frameLocator/locator；不支持或失败时用扁平 DOM snapshot 或截图。主文档 DOM 无法直接读取跨源 iframe 并不等于题目不存在。
- 历史 facade 中帧内 `evaluate("el => el.click()")` 曾返回空对象且没有执行，函数对象 `evaluate(el => el.click())` 才生效；仅在当前文档允许 evaluate 时采用。
- `getByRole` 曾无法跨帧定位。以当前 snapshot/帧身份缩小目标，避免对同一失败选择器重复试探。

## 读题与巡检工具

- 沿用 ZCode 已实战的 DOM、扁平 snapshot、题图与截图读题方法；新版采集器作为可选增强，已在本轮两个节点实战。preview.2 将两采集器从立即执行表达式改为 `collect(document, options)` 纯函数，原先直接执行整文件或设置页面选项全局变量的调用不能原样复用。
- 列表巡检只采集列表。作业行详情 URL 可保存为本地定位信息，但不为“看看有没有新作业”导航到 dowork 或开始计时页。
- 选择新版读题采集时，在已打开的真实题目帧调用 `scripts/collect_questions.js` 的只读函数，返回题面、字体及来源；不是 Node CLI。用 `browser_payload.py` 生成 page/element 函数，按当前 API 传函数对象与显式 options 参数；见 `references/tool-data.md`。
- 本地 `scripts/question_reader.py` 接收采集包，渲染当前字体并可用 OCR。参数看 `--help`，数据格式见 `references/tool-data.md`，当前验证范围见 `references/validation.md`，不把源码字符串直接当浏览器工具参数猜执行方式。
- 本轮记录中第二节点的题干与选项均有混淆字体，当前批次内嵌字体、渲染/OCR、人工复核与平台结果配对成功。这不授予跨题页复用字形映射，也不把 OCR 置信度当成答案正确性。
- 列表采集函数 `scripts/collect_task_list.js` 不会主动打开任务；以参数提供当前 platform 和 scope 后保存快照，用 `scripts/inspect_tasks.py summary` / `diff` 离线比较，跨账号/课程/view 的 scope 不混用。不得把函数字符串返回 undefined 当作空列表；先确认当前 evaluate 是否实际调用了函数。
- 当前插件支持导出截图/资源时正常保存；仅支持返回 data URL 时，通过已支持的本地写文件通道落盘。附件下载需核对内容签名，HTML 错误页不算 PDF。
- 新采集调用失败、结果不完整或工具链不可用时，保存错误、原题图和来源，回到上述 DOM/snapshot/截图方法继续；未验证的新采集调用不替换已实战路径。自动 OCR 也是可选增强，缺少它不影响明文或图片读题。

## 视频与信标

- 保留 ZCode 原有的播放器静音、起播与信标路径；页面操作能力以当前 ZCode 工具文档为准。某次 Codex 的只读 evaluate 限制不适用于 ZCode，也不构成禁用其受支持页面操作的理由。
- 按当前平台实际限制选择播放器操作；学习通知识见 `references/chaoxing.md`，MOOC 见 `references/icourse163.md`。
- 新版 `scripts/keepalive.beacon.js` 只在当前工具允许页面脚本且已定位正确任务时使用；读源码头部了解当前版本。它负责观察及静音约束，不代替平台完成核验，也不自动提交答案。
- 锁速课不用旧版会强制 2x 的 keepalive；恢复暂停时让弹题、登录挑战和用户主动暂停优先。
- 静音优先。低音量短试按共享知识收尾，外层 `finally` 负责新旧视频静音；信标/后台定时器仅为附加保障。
- 无法注入时通过平台控件、状态截图和间隔观察执行；不得把未注入说成已装好保活。

## 可交付与验证

- 作业 PDF、程序、截图使用当前可用的文档/科学计算工具生成，输出路径写入本地交接；发布副本排除原题、身份、会话和运行日志。
- 本轮新版两个节点的持久化记录包括静音 1x 播放结束、各一次弹题、章节测验结果，以及目录任务点 0/84→4/84。核对当前平台再扩大范围；后台、锁屏、整课自动切节和独立作业交付仍没有由这两节证明。
- 出错时保存新版当前身份、平台状态和未决动作；先停止新版执行者，再在旧版重新核对平台状态，不复制未知提交事务继续重放。
