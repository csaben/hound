from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .errors import HoundError
from .evidence import compose_focus_videos
from .runner import Hound, RunOptions, RunResult
from .util import render, user_root


@dataclass(frozen=True)
class Chain:
    path: Path
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.data["name"])


@dataclass
class ChainResult:
    success: bool
    run_dir: Path
    stages: list[dict[str, Any]]
    reason: str
    tutorial: Path | None = None
    metrics: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "run_dir": str(self.run_dir),
            "tutorial": str(self.tutorial) if self.tutorial else None,
        }


def load_chain(value: str | Path) -> Chain:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise HoundError(f"chain {value!r} was not found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise HoundError(f"cannot read chain {path}: {exc}") from exc
    if data.get("schema") != "hound.chain/v1":
        raise HoundError(f"{path}: unsupported chain schema {data.get('schema')!r}")
    if not data.get("name") or not isinstance(data.get("stages"), list) or not data["stages"]:
        raise HoundError(f"{path}: a chain needs a name and at least one stage")
    ids = [stage.get("id") for stage in data["stages"]]
    if any(not stage_id for stage_id in ids) or len(ids) != len(set(ids)):
        raise HoundError(f"{path}: every chain stage needs a unique id")
    if any(not stage.get("adapter") for stage in data["stages"]):
        raise HoundError(f"{path}: every chain stage needs an adapter")
    layout = data.get("recording", {}).get("layout", "focus")
    if layout != "focus":
        raise HoundError(f"{path}: unsupported recording layout {layout!r}; use 'focus'")
    return Chain(path, data)


class ChainRunner:
    def __init__(self, chain: str | Path | Chain, driver: str | None = None):
        self.chain = chain if isinstance(chain, Chain) else load_chain(chain)
        self.driver = driver

    def _adapter_ref(self, value: str) -> str | Path:
        relative = self.chain.path.parent / value
        return relative if relative.exists() else value

    def run(self, options: RunOptions | None = None) -> ChainResult:
        options = options or RunOptions()
        data = render(self.chain.data, options.variables)
        run_dir = options.output or user_root() / "runs" / self.chain.name / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = Path(run_dir).resolve()
        stages_root = run_dir / "stages"
        stages_root.mkdir(parents=True, exist_ok=True)
        stage_summaries: list[dict[str, Any]] = []
        clips: list[Path] = []
        total_steps = 0
        driver_calls = 0
        driver_ms = 0.0
        input_tokens = 0
        output_tokens = 0
        estimated_cost = 0.0
        reason = "done"
        success = True

        for index, stage in enumerate(data["stages"]):
            stage_id = str(stage["id"])
            stage_dir = stages_root / f"{index + 1:02d}-{stage_id}"
            stage_options = replace(
                options,
                output=stage_dir,
                variables={**options.variables, **stage.get("variables", {})},
                tutorial=bool(options.tutorial or data.get("tutorial", False)),
            )
            result: RunResult = Hound(
                self._adapter_ref(str(stage["adapter"])),
                stage.get("driver") or self.driver or "jev",
            ).run(stage.get("goal"), stage_options)
            summary = {"id": stage_id, **result.as_dict()}
            stage_summaries.append(summary)
            total_steps += result.steps
            driver_calls += int(result.metrics.get("driver_calls") or 0)
            driver_ms += float(result.metrics.get("driver_ms") or 0)
            input_tokens += int(result.metrics.get("driver_input_tokens") or 0)
            output_tokens += int(result.metrics.get("driver_output_tokens") or 0)
            estimated_cost += float(result.metrics.get("estimated_model_cost_usd") or 0)
            clip = result.captioned or result.recording
            if clip:
                clips.append(clip)
            if not result.success and not stage.get("continue_on_failure", False):
                success = False
                reason = f"stage {stage_id}: {result.reason}"
                break

        tutorial = None
        if options.record and clips:
            tutorial = compose_focus_videos(clips, run_dir / "tutorial.mp4")
        metrics = {
            "stages": len(stage_summaries),
            "steps": total_steps,
            "driver_calls": driver_calls,
            "driver_ms": round(driver_ms, 1),
            "driver_input_tokens": input_tokens,
            "driver_output_tokens": output_tokens,
            "estimated_model_cost_usd": round(estimated_cost, 9),
        }
        summary = {
            "format": "hound.chain-run/v1",
            "chain": self.chain.name,
            "success": success,
            "reason": reason,
            "stages": stage_summaries,
            "tutorial": tutorial.name if tutorial else None,
            "metrics": metrics,
        }
        (run_dir / "chain.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return ChainResult(success, run_dir, stage_summaries, reason, tutorial, metrics)
