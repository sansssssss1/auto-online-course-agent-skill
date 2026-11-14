# Codex 运行与开销记录

先读本轮状态、执行归属和当前工具文档；对应故障发生时才读 [历史说明](codex-troubleshooting.md)。一个账号只有一个执行器，恢复先回读平台未决事务。

## 当前视频事务

复用实际标签及公开 CDP capability。先从真实页面核对章节、cards knowledgeid、附件 objectid 和完整媒体 pathname（不留签名查询串）；换视频重新核对并静音。

本地 REPL 可导入 [会话模块](../scripts/codex_session.mjs)。它只接收已经取得的公开 CDP 对象，缓存本 skill 的脚本，保存完整记录并返回短摘要；不选择答案、发现浏览器或连接端口。

```js
const { createCodexSession } = await import(sessionModuleFileUrl);
const session = await createCodexSession({ cdp, skillRoot, runDir });
// identity: expected_chapter_id / expected_object_id / expected_source_path
const result = await session.run('start', identity, { budget_ms: 2000 });
```

`sessionModuleFileUrl` 是实际 skill 根中该模块的本地 file URL。`start` 完整核验后用原有静音脚本点唯一平台播放控件，再观察时间推进。`watch` 只观察：弹题、结束、异常暂停、静音/倍速错误、身份变化或停滞便返回。
事件合并检查，另有每秒后备读取；返回时清理全部监听和计时器，不注册常驻执行器。
会话按模式组装必需助手：watch 只带观察器，start 加静音助手，answer 加答题助手；不在页面缓存全局执行器。
上一观察只携带 scope、题目摘要键与状态，不反复发送题干正文。重叠调用返回 `transaction-in-flight` 且不发出第二个浏览器请求；先等待在途事务，不重放作答。

默认观察上限 10 秒、传输预留 50 秒，适配本轮 60 秒外层预算；一次只放一个可能耗时的事务。可配置上限最多 20 秒，必须先实测；本轮 30 秒窗口曾超时，不能照搬 DSH 的长等待参数。
模块根据最近三次返回估计传输耗时，向上增加预留。新页面或新通道重新使用保守预留。页面后台计时器可能延迟，预算不是外层墙钟保证。
超时或缺返回只回查，不重放动作。短观察不要求马上再观察；按剩余时间安排检查，其间做本地工作或用当前可中断等待，避免机械轮询。

## 已解答的单选/判断弹题

模型先核对完整题干、题型与显示选项顺序并求解，再传给 `answer`：

```js
const result = await session.run('answer', identity, {
  budget_ms: 4000,
  expected_type: verifiedType, expected_question: verifiedQuestion,
  expected_options: displayedOptions,
  expected_selected_indices: [chosenIndex], select_index: chosenIndex,
  expected_right_num: observedRightNum
});
```

事务使用原有弹题闸门：选择并检查 checked → 只提交一次 → 有界只读等待判定 → 仅确认正确后继续 → 观察弹题消失与推进。
提交前挂接本题结果层的只读监听，同时保留轮询，记录短暂的可见判定。存在继续控件才点击；正确结果自动收起时只观察，不补点播放或重复提交。
每步仍核对章节、附件、完整源路径、精确题干、选项和选中集合。同 DOM 提交/继续有防重标记；重载后先查平台结果。

原有计数器结构要求 `right_num` 增一；无计数器时必须存在已核对的 `#spanHas/#spanNot/#spanNotBack` 三标签契约，并读实际可见判定。后者显式传 `expected_right_num:null`，继续动作另匹配 `expected_verdict`。
隐藏的正确文字、结果层出现、弹题消失或视频恢复都不能单独证明答对。结果不明或错误时返回现场，不重复提交、不自动重考。精简失败摘要只带状态、守卫错误和最后几个判定事件，完整回执仍留本机。
错误判定和重答控件可以同时出现，状态记 `retry`，事务立即返回错误而非等满预算。普通作答入口不接受该状态；需要重答时先核对本次授权和平台机会，作为新的明确事务记录。数字/年代题可能采用本课口径，作答前按需核对当前字幕或讲义；没有材料时标明推断及置信度。
已获明确重答授权时，`submitting` 中残留的上一答错误标签属于待核对状态，等待本次新判定；不能把旧标签立即认作新结果。真实可见正确反馈优先于仍显示的提交按钮，避免漏过自动收起的结果。

## 取证、成本与验收

- `transactions.jsonl` 保存调用数、预算、墙钟/页面耗时、请求/返回字节和完整回读。`response_bytes` 为页面返回值 JSON，`summary_json_bytes` 为精简摘要 JSON，均不包含工具渲染外壳。稳定时只回传原因、起止时间与检查次数；变化时才带题面。字体、DOM、截图留本机。
- 同口径比较相同页面/流程及质量条件，另记模型介入次数、有效播放时间、恢复成本、正确率和保存结果。发现故障和失败尝试也计入。
- 实际 token 不可得时写 `actual_tokens:null`。字节、调用数和共享额度不能冒充本任务精确 token。AX/DOM 单次对照是样本，不推算整课或额度节省百分比。
- 字幕 `--brief`、材料复用和单次 OCR 补读见 [证据与效率](evidence-efficiency.md)。传输请求缩小只代表浏览器参数减少；是否减少模型 token 需用 `codex_usage.py` 的真实计数另测。
- 视频看对应完成标记；测验看保存反馈、作答次数及成绩，再刷新目录核验服务器保存。无成绩就只报告提交状态。
- 后台、原生最小化与视口条件独立记录。页面限制离开/最小化时按正常可见状态完成，停摆则记录降级。原生能力不足时由用户操作实际最小化，不伪造 focus/visibility 或学习上报。

## 混淆字体

仅在题面无法可靠读取时取本页字体并离线 render/ocr；题量、选项、输入哈希与批次对应。缺字时可在新输出批次显式用 `--fallback-missing-glyphs`，只回退子集字体缺失且普通字库存在的字形，保留警告并复核渲染。混淆字形仍用当前字体，未知字不补造。
