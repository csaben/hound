from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path

from . import __version__
from .adapter import describe, load, schema
from .errors import HoundError
from .foxhound import ensure_helper, find_helper
from .registry import install, installed, search
from .runner import Hound, RunOptions
from .util import dump, platform_name


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="hound", description="Drive, inspect, and record apps without interrupting the user")
    root.add_argument("--version", action="version", version=f"hound {__version__}")
    root.add_argument("--json", action="store_true", help="machine-readable output")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="check this machine")
    commands.add_parser("setup", help="download and verify the native Foxhound helper")
    commands.add_parser("adapter-schema", help="print the adapter contract")

    adapters = commands.add_parser("adapters", help="discover and manage adapters")
    sub = adapters.add_subparsers(dest="adapters_command", required=True)
    sub.add_parser("list", help="list installed adapters")
    remote = sub.add_parser("search", help="search compatible remote adapters")
    remote.add_argument("query", nargs="?", default="")
    remote.add_argument("--all-platforms", action="store_true")
    remote.add_argument("--registry")
    add = sub.add_parser("add", help="install one remote adapter")
    add.add_argument("name")
    add.add_argument("--revision")
    add.add_argument("--registry")
    info = sub.add_parser("info", help="inspect an adapter")
    info.add_argument("adapter")
    path = sub.add_parser("path", help="print an adapter's editable directory")
    path.add_argument("adapter")

    run = commands.add_parser("run", help="run an adapter")
    run.add_argument("adapter")
    run.add_argument("goal", nargs="?")
    run.add_argument("--driver", choices=("jev", "clef"))
    run.add_argument("--tutorial", action="store_true")
    run.add_argument("--no-record", action="store_true")
    run.add_argument("--no-captions", action="store_true")
    run.add_argument("--max-steps", type=int, default=20)
    run.add_argument("--timeout", type=float, default=180)
    run.add_argument("--output", type=Path)
    run.add_argument("--var", action="append", default=[], metavar="KEY=VALUE")
    return root


def check() -> dict:
    helper = find_helper()
    return {
        "ok": platform_name() == "windows" and bool(helper),
        "hound": __version__, "python": platform.python_version(), "platform": platform_name(),
        "foxhound_helper": helper, "ffmpeg": shutil.which("ffmpeg"),
        "jev_key": bool(os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")),
        "clef_url": os.environ.get("CLEF_URL"),
    }


def _variables(items: list[str]) -> dict[str, str]:
    out = {}
    for item in items:
        if "=" not in item:
            raise HoundError(f"--var expects KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        out[key] = value
    return out


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    json_anywhere = "--json" in raw
    raw = [item for item in raw if item != "--json"]
    args = parser().parse_args(raw)
    args.json = args.json or json_anywhere
    try:
        if args.command == "check":
            result = check()
        elif args.command == "setup":
            result = {"ok": True, "foxhound_helper": ensure_helper()}
        elif args.command == "adapter-schema":
            result = schema()
        elif args.command == "adapters":
            if args.adapters_command == "list":
                result = installed()
            elif args.adapters_command == "search":
                result = search(args.query, args.all_platforms, args.registry)
            elif args.adapters_command == "add":
                result = install(args.name, args.revision, args.registry)
            elif args.adapters_command == "info":
                result = describe(load(args.adapter))
            else:
                result = str(load(args.adapter).path)
        elif args.command == "run":
            adapter = load(args.adapter)
            driver = args.driver or adapter.data.get("driver", {}).get("default", "jev")
            options = RunOptions(record=not args.no_record, captions=not args.no_captions,
                                 tutorial=args.tutorial, max_steps=args.max_steps, timeout_s=args.timeout,
                                 output=args.output, variables=_variables(args.var))
            result = Hound(adapter, driver).run(args.goal, options).as_dict()
        else:
            raise HoundError("unknown command")
        if args.json or isinstance(result, (dict, list)):
            print(dump(result))
        else:
            print(result)
        return 0 if not isinstance(result, dict) or result.get("success", result.get("ok", True)) else 1
    except (HoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        if args.json:
            print(dump({"ok": False, "error": str(exc)}))
        else:
            print(f"hound: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
