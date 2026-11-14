# 证据复用与节点开销

字幕、OCR 题面、多视频或低置信答案出现时读本页。策略来自独立 DSH 的实战经验；
通道和调用时限仍分别走各宿主适配。这里不授予播放、作答、提交、重考或外部转写权限。

## 先盘点，再执行

- 从新鲜目录分开记录视频、测验任务点。平台已确认的视频只记既有完成；纯测验节点不重新播放来凑本轮 ended 证据。
- 盘点当前节所有视频附件，而非只取第一个播放器；逐个记录附件与完整源路径，再由平台汇总标记验收。本版 Codex 守卫仍拒绝多义帧结构，遇到多个帧应走当前支持的逐帧控件流程，不放宽唯一性检查。
- 稳定布局复用已核实的骨架与局部 locator；导航后重新核对身份，布局或题型变化再补快照。不要把旧 frame、输入 token 或旧试卷批次当新节点。

## 一次取材，按需取片段

同一账号别名、课程键、章节、附件和输入哈希构成材料索引。新媒体重判字幕有无；
只有身份和输入均匹配时复用本地 SRT、题面渲染或 OCR，不跨页复用随机字体，不重放过期签名链接。
原始正文、字体、截图、完整工具回执留在私有 run；模型只接必要题面、引文和短状态。

已有字幕工具的低输出入口：

```text
python scripts/subtitle_evidence.py find --corpus <LOCAL_SRT> --query <TERM> --brief
python scripts/subtitle_evidence.py gate --corpus <LOCAL_SRT> --questions <QUESTIONS_JSON> --out <NEW_GATE_JSON> --brief
python scripts/subtitle_evidence.py slice --corpus <LOCAL_SRT> --from 00:02:00 --to 00:02:30
```

多个 `--query` 是 AND。未命中先拆开查词或看邻近语境；不要不断扩大窗口拼出“支持”。
`gate` 只证明原文共现，不能证明题干改换主语、否定词、年代、范围之后仍成立。

多选逐项取证可用 `option_coverage.py check --corpus <LOCAL_SRT> --options <OPTIONS_JSON> --out <NEW_REPORT> --brief`。
输入含 `options:[{key,text}]` 与 `selected:[key]`。它提示缺词、片段命中和枚举差异，**不决定正确集合**；
`ready` 仅表示词面预检未拦截，`requires_semantic_review` 始终为 true。原文“不是甲而是乙”会同时命中甲、乙，不能按命中全选。

## OCR 只补缺口

先核对题量、选项、否定词和图形。整页 OCR 丢失题干时：

```text
python scripts/ocr_guard.py <SCREENSHOT> <OCR_JSON> --dry-run
python scripts/ocr_guard.py <SCREENSHOT> <OCR_JSON> --out <NEW_CROP_PNG>
```

守卫检查题区内首道题、过滤导航和章节标题，其他题仍需分别复核；最多触发一次裁剪和一次 OCR，复用裁剪工具返回的结果。
补读后仍短缺返回 5（需复核），不会循环尝试或声称可作答。短题可能被误报为可疑，可结合原图复核。
原手动 `crop_ocr.py --from-text/--to-text` 保留；新增 `--auto --json` 用于机器化补读。

## 节点回执与成本

先写本次节点回执再汇报：任务范围、授权、媒体列表、字幕/题面批次、答案依据与置信度、真实判定、
提交是否已确认、目录前后读数、调用数、模型介入、耗时和未决项。未做的视频记未做；未打开的测验记未打开。
弹题题库与章节测验分开记录；平台未公布正确答案就留 null，不能由浮层关闭反推正确答案。

优化以相同布局、视频时长、质量与授权范围比较“每个已验收节点”的总调用数和模型输入/缓存/输出 token；
重复 OCR、失败恢复和人工补证也计入。返回字节、传输请求字节、播放墙钟分别记录，不能换算成订阅额度或正确率。
DSH 的历史调用预算只能作为定位异常的参考，不照搬为 Codex 的考核线。

## 本次迁移的范围

本版更新 DSH 适配、整包安装探针、OCR 单次补读与逐选项证据预检；Codex 会话按操作只携带需要的脚本，
只保留上一弹题的摘要键，并拒绝并发重叠事务。现有 `--brief` 字幕能力得到明确路由，没有重复实现。
独立 DSH 的题库/知识文档流水线、付费 ASR、浏览器多账号并发和窗口 watcher 继续由独立版维护，本次没有复制或启动。
