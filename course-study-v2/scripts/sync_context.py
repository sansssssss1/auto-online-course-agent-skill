"""Synchronise state.json and run-context.md in one offline call.

The run-context "current business node" summary is generated from state.json,
while the read-file list and environment-facts sections are preserved. Small
files are replaced atomically via a same-directory temp file. Repeated calls
with no changes are idempotent (identical bytes).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

NODE_HEADER = "## 三、当前业务节点摘要"


class SyncError(Exception):
    """A user-facing input error; the CLI maps it to a non-zero exit."""


def write_atomic(path, text):
    """Write text via a same-directory temp file then atomically replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(str(temporary), str(path))


def load_state(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SyncError("state file not found: " + str(path))
    except json.JSONDecodeError as exc:
        raise SyncError("invalid state JSON: " + str(exc))


def _set_path(data, dotted_key, value):
    keys = dotted_key.split(".")
    cursor = data
    for key in keys[:-1]:
        if not isinstance(cursor.get(key), dict):
            cursor[key] = {}
        cursor = cursor[key]
    cursor[keys[-1]] = value


def _parse_value(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def apply_sets(state, assignments):
    for assignment in assignments:
        if "=" not in assignment:
            raise SyncError("--set expects key=value: " + assignment)
        key, raw = assignment.split("=", 1)
        _set_path(state, key.strip(), _parse_value(raw))
    return state


def _auth_text(authorization):
    if isinstance(authorization, dict):
        return "、".join("%s=%s" % (k, v) for k, v in authorization.items())
    return str(authorization)


def _completed_text(completed):
    if not completed:
        return "无"
    if isinstance(completed, list):
        labels = [
            str(item.get("section", item)) if isinstance(item, dict)
            else str(item) for item in completed
        ]
        return "、".join(labels)
    return str(completed)


def render_node_summary(state):
    """Deterministically render the node summary bullets from state."""
    lines = []
    account = state.get("account_alias", "?")
    course = state.get("course_key") or state.get("course", "?")
    lines.append(
        "- 账号别名 %s；课程《%s》；授权 %s。"
        % (account, course, _auth_text(state.get("authorization", {}))))

    progress = state.get("progress")
    if isinstance(progress, dict):
        start = progress.get("catalog_start", progress.get("started", "?"))
        verified = progress.get("catalog_verified", progress.get("current", "?"))
        lines.append("- 目录进度：起始 %s，平台已回读 %s。" % (start, verified))
        completed = progress.get("completed_this_run", state.get("completed"))
    elif progress is not None:
        lines.append("- 目录进度：%s。" % progress)
        completed = state.get("completed")
    else:
        completed = state.get("completed")

    lines.append("- 已完成节点：%s。" % _completed_text(completed))

    current = state.get("current")
    if isinstance(current, dict):
        section = current.get("section") or current.get("node", "?")
        detail = str(section)
        if current.get("title"):
            detail += " " + str(current["title"])
        bits = ["状态 " + str(current.get("status", "?"))]
        for field in ("tab", "media_key"):
            if current.get(field):
                bits.append("%s=%s" % (field, current[field]))
        lines.append("- 当前节点：%s（%s）。" % (detail, "，".join(bits)))
        if current.get("note"):
            lines.append("- 节点备注：%s" % current["note"])
    elif current is not None:
        lines.append("- 当前节点：%s。" % current)

    if state.get("pause_reason"):
        lines.append("- 暂停原因：%s" % state["pause_reason"])
    if state.get("next_action"):
        lines.append("- 下一步：%s" % state["next_action"])
    if state.get("updated_at"):
        lines.append("- 更新时间：%s" % state["updated_at"])
    return "\n".join(lines)


def update_run_context(run_context_path, state):
    """Preserve sections 1-2 and regenerate section 3; return the new text."""
    run_context_path = Path(run_context_path)
    if run_context_path.is_file():
        existing = run_context_path.read_text(encoding="utf-8-sig")
    else:
        existing = (
            "# 运行上下文摘要（run-context）\n\n"
            "## 一、已读文件清单（相对路径 + sha256）\n\n"
            "（待模型维护）\n\n"
            "## 二、已确认环境事实\n\n"
            "（待补充）\n"
        )
    summary = render_node_summary(state)
    if NODE_HEADER in existing:
        head = existing.split(NODE_HEADER, 1)[0].rstrip()
    else:
        head = existing.rstrip()
    return head + "\n\n" + NODE_HEADER + "\n\n" + summary + "\n"


def run(args):
    state_path = Path(args.state).resolve()
    state = load_state(state_path)
    if args.set:
        apply_sets(state, args.set)
    if args.touch:
        state["updated_at"] = datetime.now(timezone.utc).astimezone().isoformat()

    if args.set or args.touch:
        write_atomic(state_path,
                     json.dumps(state, ensure_ascii=False, indent=2) + "\n")

    new_context = update_run_context(args.run_context, state)
    context_path = Path(args.run_context).resolve()
    if not context_path.is_file() or \
            context_path.read_text(encoding="utf-8-sig") != new_context:
        write_atomic(context_path, new_context)
    return {
        "state": str(state_path),
        "run_context": str(context_path),
        "state_written": bool(args.set or args.touch),
        "summary_lines": render_node_summary(state).count("\n") + 1,
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--state", required=True, help="Path to state.json")
    parser.add_argument("--run-context", required=True,
                        help="Path to run-context.md")
    parser.add_argument("--set", action="append", default=[],
                        metavar="KEY=VALUE",
                        help="Update a state field (dotted key; value parsed as JSON)")
    parser.add_argument("--touch", action="store_true",
                        help="Refresh state.updated_at before syncing")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except SyncError as exc:
        print("SYNC_ERROR: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
