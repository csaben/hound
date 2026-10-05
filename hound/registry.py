from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import requests

from .adapter import describe, load
from .errors import AdapterError
from .util import platform_name, user_root


def registry_url() -> str:
    source = os.environ.get("HOUND_REGISTRY_URL")
    if not source:
        raise AdapterError(
            "no adapter registry is configured; set HOUND_REGISTRY_URL or pass --registry"
        )
    return source


def fetch(url: str | None = None) -> dict[str, Any]:
    source = url or registry_url()
    if source.startswith(("http://", "https://")):
        response = requests.get(source, timeout=15)
        response.raise_for_status()
        data = response.json()
    else:
        data = json.loads(Path(source).expanduser().read_text(encoding="utf-8"))
    if data.get("schema") != "hound.registry/v1":
        raise AdapterError(f"unsupported registry schema from {source}")
    return data


def compatible(entry: dict[str, Any]) -> tuple[bool, str]:
    platforms = entry.get("platforms", {})
    current = platform_name()
    if platforms and current not in platforms:
        return False, f"requires {', '.join(platforms)}"
    backend = entry.get("requires", {}).get("backend")
    if backend == "foxhound" and current != "windows":
        return False, "Foxhound currently requires Windows"
    return True, "compatible"


def search(query: str = "", include_incompatible: bool = False, url: str | None = None) -> list[dict[str, Any]]:
    query = query.casefold()
    out = []
    for raw in fetch(url).get("adapters", []):
        haystack = f"{raw.get('name', '')} {raw.get('description', '')}".casefold()
        if query and query not in haystack:
            continue
        ok, reason = compatible(raw)
        if ok or include_incompatible:
            out.append({**raw, "compatible": ok, "compatibility": reason})
    return out


def installed() -> list[dict[str, Any]]:
    roots = [Path.cwd() / ".hound" / "adapters", user_root() / "adapters"]
    seen: set[Path] = set()
    out = []
    for root in roots:
        if not root.exists():
            continue
        for manifest in list(root.glob("*/adapter.yaml")) + list(root.glob("*/adapter.yml")):
            if manifest.parent.resolve() in seen:
                continue
            seen.add(manifest.parent.resolve())
            try:
                out.append(describe(load(manifest.parent)))
            except AdapterError as exc:
                out.append({"name": manifest.parent.name, "path": str(manifest.parent), "error": str(exc)})
    return out


def install(name: str, revision: str | None = None, url: str | None = None) -> dict[str, Any]:
    matches = [x for x in search(name, url=url) if x.get("name") == name]
    if not matches:
        raise AdapterError(f"no compatible remote adapter named {name!r}")
    entry = matches[0]
    repo = entry["repository"]
    ref = revision or entry.get("revision")
    destination = user_root() / "adapters" / name
    if destination.exists():
        raise AdapterError(f"{destination} already exists; local adapters are never overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hound-adapter-") as td:
        command = ["git", "clone", "--depth", "1"]
        if ref:
            command += ["--branch", ref]
        command += [repo, td]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise AdapterError(f"git clone failed: {result.stderr.strip()}")
        source = Path(td) / entry.get("path", ".")
        if not source.is_dir():
            raise AdapterError(f"registry path {entry.get('path')!r} does not exist in {repo}")
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git"))
    adapter = load(destination)
    lock = {"name": name, "origin": repo, "revision": ref}
    (destination / "hound.lock").write_text(json.dumps(lock, indent=2), encoding="utf-8")
    return describe(adapter) | {"origin": repo, "revision": ref}
