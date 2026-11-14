# 豆包工作（Doubao Work）适配

明确选择 `course-study-v2` 后，在豆包工作桌面端（Windows）按本页执行。通用边界（单执行器、
不伪造心跳、平台完成标记为准、测验/作业授权分级、登录接管）统一遵循 SKILL.md「全程保留的边界」，
本页只写豆包特有事实：路径、版本、`aha_browser_use` 接口契约与本机实测结论。独立技能
`mooc-agent-skill`、`course-study-dsh` 不在本版读写范围。

## 资源根、任务目录与续跑

- 技能资源根（安装/加载目标）：`C:\Users\<USER>\.agents\skills\course-study-v2`；
  可编辑维护源（Git）：`C:\<SOURCE_DIR>\course-study-v2`，两者按同一组文件同步；
  `D:\<OLD_DIR>\course-study-v2` 是历史快照，禁止覆盖安装。
- `package-manifest.json` 是带 SHA-256 的整包静态白名单；任何文件改动后必须同步重生成，
  否则探针报 `manifest-hash-mismatch`。
- 运行材料放独立任务目录 `...\<会话>\doubao-adapt-run\`，不写进技能目录。
- **续跑先读任务目录的 `run-context.md`**：其中「已读文件清单」按 SHA-256 判定有效性，
  哈希未变不重读，变化才重读对应文件；环境事实与当前节点摘要直接复用。关键节点（完成小节、
  测验提交、目录总验收）更新该文件。业务断点仍以 `state.json` 为准，二者分工不重复。

## 硬性步骤 checklist（脚本固化，不执行不得继续）

长任务实测证明「建议性」流程会被顺手路径跳过，下列步骤改为默认硬步骤，由脚本固化：

1. **读选项图前必须先本地拼合（Q1/R3）**：用 `scripts/merge_images.py` 把同题/同小节选项图
   按题号分组、纵向白底拼成一张，模型只读拼合图；**禁止逐个 Read 原始选项图**，原图保留不删。
   缺图、尺寸不一按脚本非零退出处理，不跳过、不裁换选项。默认走高分辨率拼合（见下文 R3）。
2. **播放观察必须用 `observe_loop` 封装（Q2）**：直接整段粘贴下文函数，只填媒体定位与轮数，
   不自己组织多轮 sleep 逻辑；`paused/ended` 立即 break。
3. **每章收尾必须调用 `scripts/sync_context.py`（Q3）**：动作完成紧后一次更新 `state.json`
   与 `run-context.md`，节点摘要由 state 生成；杜绝「已完成但状态未更新」。
4. **字体解码必须调用固化 CLI（R1，硬性）**：字形图、解码、拼合清单一律用
   `scripts/glyph_map.py`、`scripts/decode_batch.py`、`scripts/build_merge_manifest.py`，
   节点字形 mapping 作为唯一人工输入 JSON；**禁止再临时 Write render_glyph/decode/build_manifest
   三类脚本**，只允许传参数调用固化 CLI。
5. **操作必须合并到同一单元格（R2，硬性）**：把「定位 + 动作 + 回读验证」放进一个
   `computer_use_tool` 单元格，连续可合并的点击/填写/回读不得拆成单动作单元格；目标每单元格
   `bu.` 动作数均值 ≥ 2.5。模板见下文「操作合并」。

## 运行时与 PowerShell 引导

- 命令只有 PowerShell（pwsh 7.6.4），Bash 禁用。默认 `python` 是 sandbox_runtime（3.13.16），
  处理 UTF-8 一律 `python -X utf8`；`C:\Python314`（3.14）非必要不重复装依赖。
- 已确认 Node v22.23.2、Typst 0.15.1、Git、LibreOffice 可用；tesseract 未安装，OCR 走 RapidOCR。
- 任务目录的 `env.ps1` 定义 `$run`/`$inst`/`$scripts`，命令以点源开头，避免重复路径前缀：

```powershell
. "<run>\env.ps1"; python -X utf8 "$scripts\doctor.py"
```

- 先跑 `doctor.py` 确认解释器、可选依赖与资源；工具不是授权来源。

## 浏览器接口契约（高效，默认限流）

主通道是豆包内置浏览器，所有页面操作放在一个 `computer_use_tool(plane="bu")` 单元格，
`import aha_browser_use as bu`，不另建 Playwright/CDP/Selenium。**默认禁止裸 `snapshot()`**：
交互快照必须带 `max_chars`，并尽量用 `within`/`view` 限定范围。简单查询优先结构化读取，
`bu.js` 只用于 `currentTime` 等动态状态和采集 payload 执行。

| 接口（已核实签名） | 用法要点 |
|---|---|
| `snapshot(*, view='outline', within='viewport', max_chars=3200)` | `view` 取 outline/interactive/all；`within` 取 viewport/full/`nN`/css；交互用 interactive 取 `nN` ref |
| `css(selector, *, frame_path=(), match='unique')` | match 取 unique/first/all；返回可复用定位器，不支持 iframe frame_path |
| `read_all(selector_or_refs, fields=None, limit=50, *, max_chars=12000)` | 批量读重复记录并保持字段配对；`fields` 可给映射读后代 |
| `wait_for_element(selector, timeout=10.0, visible=False)` | 等元素而非 sleep；导航后配合 `wait_for_load()` |
| `extract_content(types='all', max_chars=4000, *, within=None)` | 读正文无交互噪声；`types` 可限 heading/paragraph/list/link/table |
| `find(query, *, limit=10, search_type='all', max_chars=8000)` | 取 ref；`|` 表 OR、`&` 表 AND；语义标签不是稳定选择器 |

```python
bu.snapshot(view="interactive", within="viewport", max_chars=2000)
rows = bu.read_all(bu.css(".TiMu", match="all"), fields=["text"], limit=20)
bu.wait_for_element(".vjs-play-control", visible=True)
```

导航、刷新或换标签后旧 ref 失效，必须重新观察；坚持 ref 优先的观察—动作—回读。

### 跨帧、截图、下载、登录

- 同源帧可经 `iframe.contentDocument` 直接 JS 读取；跨源帧主文档访问被同源策略拦截，属预期。
  `bu.snapshot()` 把同源/跨源帧统一扁平化（帧内元素带 `nN` ref），对跨源帧内 ref 的 `bu.click`
  真实生效，故跨源帧读题/点选/核对可经快照 ref 闭环。`bu.iframe_target()` 本机返回 None，不可依赖。
- 截图 `bu.screenshot(path=..., with_cursor=False)`，元素证据用 `screenshot(ref=...)`；图片用文件 Read 查看。
- 下载 `bu.download(...)` 或点击后 `wait_for_download()`，文件落 `C:\Users\<USER>\Downloads`，只报已完成下载。
- 登录/验证码/扫码/OTP 拦截（`blocked=auth`）下一步必须 `interaction.request_action(type="browserControl")`
  保留现场交用户，不输入密码、不绕过；返回后重新快照，旧 ref 不再使用。

### 字体解码流水线（R1，硬性，固化 CLI）

混淆字体节点的完整流水线只调用三个固化 CLI，不再临时写脚本；`<tag>` 如 `13-2`：

```text
# 1. 渲染字形对照图（fontTools + PIL，离线）
python -X utf8 scripts/glyph_map.py --font <run>\cxsecret-<tag>.bin --out <run>\cxsecret-<tag>-glyph-map.png
# 2. 人工读字形图，写 <tag>-mapping.json（{"0x630b":"是", ...}，唯一人工环节）
# 3. 用 mapping 解码批次
python -X utf8 scripts/decode_batch.py --batch <run>\<tag>-questions-batch.json --mapping <run>\<tag>-mapping.json --out <run>\<tag>-decoded.json
# 4. 归集图片并生成按题分组的高分辨率拼合清单
python -X utf8 scripts/build_merge_manifest.py --batch <run>\<tag>-questions-batch.json --tag <tag> --out <run>\<tag>-merge-manifest.json
```

- mapping 键支持 `"0x.."` 十六进制或十进制字符串；未映射码点原样保留，不猜测。
- 各脚本写入走同目录临时文件原子替换，输入/字体/JSON 错误非零退出，不联网、不改源文件。
- 不同小节字体不同，mapping 与字形图不可跨批次复用。

### 选项图拼合（Q1/R3，硬性，高分辨率、只读拼合图）

选项图下载到任务目录后，先拼合再读图，不逐个 Read。**默认直接喂 `build_merge_manifest`
产出的清单**：清单内置 `min_width`（默认 600），`merge_images` 自动按题分块并等比放大，
无需放大即可读公式；原图保留、选项顺序不变：

```text
python -X utf8 scripts/merge_images.py --input <run>\<tag>-merge-manifest.json --out <run>\<tag>-merged --json
```

裸目录输入（整目录一张）或自写 JSON 清单（按题号显式分组）仍可用；需要更高分辨率时用
`--scale`（≥1，LANCZOS）或 `--min-width`（CLI 优先于清单值）：

```text
python -X utf8 scripts/merge_images.py --input <run>\<section>-option-images --out <run>\<section>-merged --json
python -X utf8 scripts/merge_images.py --input <run>\groups.json --out <run>\<section>-merged --scale 2 --json
```

需要按题号分组时，目录用 `--group-pattern`（正则第一个捕获组为组 id），JSON 用
`{"groups":[{"id":"q1","images":[...]}]}`；间距/边距用 `--spacing`/`--margin`，宽度不一用
`--align` 或 `--uniform-width`。脚本非零退出即缺图/坏图，先修复再继续，不跳过、不互换选项。
**补读原图仅限复核场景**（拼合图仍无法确认、P 模式小图、需核对单像素笔画），且必须先读
拼合图确认不足，再按标签定位单张原图，不允许跳过拼合直接逐个 Read。

## 操作合并（R2，硬性，定位+动作+回读同单元格）

历史轨迹每个单元格只做 1 个 `bu.` 动作（中位数 1.0），往返过多。硬性要求：一个
`computer_use_tool(plane="bu")` 单元格内完成「取定位/快照 → 一个或多个连续动作 → 回读验证」，
连续可合并的点击/填写/回读不得拆成单动作单元格；**目标每单元格 `bu.` 动作数均值 ≥ 2.5**。
墙钟限制不变（单格 ≤110s，observe_loop 仍按 3 轮降级）。下面模板可整段粘贴，只改选择器/索引：

```python
# ===== 操作合并模板：定位 + 动作 + 回读，同单元格 =====
import aha_browser_use as bu, json

# 1) 定位（一次结构化读取，拿到当前 ref/状态，不裸 snapshot）
options = bu.read_all(bu.css(".ans-videoquiz-opt", match="all"),
                      fields=["text"], limit=10)
# 2) 动作：JS 点内部 input（弹题可靠做法），再点可见提交
picked = bu.js(r'''(() => {
  const input = document.querySelectorAll('.ans-videoquiz-opt input')[0];
  input.click();
  const submit = document.querySelector('.ans-videoquiz-submit');
  return {checked: input.checked, hasSubmit: !!submit};
})()''')
# 3) 回读验证：确认选中后再提交，并回读面板是否消失
if picked["checked"]:
    bu.js(r'''document.querySelector('.ans-videoquiz-submit').click()''')
state = bu.js(r'''(() => ({quiz: !!document.querySelector('.ans-videoquiz'),
                           paused: document.querySelector('video')?.paused}))()''')
print(json.dumps({"options": len(options), "picked": picked, "state": state},
                 ensure_ascii=False, indent=2))
# 本单元格 bu. 动作数 = 4（read_all + 2 个 js + 1 个 js）
```

- 章节测验同理：同一单元格内 `read_all` 取 `.TiMu` 行 → 按索引 `click` 各 `li` → 回读
  `aria-checked` 唯一 true，不拆成每题一格。
- 合并的前提是动作间无歧义、回读能确认上一步成功；若回读失败或出现弹窗/阻塞，立即停下，
  下一个单元格只做排查与恢复（降级写法），不带着未确认状态继续动作。
- 导航/刷新后旧 ref 失效，必须在同一单元格重新定位，不跨单元格复用旧 ref。

## 播放观察与 observe_loop 封装（Q2，硬性）

播放健康看 `currentTime` 连续变化与平台状态；观察超时先只读状态，确认仍在播放就继续等，不把仍在
播放的视频重新起播。学习通锁速接受 1x，不伪造心跳或写倍速。**播放观察必须用下面的 `observe_loop`，
整段粘贴，只改 `rounds`/`interval`，不再自己组织多轮 sleep 逻辑**；单元格 `timeout_ms=300000`。

```python
# ===== observe_loop：整段粘贴；媒体定位默认全帧找 video，一般无需改 =====
import aha_browser_use as bu, time, json

VIDEO_STATE_JS = r'''(() => {
  let d0=null;
  const walk=(d)=>{if(d.querySelector&&d.querySelector('video'))d0=d;
    Array.from(d.querySelectorAll('iframe')).forEach(f=>{try{walk(f.contentDocument)}catch{}})};
  walk(document);
  if(!d0)return {no_video:true};
  const v=d0.querySelector('video');
  return {paused:v.paused, ended:v.ended, t:+v.currentTime.toFixed(2),
          dur:+v.duration.toFixed(2), visibility:document.visibilityState,
          quiz:!!d0.querySelector('.ans-videoquiz')};
})()'''

def observe_loop(rounds=5, interval=55, state_js=VIDEO_STATE_JS):
  samples=[]; reason='max_rounds'
  for i in range(rounds):
    try:
      s=bu.js(state_js)
    except Exception as exc:
      reason='error'; samples.append({'round':i,'error':str(exc)[:120]}); break
    s['round']=i; samples.append(s)
    if s.get('ended'): reason='ended'; break          # 结束立即 break
    if s.get('paused') or s.get('quiz') or s.get('no_video'): reason='paused'; break
    if i < rounds-1: time.sleep(interval)
  return {'reason':reason, 'samples':samples,
          'hidden_seen':any(x.get('visibility')=='hidden' for x in samples)}

# 调用：最多 4-5 轮、每轮间隔约 55-60 秒；reason 为 ended/paused/error/max_rounds
print(json.dumps(observe_loop(rounds=5, interval=55), ensure_ascii=False, indent=2))
```

- `reason` 含义：`ended`=播完；`paused`=被暂停/弹题/无视频，需先处理再续；`error`=读取异常，
  按错误信息排查；`max_rounds`=轮次用完仍在播放，再粘贴一次继续，不重新起播。
- **可见性实测（必须遵守）**：`hidden_seen=true` 只作记录，不立即停止——5.2/5.3 实测 hidden 下
  视频仍持续播放；但 hidden 也可能在数十秒后被平台自动暂停（历史 571→595 仅约 23 秒即 paused）。
  因此一律以 `paused` 为准，一旦 `reason=paused` 立即停止并恢复可见后续播，不假设长循环不被打断。
- **降级写法（墙钟受限时，本轮实测）**：单元格墙钟截断点在 110–120 秒之间（与 `timeout_ms`
  无关）——3 轮×55s=110s 可完整返回，4 轮×40s=120s 触发 `COMMAND_TIMEOUT`；75/80/90/100s
  各档均完整返回。因此单单元格内 `observe_loop` 最多约 3 轮（interval≈55s），需要更多轮就再
  粘贴一次；视频在截断后仍继续播放，重新粘贴观察即可，不重启、不跳进度。证据见实施报告。

## 采集函数与现成片段

- 生成载荷：`python -X utf8 scripts/browser_payload.py questions --scope page --out <run>/p.js`。
  要一步到位，用 `--emit-bu-call` 直接打印可粘贴的完整 `bu.js(...)` 片段（含内联选项占位，不连接浏览器）：

```text
python -X utf8 scripts/browser_payload.py questions --scope page --emit-bu-call
```

- 因 `bu.js(expression, target_id=None)` 无参数位，选项 JSON 必须内联进表达式。题面默认读 `.TiMu`，
  找不到题目即失败，不回退抓整页登录表单；题号/选项标签/图片归属/字体批次按 `references/tool-data.md` 保持。
- 混淆字体 `font-cxsecret` 一律走 R1 固化流水线（见上文「字体解码流水线」），不临时写
  render_glyph/decode/build_manifest；不同小节字体不同，mapping 不可跨批次复用，乱码文本不能直接理解。

### 现成状态片段（直接用，勿临时造 IIFE）

```javascript
// 1. 视频时间与状态
(() => { let v=null; const w=d=>{if(d.querySelector&&d.querySelector('video'))v=d.querySelector('video');Array.from(d.querySelectorAll('iframe')).forEach(f=>{try{w(f.contentDocument)}catch{}})}; w(document); return v?{paused:v.paused,t:+v.currentTime.toFixed(2),dur:+v.duration.toFixed(2),ended:v.ended}:'no video'; })()
// 2. 页面可见性/焦点
(() => ({visibility:document.visibilityState, hasFocus:document.hasFocus()}))()
// 3. 是否存在弹题
(() => { let d0=null; const w=d=>{if(d.querySelector&&d.querySelector('video'))d0=d;Array.from(d.querySelectorAll('iframe')).forEach(f=>{try{w(f.contentDocument)}catch{}})}; w(document); const tr=d0.querySelector('tr'); return tr?tr.innerText:null; })()
// 4. 各题选项选中态（check_answer 类即选中）
(() => { let d0=null; const w=d=>{if(d.querySelectorAll('.TiMu').length)d0=d;Array.from(d.querySelectorAll('iframe')).forEach(f=>{try{w(f.contentDocument)}catch{}})}; w(document); return Array.from(d0.querySelectorAll('.TiMu')).map(t=>Array.from(t.querySelectorAll('ul li span[class*=num_option]')).map(s=>/check_answer/.test(s.className))); })()
// 5. 静音起播（真实控件）
(() => { let d0=null; const w=d=>{if(d.querySelector&&d.querySelector('video'))d0=d;Array.from(d.querySelectorAll('iframe')).forEach(f=>{try{w(f.contentDocument)}catch{}})}; w(document); d0.querySelector('.vjs-mute-control').click(); (d0.querySelector('.vjs-big-play-button')||d0.querySelector('.vjs-play-control')).click(); return 1; })()
// 6. 视频身份（确认媒体未换）
(() => { let v=null; const w=d=>{if(d.querySelector&&d.querySelector('video'))v=d.querySelector('video');Array.from(d.querySelectorAll('iframe')).forEach(f=>{try{w(f.contentDocument)}catch{}})}; w(document); return {src:v.currentSrc||v.src, ready:v.readyState}; })()
```

## 每章收尾同步（Q3，硬性，动作完成紧后执行）

完成一个小节的视频/测验并平台验收后，**立即调用一次 `sync_context.py`**，再做下一个节点；
不允许「已完成但状态未更新」。需要同时改状态时用 `--set`（点号键，值按 JSON 解析），刷新
时间戳用 `--touch`；节点摘要由 state 自动生成，模型只手动维护 run-context 的「已读文件清单」：

```text
python -X utf8 scripts/sync_context.py --state <run>\state.json --run-context <run>\run-context.md
python -X utf8 scripts/sync_context.py --state <run>\state.json --run-context <run>\run-context.md --set current.status=completed --touch
```

- 写入走同目录临时文件原子替换，无变化重复调用逐字节一致（幂等），可安全重跑；不联网。

## 作业 PDF 与交付

排版优先 Typst（重公式、中文已实测），保留「答案速查表＋规范作答＋详解」结构与可识别中文文件名，
不做空白封面。PDF 生成后用 pymupdf 核对页数/文字层（无 U+FFFD），渲染每页 PNG 用 Read 查看，
再用真实 manifest 跑 `scripts/delivery_gate.py` 并保留原始 `GATE: PASS`。作业默认仅参考解答、
用户自行提交，网课测验授权不扩展到作业。完整要求见 `references/homework-output.md`。

## 禁令与能力边界

- **禁止 `cat`/打印完整 `package-manifest.json`**（曾造成单次约 6 万 token 输出）；清单核对只输出
  `dsh_probe.py` 的 verdict 结论。`dsh_probe` 的发现顺序与浏览器判定属 DSH 逻辑，不能单独证明豆包适配。
- 已验证（本地工具与夹具）：内置浏览器导航、快照与跨帧 ref 点击、截图/下载、`bu.js` 采集链、
  question_reader render/ocr 与 `--composite`、各工具与交付闸门、Typst 中文数学 PDF。
- 已有真实学习通运行记录（2026-11-06 至 11-07）：用户接管登录后恢复、跨多个章节静音1x播放、
  弹题处理、混淆字体与图片选项读题、已授权章节测验提交及成绩回读、目录完成标记复核，
  以及旧会话停滞后的新会话接管续跑。固化字体 CLI 和高分辨率拼合已用于真实题面。
  证据截点、进度与适用范围统一见[豆包实战验证](../references/validation.md#豆包工作实战记录2026-11-06-至-11-07)。
- 尚未覆盖：豆包通道下的中国大学MOOC与Polymas完整实战、后台/操作系统最小化/锁屏/进程退出后的
  完整闭环、每日上限触发处理，以及独立真实作业的取题至PDF交付；真实作业提交也未验证，且默认由用户自行提交。
  `hidden` 下曾持续播放也曾暂停，只能按实际媒体状态续接；已有章节成绩含错误答案，不保证满分。
  新课程仍先按授权做单节点核验；文件同步、离线检查与真实平台验收分别报告。
