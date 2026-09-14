# mooc-agent-skill

> 安全优先、可断点续跑、由 AI agent 监督的 MOOC（超星学习通、中国大学MOOC）任务点完成工具。
> 核心卖点不是"刷得快"，而是"刷得稳"：真实播放、风控感知、异常才叫人；
> **默认无头 Runner，不占用你的电脑；登录自适应（凭据登录前获取、通道自动降级）。**

## 定位

GitHub 上刷课工具很多（API 伪造心跳的 CLI、油猴脚本、AI 答题），但几乎全部以
"尽快完成"为导向。本项目的差异化：

1. **安全模式是一等公民** —— 真实 2 倍速播放（官方最高档）、每日任务点上限检测、
   弹题处理、字体混淆题目处理、节奏模拟，而不是把风控当副作用。
2. **Agent skill 形态** —— 确定性工作交给脚本（Runner），LLM agent 只处理异常
   （测验读题、弹窗、验证码）。SKILL.md 是 harness 无关的运行手册，
   任何能跑命令行和截图的 agent（ZCode / Claude Code / Codex / OpenClaw…）都能当监督者。
   Runner 无头运行，**挂机不占用电脑**；登录自适应：**每次登录前先问用户本次账号**
   （密码只由用户本地告知，或扫码），通道自动降级（密码→扫码/短信），
   **不存储不复用任何历史登录信息**，账号数据只保留本地。
3. **页面知识是一等资产** —— `knowledge/` 里沉淀 iframe 结构、选择器、接口知识、
   坑清单，这是最难获得的部分，油猴脚本等其他产品线也从这里生成。

## 当前状态：骨架期（Phase 1–2）

- [x] 仓库骨架与文档
- [x] 知识库 `knowledge/chaoxing.md` + `knowledge/icourse163.md`（实测浏览器侧知识 + 上游接口知识）
- [x] 运行手册 `SKILL.md`（**双平台**：Runner 默认形态 + 凭据获取流程 + 平台路由 +
      分平台 paused 词表处理表，skill 名 `auto-online-course-agent-skill`）
- [x] 保活脚本独立版 `scripts/keepalive.js`（实测 v2.1）+ 监督者变体
      `scripts/keepalive.supervisor.js`（标题信标，供远程低频轮询）
- [x] Runner MVP（icourse163）— `platforms/icourse163/`：自动发现任务 + **自适应登录
      （密码/短信/扫码）** + 真实播放循环；**2026-09-14 马原课新周 14/14 全部 learned**
- [x] Runner（chaoxing）— `platforms/chaoxing/`：结构就绪；实测发现学习通风控会切出
      无头会话 → 学习通改以**可见浏览器监督模式**完成（2026-09-14 网络安全培训 19/19，
      侧边浏览器 + 9010 验证码 agent-first 一次通过，见 field-notes）
- [x] 凭据层 — `credentials.example.json` 模板（`credentials.local.json` 已 gitignore，
      多账号 `--account` 选择）；每次登录前监督者询问用户本次账号（安全规则第 11 条）
- [ ] chaoxing Runner 实测收敛 + core/ 引擎提取（等两平台 runner 实测后提炼公共部分）— Phase 2 收尾
- [ ] 模式配置化 / 多账号并发 — Phase 3
- [ ] 油猴脚本产品线 — Phase 4

## 使用

现阶段请阅读 [SKILL.md](SKILL.md)（给 agent 看的运行手册）；
人类读者看 [docs/architecture.md](docs/architecture.md) 了解设计。

## 免责声明

- 本项目仅供学习交流，使用者需自行承担账号风险，并遵守所在学校/平台的规定。
- 本项目**不伪造**学习进度上报、不绕过付费/权限控制；学习进度由平台真实记录的
  真实播放产生。
- 代码以 MIT 协议发布。接口与页面**事实知识**部分学习自
  [Samueli924/chaoxing](https://github.com/Samueli924/chaoxing)（GPL-3.0）等开源项目，
  未搬运其代码；如未来移植其代码，相应文件将遵循 GPL-3.0。

## 致谢

- [Samueli924/chaoxing](https://github.com/Samueli924/chaoxing) — 接口知识的主要参考
- [ocsjs/ocsjs](https://github.com/ocsjs/ocsjs) — 浏览器内脚本路线的多平台参考
