from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .adapter import Adapter, load
from .backend import FoxhoundBackend, HumanState, human_state
from .drivers import Decision, create
from .errors import HoundError
from .evidence import Recorder, Trace, burn_captions, write_captions
from .util import user_root


@dataclass
class RunOptions:
    record: bool = True
    captions: bool = True
    tutorial: bool = False
    max_steps: int = 20
    timeout_s: float = 180
    settle_s: float = 0.4
    fps: int = 8
    output: Path | None = None
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    success: bool
    run_dir: Path
    steps: int
    criteria: list[dict[str, Any]]
    reason: str
    recording: Path | None = None
    captioned: Path | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "run_dir": str(self.run_dir),
                "recording": str(self.recording) if self.recording else None,
                "captioned": str(self.captioned) if self.captioned else None}


@dataclass
class RunContext:
    adapter: Adapter
    backend: FoxhoundBackend
    run_dir: Path
    variables: dict[str, Any]
    last_frame: bytes = b""

    def screenshot(self, name: str | None = None) -> bytes:
        self.last_frame = self.backend.screenshot()
        if name:
            (self.run_dir / "shots" / name).write_bytes(self.last_frame)
        return self.last_frame


class Hound:
    def __init__(self, adapter: str | Path | Adapter, driver: str = "jev"):
        self.adapter = adapter if isinstance(adapter, Adapter) else load(adapter)
        self.driver_name = driver

    def _criteria(self, context: RunContext) -> list[dict[str, Any]]:
        results = []
        for criterion in context.adapter.workflow.get("criteria", []):
            check = criterion.get("check", "")
            if check == "builtin.target_alive":
                value: Any = bool(context.backend.health().get("target"))
            elif check.startswith("hook."):
                value = context.adapter.call(check[5:], context)
            else:
                value = {"pass": False, "detail": f"unknown check {check!r}"}
            if isinstance(value, dict):
                passed = bool(value.get("pass"))
                detail = value.get("detail", "")
            else:
                passed, detail = bool(value), ""
            results.append({"id": criterion.get("id", check), "pass": passed,
                            "expect": criterion.get("expect", ""), "detail": detail})
        return results

    def _done(self, context: RunContext, actions_taken: list[str]) -> bool:
        spec = context.adapter.workflow.get("done", {})
        if not spec:
            return False
        if "hook" in spec:
            return bool(context.adapter.call(spec["hook"], context))
        if "after_action" in spec:
            return spec["after_action"] in actions_taken
        if "all_criteria" in spec:
            values = self._criteria(context)
            return bool(values) and all(x["pass"] for x in values)
        return False

    def run(self, goal: str | None = None, options: RunOptions | None = None) -> RunResult:
        options = options or RunOptions()
        adapter = self.adapter.expanded(options.variables)
        goal = goal or adapter.workflow["goal"]
        run_dir = options.output or user_root() / "runs" / adapter.name / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = Path(run_dir).resolve()
        (run_dir / "shots").mkdir(parents=True, exist_ok=True)
        started = time.time()
        trace = Trace(run_dir / "trace.jsonl", started)
        backend = FoxhoundBackend(adapter.target, timeout=float(adapter.target.get("backend_timeout_s", 20)))
        recorder = None
        action_events: list[dict[str, Any]] = []
        recording = captioned = None
        criteria: list[dict[str, Any]] = []
        actions_taken: list[str] = []
        driver_calls = 0
        driver_ms = 0.0
        input_tokens = 0
        output_tokens = 0
        deliberate_wait_s = 0.0
        backend_start_s = 0.0
        reason = "step limit"
        success = False
        driver = None
        try:
            prepare = getattr(adapter.hooks, "prepare", None) if adapter.hooks else None
            if callable(prepare):
                prepare(adapter, run_dir)
            backend.start()
            backend_start_s = time.time() - started
            context = RunContext(adapter, backend, run_dir, options.variables)
            if options.record:
                recorder = Recorder(run_dir, backend.screenshot, options.fps)
                trace.started = time.time()
                recorder.start()
            start_hook = adapter.workflow.get("start", {}).get("hook")
            if start_hook:
                adapter.call(start_hook, context)
            driver_config = adapter.data.get("driver", {})
            driver = create(self.driver_name, model=driver_config.get("model"), url=driver_config.get("url"))
            actions = adapter.workflow.get("actions", [])
            if not actions:
                raise HoundError("adapter has no workflow actions")
            deadline = time.monotonic() + options.timeout_s
            previous_hash = None
            repeated = 0
            trace.emit("run_start", adapter=adapter.name, goal=goal, driver=self.driver_name)
            for step in range(options.max_steps):
                if time.monotonic() > deadline:
                    reason = "timeout"
                    break
                if self._done(context, actions_taken):
                    reason, success = "done", True
                    break
                frame = context.screenshot(f"{step:03d}-before.png")
                digest = hashlib.sha256(frame).hexdigest()
                repeated = repeated + 1 if digest == previous_hash else 0
                previous_hash = digest
                state = {
                    "goal": goal,
                    "guidance": adapter.workflow.get("guidance", []),
                    "windows": backend.windows(),
                    "actions_taken": actions_taken[-6:],
                    "screen_unchanged_steps": repeated,
                }
                available = []
                for candidate in actions:
                    after = candidate.get("after", [])
                    after = [after] if isinstance(after, str) else after
                    if any(required not in actions_taken for required in after):
                        continue
                    if candidate.get("once", True) and candidate["id"] in actions_taken:
                        continue
                    available.append(candidate)
                if not available:
                    raise HoundError("adapter has no available actions in the current workflow state")
                use_image = self.driver_name == "clef" and adapter.data.get("driver", {}).get("image_policy", "always") != "never"
                if len(available) == 1:
                    decision = Decision(available[0]["id"], 1.0, {"mode": "deterministic"}, 0.0)
                else:
                    decision = driver.choose(state, available, frame if use_image else None)
                usage = decision.raw.get("usage") or {}
                if decision.raw.get("mode") != "deterministic":
                    driver_calls += 1
                    driver_ms += decision.elapsed_ms
                    input_tokens += int(usage.get("input_tokens") or 0)
                    output_tokens += int(usage.get("output_tokens") or 0)
                action = next((a for a in available if a["id"] == decision.action_id), None)
                if action is None:
                    raise HoundError(f"driver chose unavailable action {decision.action_id!r}")
                before_human = human_state()
                action_started = time.time()
                if action["op"] == "hook":
                    adapter.call(action["hook"], context, action)
                    effect: Any = {"ok": True}
                else:
                    effect = backend.act(action)
                if action["op"] == "wait":
                    deliberate_wait_s += float(action.get("seconds", 1))
                time.sleep(options.settle_s)
                after_human = human_state()
                actions_taken.append(action["id"])
                event = trace.emit("action", step=step + 1, action_id=action["id"],
                                   t_video=round(action_started - trace.started, 3),
                                   caption=action.get("caption") or action.get("description") or action["id"],
                                   confidence=decision.confidence, driver_ms=decision.elapsed_ms, effect=effect,
                                   usage=usage or None,
                                   human_state={"before": asdict(before_human), "after": asdict(after_human)})
                action_events.append(event)
                context.screenshot(f"{step:03d}-after.png")
                if action.get("terminal"):
                    reason = "terminal action"
                    success = True
                    break
            else:
                step = options.max_steps - 1
            criteria = self._criteria(context)
            if criteria:
                success = success and all(item["pass"] for item in criteria)
                if not all(item["pass"] for item in criteria):
                    reason = "criteria failed"
            trace.emit("run_end", success=success, reason=reason, criteria=criteria)
            steps = len(actions_taken)
        except Exception as exc:
            trace.emit("run_error", error=repr(exc))
            reason = str(exc)
            steps = len(actions_taken)
        finally:
            if recorder:
                recording = recorder.finish(run_dir / "recording.mp4")
            backend.close()
        if options.captions:
            duration = max(0.1, time.time() - started)
            captions = run_dir / "captions.vtt"
            write_captions(captions, action_events, duration)
            if recording:
                captioned = burn_captions(recording, captions, run_dir / "captioned.mp4")
        driver_model = getattr(driver, "model", None) if driver_calls else None
        if self.driver_name == "jev":
            price_per_million = float(os.environ.get("HOUND_JEV_INPUT_USD_PER_M", "0.042"))
        elif self.driver_name == "clef":
            default_rate = "0.09" if driver_model == "clef-flash" else "0.24"
            price_per_million = float(os.environ.get("HOUND_CLEF_INPUT_USD_PER_M", default_rate))
        else:
            price_per_million = None
        metrics = {
            "wall_s": round(time.time() - started, 3),
            "backend_start_s": round(backend_start_s, 3),
            "driver_calls": driver_calls,
            "driver_ms": round(driver_ms, 1),
            "driver_input_tokens": input_tokens,
            "driver_output_tokens": output_tokens,
            "driver_model": driver_model,
            "deliberate_wait_s": deliberate_wait_s,
            "estimated_model_cost_usd": (
                round(input_tokens / 1_000_000 * price_per_million, 9)
                if price_per_million is not None and input_tokens else None
            ),
            "input_price_usd_per_million": price_per_million,
        }
        summary = {
            "format": "hound.run/v1", "adapter": adapter.name, "driver": self.driver_name,
            "goal": goal, "started": started, "ended": time.time(), "success": success,
            "reason": reason, "steps": steps, "criteria": criteria,
            "recording": recording.name if recording else None,
            "captioned": captioned.name if captioned else None,
            "metrics": metrics,
        }
        (run_dir / "run.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return RunResult(success, run_dir, steps, criteria, reason, recording, captioned, metrics)
