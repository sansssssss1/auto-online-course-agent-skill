# 本地状态与交接

新版任务目录由调用方明确选择，例如 `runs/<task-id>/`；脚本使用绝对路径或相对输入文件的位置，
不把当前shell目录当成技能资源根。旧目录不移动、不清理、不覆盖。

一个任务目录可包含 `state.json`、课程配置、列表快照、读题批次、验算脚本、产物清单和脱敏摘要。
密码保留在用户选择的本地凭据位置或本次进程环境中，不写进状态和输出日志。

```json
{
  "schema_version": 1,
  "task_id": "local-task",
  "platform": "chaoxing",
  "mode": "course",
  "account_alias": "account-a",
  "course_key": "course-a",
  "authorization": {"read": true, "answer": false, "submit": false},
  "active_attempt": null,
  "current": {"section": "section-a", "media_key": null},
  "confirmed": [],
  "pause_reason": null,
  "next_action": "reload-list-and-verify",
  "updated_at": "2026-01-01T00:00:00+08:00"
}
```

这是记录格式，不授予动作权限；authorization 来自当前用户与同一任务已有授权。
`confirmed` 每项应包含对象身份、平台证据、读取时间和使用方法；没有证据的旧done不能直接计入。

进行中测验另记录 attempt标识、是否已开始、剩余时间/截止、已保存答案清单和提交结果。
保存时避免密码、cookie和签名链接；题目、答案与真实课程资料可以保留在本机任务目录。

更新小型JSON文件用“临时文件→同目录替换”，避免中断产生半份状态。切换执行器先停旧进程。
旧版可能用字符串 paused 或布尔 paused+pauseReason；读取时记录原格式并解释，不原地改写旧文件。

交接应说明：任务与账号别名、授权范围、当前执行器/标签、进行中的尝试、已确认项、未知项、
最近错误、状态文件位置和下一步。恢复先读盘面再核对平台，不以历史聊天中的完成声明替代。
