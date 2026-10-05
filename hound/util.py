from __future__ import annotations

import json
import os
import platform
import re
from pathlib import Path
from typing import Any


def user_root() -> Path:
    override = os.environ.get("HOUND_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".hound"


def platform_name() -> str:
    return {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(
        platform.system(), platform.system().lower()
    )


def dump(value: Any, pretty: bool = True) -> str:
    return json.dumps(value, indent=2 if pretty else None, ensure_ascii=False, default=str)


_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def render(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _VAR.sub(lambda m: str(variables.get(m.group(1), m.group(0))), value)
    if isinstance(value, list):
        return [render(x, variables) for x in value]
    if isinstance(value, dict):
        return {k: render(v, variables) for k, v in value.items()}
    return value

