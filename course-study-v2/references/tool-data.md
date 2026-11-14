# 工具输入与输出

工具负责采集/整理，不选择答案、不导航到题页、不启动测验、不提交。JSON中真实资料只保留本机。

## 题面批次

两个采集器都是纯函数表达式 `(document, options) => result`，不自动调用、不写页面全局变量。
先在本地生成与当前 API 匹配的函数，再通过受支持的只读 evaluate 通道调用：

```text
python scripts/browser_payload.py questions --scope element --out runs/task-a/questions-payload.js
python scripts/browser_payload.py tasks --scope page --out runs/task-a/tasks-payload.js
```

输出必须是新文件。`page` 函数签名为 `(options)`，供页面 evaluate 使用；`element` 为
`(body, options)`，供目标帧唯一的 `body` locator.evaluate 使用。生成器只写本地文件，不连接浏览器。
将代码按当前 harness 文档转换为函数对象后传给 evaluate，选项作为第二参数；不要把箭头函数
字符串当作已调用的表达式，也不要在页面里安装选项全局变量。Codex 的实测调用见 `adapters/codex.md`。

在已授权且已打开的题目帧调用 questions 函数，以参数设置 `batch_id`、`source` 和选择器。
默认读取 `.TiMu`，找不到题目就失败，不能回退抓取整页登录表单。
若此harness不支持页面脚本，按同一格式整理当前DOM/截图材料，不绕开其工具限制。

```json
{
  "schema_version": 1,
  "batch_id": "sample-batch",
  "source": {"platform": "chaoxing", "course_key": "course-a", "section": "section-a"},
  "fonts": [{"id": "obf", "path": "current-font.ttf", "sha256": "<字体SHA256>"}],
  "questions": [{
    "id": "q1",
    "stem": [{"text": "示例题干", "font": "normal"}],
    "options": [{"label": "A", "runs": [{"text": "示例选项", "font": "normal"}]}]
  }]
}
```

字体可用 `data_base64` 替代path；当前题面内嵌字体由采集器读取，不从不明网络地址自动下载。
文件路径相对输入JSON目录解析。`question_reader.py` 按批次与输入哈希隔离输出，`needs_review`
表示仍需检查题号、否定词、公式和图形。OCR文字与置信度不是作答授权或正确答案。
图片可用本地 `path`，或 `{src,requires_visual_review:true}` 页面引用；后者只记录、不下载。
每张图保留 `role:stem|option`，选项图带当前题的 `option_label`，不能凭图片排列顺序重新推定字母。
`option_selector` 可指定当前页面已核对的选项行；可选 `option_label_selector` 指定每行真实标签节点，
未提供时仍用原 `.num_option_dx, .num_option`。标签节点从正文 runs 排除，找不到标签时保留
`label_inferred=true`。先对照可见题量/选项数；返回了题干不代表已经读全选择题。
当前通道无法读取计算样式、字体匹配失败或混淆字体未取得时，保留 `warnings`、`font_unresolved`
与 `needs_review`；不能把缺少 CSS 证据的文本宣称为已解码题面。

## 任务列表快照

在已加载的列表页调用 tasks 函数，以参数指定 `platform`、`scope`（账号别名/课程键/视图）
和必要选择器；没有账号别名和课程键时先补齐任务上下文。
采集器不会打开work/dowork页面或点击“开始测验”。

```json
{
  "schema_version": 1,
  "platform": "chaoxing",
  "scope": {"account_alias": "account-a", "course_key": "course-a", "view": "homework"},
  "captured_at": "2026-01-01T00:00:00+08:00",
  "authoritative": true,
  "items": [{"id": "work-a", "title": "示例作业", "kind": "homework", "status": "pending", "deadline": "页面原文"}]
}
```

空列表默认 `authoritative=false`；只有当前页面明确证明无任务时才由监督者确认。
所有列表的authoritative只代表“本次已加载范围”，分页/折叠/未发布内容要分别说明。
deadline原样保留，不把相对时间猜成绝对截止。
目录小节数与平台任务点数是不同口径；不能用条目数推算任务点完成率。缺少稳定 ID 的条目
带 `id_inferred`，重名时离线工具会拒绝比较；先核对真实 DOM 标识或缩小到正确列表，不能静默去重。

```text
python scripts/inspect_tasks.py summary --input snapshot.json
python scripts/inspect_tasks.py diff --before previous.json --after current.json --out changes.json
```

对比要求platform与整个scope相同；只输出新增、移除、变化及未知项，不自动执行任何后续任务。
