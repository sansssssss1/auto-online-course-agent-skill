# platforms/icourse163 — 中国大学MOOC Runner

真实播放挂机的 Runner 端（监督者-Runner 架构，见 [docs/architecture.md](../../docs/architecture.md)；
**监督者操作手册（登录/监督循环/paused 词表处理表）见仓库根 [SKILL.md](../../SKILL.md) §3**）。
收编自 2026-09-12 首轮实战版本（原路径 `workspace/default/mooc-runner/` 保留，登录态在那边）。

## 安装

```bash
cd platforms/icourse163
npm install        # 仅 playwright-core（驱动系统 Edge，无需下载浏览器内核）
```

## 登录（首次 / 登录态失效时）

```bash
MOOC_PROFILE_DIR="<profile 绝对路径>" npm run login
```

- 会生成 `qr.png`，用手机 App 扫码确认；成功后 `qr-meta.json` 写 `success`
- 短信验证码通道会触发易盾滑块（我们选择不绕过），**扫码是首选**
- runner 兜底的短信通道需要 `MOOC_PHONE` 环境变量 + 把收到的验证码写进 `code.txt`
  （凭据走环境变量与文件握手，不写入脚本与状态文件）

## 挂机运行

```bash
MOOC_PROFILE_DIR="<profile 绝对路径>" npm start
# 可选：外置课程配置（缺省用内置课程；tasks 留空 = 自动发现未 learned 的视频/文档）
MOOC_PROFILE_DIR="<...>" node runner.mjs --course ../../courses/icourse163.example.json
```

- 指向已有登录态时用 `MOOC_PROFILE_DIR`（例如原 `workspace/default/mooc-runner/edge-profile`）；
  不设置则在本目录新建 profile
- 行为：自动发现任务（视频优先）→ 2x 静音真实播放 → 播完回列表核对 `learned` 标记
  （`ended` 不算数）→ 文档任务（20/40/60 秒三轮打开）→ 终态矩阵核对
- 播放器状态机脆弱：恢复顺序 = 播放器大按钮事件序列 → 整页 reload（原理见
  [knowledge/icourse163.md](../../knowledge/icourse163.md)）
- 异常即停：暂停原因写入 `state.json` 的 `paused` 字段（词表与处理表见 SKILL.md §3.4，
  协议见 architecture.md v0.1）

## 目录内运行期产物（已 gitignore，不入库）

`state.json`、`runner.log`、`qr.png`、`qr-meta.json`、`code.txt`、`sms-*.png`、`edge-profile/`
