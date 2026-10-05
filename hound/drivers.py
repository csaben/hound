from __future__ import annotations

import base64
import io
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from PIL import Image

from .errors import DriverError


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
        try:
            from typesafe_sdk import TypeSafeClient
        except ImportError as exc:
            raise DriverError("JEV requires `pip install hound-agent[jev]`") from exc
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
            raise DriverError(f"CLEF request failed: {exc}") from exc
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
