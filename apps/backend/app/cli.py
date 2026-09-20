"""Terminal access to the same engine the app drives: python -m app.cli <command>. Keys come from the repo
.env (like dev mode) and the data folder from ACS_DATA_DIR (default <repo>/data), so the CLI works on the
app's own projects. Publish commands need the Buffer connection and media host set up in the app first."""
import argparse
import json
import sys

from app import database


def main(argv=None) -> int:
    database.migrate()
    parser = argparse.ArgumentParser(prog="python -m app.cli",
                                     description="Drive AiContentStudio from the terminal.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("projects", help="list projects")
    clips = sub.add_parser("clips", help="list a project's clips")
    clips.add_argument("project_id")
    export = sub.add_parser("export", help="export a project's rendered pieces/clips to a folder")
    export.add_argument("project_id")
    channels = sub.add_parser("channels", help="list connected Buffer channels")
    publish = sub.add_parser("publish", help="publish an approved clip through Buffer")
    publish.add_argument("project_id")
    publish.add_argument("clip_idx", type=int)
    publish.add_argument("--channels", required=True, help="comma-separated Buffer channel ids")
    publish.add_argument("--at", help="schedule: ISO time, e.g. 2026-09-21T09:00:00+01:00 (default: now)")
    tool = sub.add_parser("metricool", help="call a Metricool MCP tool by name (tools: python -m app.cli metricool tools)")
    tool.add_argument("tool")
    tool.add_argument("--args", default="{}", help="JSON object of tool arguments")

    args = parser.parse_args(argv)
    try:
        return _run(args)
    except Exception as e:  # human messages from the engine; anything else is a bug worth its repr
        print(str(e) or repr(e), file=sys.stderr)
        return 1


def _run(args) -> int:
    from app import clips, export, projects
    if args.cmd == "projects":
        print(json.dumps([{k: p[k] for k in ("id", "name", "status")} for p in projects.list_()], indent=2))
    elif args.cmd == "clips":
        rows = clips.list_(args.project_id)
        print(json.dumps([{k: c[k] for k in ("idx", "title", "score", "status", "start_at", "end_at")} for c in rows],
                         indent=2))
    elif args.cmd == "export":
        result = export.export_project(args.project_id)
        print(json.dumps(result, indent=2))
    elif args.cmd == "channels":
        from app.publish import buffer
        print(json.dumps([{k: c[k] for k in ("id", "service", "displayName", "usable")}
                          for c in buffer.channels()], indent=2))
    elif args.cmd == "publish":
        from app.publish import buffer
        result = buffer.publish(args.project_id, args.clip_idx, args.channels.split(","), args.at)
        print(json.dumps([{k: r[k] for k in ("channel_name", "status", "due_at", "external_link", "error")}
                          for r in result], indent=2))
    elif args.cmd == "metricool":
        from app.publish import metricool
        if args.tool == "tools":
            print(json.dumps([{"name": t["name"], "description": t.get("description", "")} for t in metricool.tools()],
                             indent=2))
        else:
            result = metricool.call_tool(args.tool, json.loads(args.args))
            print(result["text"] or json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
