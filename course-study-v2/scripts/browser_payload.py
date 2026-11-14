"""Generate a read-only browser evaluate function; never connects to a browser."""

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
COLLECTORS = {"tasks": "collect_task_list.js", "questions": "collect_questions.js"}
PROTECTED_DIRECTORIES = ("scripts", "references", "adapters", "agents", "tests", "local")


def build_payload(kind, scope):
    source = (ROOT / "scripts" / COLLECTORS[kind]).read_text(encoding="utf-8-sig").strip()
    if scope == "page":
        return f"(options) => ({source})(document, options || {{}})\n"
    return f"(body, options) => ({source})(body.ownerDocument, options || {{}})\n"


OPTIONS_PLACEHOLDER = '{"platform": "chaoxing", "scope": {"account_alias": "<alias>"}}'


def build_bu_call(kind, scope):
    """Return a paste-ready bu.js call snippet; this never opens a browser."""
    payload = build_payload(kind, scope).rstrip("\n")
    if scope == "page":
        return (
            "# Paste into a computer_use_tool(plane=\"bu\") cell; no browser connection is made here.\n"
            "import json\n"
            "payload = \"\"\"" + payload + "\"\"\"\n"
            "options = " + OPTIONS_PLACEHOLDER + "\n"
            "bu.js(\"(\" + payload + \")(\" + json.dumps(options, ensure_ascii=False) + \")\")\n"
        )
    return (
        "# Paste into a computer_use_tool(plane=\"bu\") cell; body is a same-origin JS element.\n"
        "import json\n"
        "payload = \"\"\"" + payload + "\"\"\"\n"
        "options = " + OPTIONS_PLACEHOLDER + "\n"
        "bu.js(\"(\" + payload + \")(document.querySelector(\\\"<BODY_SELECTOR>\\\"), \"\n"
        "       + json.dumps(options, ensure_ascii=False) + \")\")\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=COLLECTORS)
    parser.add_argument("--scope", choices=("page", "element"), required=True)
    parser.add_argument("--out", help="New output file; existing files are never replaced")
    parser.add_argument("--emit-bu-call", action="store_true",
                        help="Print a paste-ready bu.js call snippet with an inline option placeholder; no browser connection")
    args = parser.parse_args(argv)
    try:
        if args.emit_bu_call:
            print(build_bu_call(args.kind, args.scope), end="")
            return 0
        if not args.out:
            raise ValueError("--out is required unless --emit-bu-call is used")
        output = Path(args.out).expanduser().resolve()
        if output == ROOT or output.exists():
            raise ValueError("Refusing to overwrite an existing file or directory")
        for name in PROTECTED_DIRECTORIES:
            protected = ROOT / name
            if output == protected or protected in output.parents:
                raise ValueError("Choose an output outside the skill source and private configuration directories")
        if output.parent == ROOT:
            raise ValueError("Choose an independent output directory or a task run directory")
        payload = build_payload(args.kind, args.scope)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        print(json.dumps({"status": "ok", "kind": args.kind, "scope": args.scope,
                          "output": str(output), "browser_connected": False}))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
