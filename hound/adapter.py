from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from .errors import AdapterError
from .util import platform_name, render, user_root


@dataclass
class Adapter:
    path: Path
    data: dict[str, Any]
    hooks: ModuleType | None = None

    @property
    def name(self) -> str:
        return str(self.data["name"])

    @property
    def workflow(self) -> dict[str, Any]:
        return self.data["workflow"]

    @property
    def target(self) -> dict[str, Any]:
        value = self.data["target"]
        per_os = value.get(platform_name())
        return {**value, **per_os} if isinstance(per_os, dict) else value

    def expanded(self, variables: dict[str, Any]) -> "Adapter":
        return Adapter(self.path, render(self.data, variables), self.hooks)

    def call(self, name: str, context: Any, *args: Any) -> Any:
        fn = getattr(self.hooks, name, None) if self.hooks else None
        if not callable(fn):
            raise AdapterError(f"adapter {self.name!r} has no hook {name!r}")
        return fn(context, *args)


def _resolve(value: str | Path) -> Path:
    raw = Path(value).expanduser()
    candidates = [
        raw,
        Path.cwd() / raw,
        Path.cwd() / ".hound" / "adapters" / str(value),
        user_root() / "adapters" / str(value),
    ]
    for candidate in candidates:
        if candidate.is_file() and candidate.name in ("adapter.yaml", "adapter.yml"):
            return candidate.parent.resolve()
        if candidate.is_dir() and any((candidate / n).exists() for n in ("adapter.yaml", "adapter.yml")):
            return candidate.resolve()
    raise AdapterError(
        f"adapter {value!r} not found; use a path or install it with `hound adapters add {value}`"
    )


def load(value: str | Path) -> Adapter:
    path = _resolve(value)
    manifest = next(p for p in (path / "adapter.yaml", path / "adapter.yml") if p.exists())
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise AdapterError(f"cannot read {manifest}: {exc}") from exc
    validate(data, manifest)
    hooks = None
    hook_path = path / "hooks.py"
    if hook_path.exists():
        spec = importlib.util.spec_from_file_location(f"hound_adapter_{data['name']}", hook_path)
        if not spec or not spec.loader:
            raise AdapterError(f"cannot load hooks from {hook_path}")
        hooks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hooks)
    return Adapter(path, data, hooks)


def validate(data: dict[str, Any], source: Path | str = "adapter") -> None:
    required = ("schema", "name", "target", "workflow")
    missing = [key for key in required if key not in data]
    if missing:
        raise AdapterError(f"{source}: missing {', '.join(missing)}")
    if data["schema"] != "hound.adapter/v1":
        raise AdapterError(f"{source}: unsupported schema {data['schema']!r}")
    workflow = data["workflow"]
    if not workflow.get("goal"):
        raise AdapterError(f"{source}: workflow.goal is required")
    actions = workflow.get("actions", [])
    ids = [a.get("id") for a in actions]
    if any(not x for x in ids) or len(ids) != len(set(ids)):
        raise AdapterError(f"{source}: every workflow action needs a unique id")
    supported = {"click", "key", "type", "scroll", "wait", "hook"}
    bad = [a.get("op") for a in actions if a.get("op") not in supported]
    if bad:
        raise AdapterError(f"{source}: unsupported action operations: {bad}")


def schema() -> dict[str, Any]:
    return {
        "schema": "hound.adapter/v1",
        "required": ["schema", "name", "target", "workflow"],
        "target": {
            "backend": "foxhound",
            "one_of": ["process", "pid", "title", "hwnd"],
            "optional": ["launch", "cwd", "launch_wait_s", "backend_timeout_s", "helper_url", "helper_path", "new_console"],
        },
        "workflow": {
            "required": ["goal", "actions"],
            "optional": ["guidance", "criteria", "done", "start", "source_refs"],
            "action_ops": ["click", "key", "type", "scroll", "wait", "hook"],
            "action_flow": {"after": "action id or list of prerequisite action ids", "once": "default true"},
        },
        "hook_signatures": {
            "prepare": "prepare(adapter, run_dir) -> None (runs before launch)",
            "reset": "reset(context) -> None",
            "criterion": "name(context) -> bool | {pass, detail}",
            "done": "name(context) -> bool",
            "action": "name(context, action) -> None",
        },
    }


def describe(adapter: Adapter) -> dict[str, Any]:
    return {
        "name": adapter.name,
        "path": str(adapter.path),
        "description": adapter.data.get("description", ""),
        "platforms": adapter.data.get("platforms", {}),
        "actions": len(adapter.workflow.get("actions", [])),
        "criteria": len(adapter.workflow.get("criteria", [])),
        "source_refs": adapter.workflow.get("source_refs", []),
    }


def read_lock(path: Path) -> dict[str, Any]:
    lock = path / "hound.lock"
    if not lock.exists():
        return {}
    try:
        return json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
