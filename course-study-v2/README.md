# course-study-v2

本地课程助手技能包，版本 **2.0.0-preview.10**。需要用户明确选择新版；通过当前宿主提供的浏览器工具和本机脚本工作。

## 功能

- 学习通、中国大学 MOOC 的任务巡检、断点恢复、正常播放、弹题和已授权章节测验。
- DOM 与截图读题；采集当前题页混淆字体，离线渲染和 OCR，保留题干、选项和图片对应关系。
- 作业取题、参考解答、独立验算、PDF/程序材料准备和存档；作业默认由用户自行提交。
- Codex 的媒体身份检查、静音与平台控件操作、有界观察、紧凑回读及本机诊断记录。
- 依赖检查、列表变化对比、交付检查、独立安装、公开导出与隐私检查。
- 可选的 Codex 本地用量分析：显式选择一个会话文件，只导出 token 计数，不导出聊天正文。
- DSH 外部 Chrome/MCP 适配、整包安装自检、单次 OCR 补读与逐选项证据预检；取材复用与成本边界见 [证据与效率](references/evidence-efficiency.md)。
- 豆包工作桌面端适配：以豆包内置浏览器为主通道，覆盖跨帧 ref 作答、截图下载、采集函数内联调用与 Typst PDF 交付检查。
- WorkBuddy 适配：技能发现根与实际加载路径核实、工具面与运行时探测、离线工具复用、能力缺口登记；该通道尚无平台实战记录。

这是监督式预览版本。解答由模型结合材料完成，不能保证答案或平台行为始终正确。功能与实测边界见 [验证说明](references/validation.md)。

## 使用

把本目录安装成 `course-study-v2` 后，明确调用 `$course-study-v2` 或说明使用“新版课程助手”。入口为 [SKILL.md](SKILL.md)。

```text
python -X utf8 scripts/doctor.py
python -X utf8 scripts/package_skill.py install --target "<SKILLS_ROOT>/course-study-v2"
```

安装目标必须是新目录或空目录。Codex 使用当前提供的公开浏览器能力；ZCode 使用自身适配。DSH 使用当前配置的外部浏览器 MCP，本版的 DSH 流程与独立 `course-study-dsh` 分别维护，账号配置、安装和运行状态不互相覆盖。豆包工作使用内置浏览器（`aha_browser_use`），适配说明见 [豆包适配](adapters/doubao.md)。WorkBuddy 使用当前受支持的浏览器控制通道；技能发现根、工具面与未覆盖条件见 [WorkBuddy适配](adapters/workbuddy.md)，未启用浏览器通道时只做离线工作，不宣称实战通过。

## 运行边界

- 同一账号只由一个执行器操作。按平台与用户要求正常播放，保持静音优先；不伪造进度、心跳或学习上报。
- 课程测验按当前授权执行。题面不完整、课程口径不明或结果未知时先补证据，不能用猜测或重复提交代替核验。
- 提交成功和课件完成以平台保存结果为准。完整后台、操作系统最小化、锁屏和退出进程是不同条件，分别验证。
- 凭据、姓名、学校、班级、学号、课程实例、截图、字体和运行记录留在用户选择的私有目录。

## 开发与发布

`adapters/` 为宿主适配，`references/` 为按需流程和知识，`scripts/` 为工具，`tests/` 为离线验证。
`local/`、`runs/`、`profiles/`、`_validation/`、`dist/` 和 Git 开发历史不进入技能公开包。

```text
python scripts/package_skill.py export --out "<NEW_PUBLIC_DIR>" --denylist "<PRIVATE_DENYLIST_JSON>"
```

敏感词文件可为字符串数组，或 `{"values":["<sensitive-value>"]}`。匹配值不会出现在扫描输出中。
导出会检查已知敏感词、个人路径、常见凭据、邮箱、手机号和会话链接；仍需人工检查未识别的个人信息及 Git 提交元数据。

## 许可

[MIT](LICENSE)。沿用已有项目的许可与公开来源署名；私人课程数据不属于发布内容。
