from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from PIL import Image

from .errors import DriverError


def status() -> dict[str, Any]:
    jev_key = bool(os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY"))
    jev_sdk = importlib.util.find_spec("typesafe_sdk") is not None
    clef_url = os.environ.get("CLEF_URL")
    jev_env = '$env:JEV_API_KEY = "<your key>"' if os.name == "nt" else 'export JEV_API_KEY="<your key>"'
    clef_env = (
        '$env:CLEF_URL = "http://127.0.0.1:8787/v1/systemone"'
        if os.name == "nt" else 'export CLEF_URL="http://127.0.0.1:8787/v1/systemone"'
    )
    return {
        "jev": {
            "ready": jev_key and jev_sdk,
            "key_configured": jev_key,
            "sdk_installed": jev_sdk,
            "model": os.environ.get("JEV_MODEL", "jev-latest"),
            "setup": [
                'uv tool install --force --with "typesafe-sdk>=0.7.2" '
                '"hound-agent @ git+https://github.com/csaben/hound.git"',
                jev_env,
                "Set the real value locally; do not paste it into chat.",
            ],
        },
        "clef": {
            "ready": bool(clef_url),
            "url_configured": bool(clef_url),
            "url": clef_url,
            "model": os.environ.get("CLEF_MODEL", "clef"),
            "setup": [
                clef_env,
                "Replace the example with your SystemOne-compatible endpoint when needed.",
            ],
        },
        "note": (
            "Drivers are needed only when two or more workflow actions are valid; "
            "deterministic one-action steps require no credentials."
        ),
    }


@dataclass
class Decision:
    action_id: str
    confidence: float | None
    raw: dict[str, Any]
    elapsed_ms: float


def _question(actions: list[dict[str, Any]], clef_compatible: bool = False) -> dict[str, Any]:
    criteria = {a["id"]: a.get("description") or a["id"] for a in actions}
    if clef_compatible and len(criteria) == 1:
        criteria["__hound_stop__"] = "Stop only if the offered workflow action is unsafe or cannot advance the goal."
    return {
        "next_action": {
            "type": "choice",
            "instructions": "Choose the single safest next action that best advances the goal.",
            "criteria": criteria,
        }
    }


def _parse(raw: dict[str, Any], elapsed: float) -> Decision:
    try:
        answer = raw["answers"]["next_action"]
        choice = answer["choice"]
    except (KeyError, TypeError) as exc:
        raise DriverError(f"driver returned no next_action choice: {raw}") from exc
    return Decision(choice, answer.get("confidence"), raw, round(elapsed * 1000, 1))


class JevDriver:
    name = "jev"

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("JEV_MODEL", "jev-latest")

    def choose(self, state: dict[str, Any], actions: list[dict[str, Any]], image: bytes | None = None) -> Decision:
        if not (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")):
            raise DriverError(
                "JEV is not configured; set JEV_API_KEY or TYPESAFE_API_KEY in your local "
                "environment (do not paste the secret into chat), then run `hound check --json`"
            )
        try:
            from typesafe_sdk import TypeSafeClient
        except ImportError as exc:
            raise DriverError(
                "JEV support is not installed; run `uv tool install --force --with "
                '\"typesafe-sdk>=0.7.2\" \"hound-agent @ git+https://github.com/csaben/hound.git\"`'
            ) from exc
        if "TYPESAFE_API_KEY" not in os.environ and os.environ.get("JEV_API_KEY"):
            os.environ["TYPESAFE_API_KEY"] = os.environ["JEV_API_KEY"]
        started = time.perf_counter()
        response = TypeSafeClient(model=self.model).system_one(state=state, questions=_question(actions))
        raw = response.model_dump() if hasattr(response, "model_dump") else json.loads(response.json())
        return _parse(raw, time.perf_counter() - started)


class ClefDriver:
    name = "clef"

    def __init__(self, model: str | None = None, url: str | None = None):
        self.model = model or os.environ.get("CLEF_MODEL", "clef")
        self.url = url or os.environ.get("CLEF_URL", "http://127.0.0.1:8787/v1/systemone")

    def choose(self, state: dict[str, Any], actions: list[dict[str, Any]], image: bytes | None = None) -> Decision:
        body: dict[str, Any] = {"model": self.model, "state": state, "questions": _question(actions, True)}
        if image:
            with Image.open(io.BytesIO(image)) as source:
                source.thumbnail((448, 448), Image.Resampling.LANCZOS)
                encoded = io.BytesIO()
                source.convert("RGB").save(encoded, format="JPEG", quality=82, optimize=True)
            body["images"] = [{
                "content_type": "image/jpeg",
                "base64": base64.b64encode(encoded.getvalue()).decode("ascii"),
            }]
        started = time.perf_counter()
        try:
            response = requests.post(self.url, json=body, timeout=float(os.environ.get("CLEF_TIMEOUT", "120")))
            if not response.ok:
                detail = response.text[:300].replace("\n", " ")
                raise DriverError(f"CLEF request failed: HTTP {response.status_code}: {detail}")
        except requests.RequestException as exc:
            hint = " Set CLEF_URL to a reachable SystemOne endpoint and run `hound check --json`."
            raise DriverError(f"CLEF request failed at {self.url}: {exc}.{hint}") from exc
        raw = response.json()
        if isinstance(raw.get("result"), dict):
            raw = raw["result"]
        return _parse(raw, time.perf_counter() - started)


def create(name: str, **kwargs: Any) -> JevDriver | ClefDriver:
    if name == "jev":
        return JevDriver(kwargs.get("model"))
    if name == "clef":
        return ClefDriver(kwargs.get("model"), kwargs.get("url"))
    raise DriverError(f"unknown driver {name!r}; choose jev or clef")
