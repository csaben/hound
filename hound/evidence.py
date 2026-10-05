from __future__ import annotations

import json
import io
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from PIL import Image


class Trace:
    def __init__(self, path: Path, started: float):
        self.path = path
        self.started = started
        self.lock = threading.Lock()

    def emit(self, kind: str, **data) -> dict:
        now = time.time()
        event = {"kind": kind, "t_epoch": now, "t_video": round(now - self.started, 3), **data}
        with self.lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        return event


class Recorder:
    def __init__(self, directory: Path, capture: Callable[[], bytes], fps: int = 8):
        self.directory = directory
        self.capture = capture
        self.fps = fps
        self.frames = directory / "frames"
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.error: str | None = None

    def start(self) -> None:
        self.frames.mkdir(parents=True, exist_ok=True)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        index = 0
        frame_size = (0, 0)
        interval = 1 / max(self.fps, 1)
        deadline = time.monotonic()
        while not self.stop_event.is_set():
            try:
                payload = self.capture()
                with Image.open(io.BytesIO(payload)) as image:
                    size = image.size
                if size[0] * size[1] > frame_size[0] * frame_size[1]:
                    # Startup prompts can briefly be Foxhound's only resolvable window. If the
                    # real application stage appears larger, discard those prompt-sized frames so
                    # ffmpeg does not lock the whole recording to the first tiny dimensions.
                    for old in self.frames.glob("*.png"):
                        old.unlink()
                    frame_size, index = size, 0
                if size != frame_size:
                    deadline += interval
                    self.stop_event.wait(max(0, deadline - time.monotonic()))
                    continue
                (self.frames / f"{index:08d}.png").write_bytes(payload)
                index += 1
            except Exception as exc:  # recorder failure should not strand app cleanup
                self.error = repr(exc)
                return
            deadline += interval
            self.stop_event.wait(max(0, deadline - time.monotonic()))

    def finish(self, output: Path) -> Path | None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.error or not any(self.frames.glob("*.png")):
            return None
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return None
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(self.fps),
                   "-i", str(self.frames / "%08d.png"), "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        return output if result.returncode == 0 else None


def _stamp(seconds: float) -> str:
    ms = int(max(0, seconds) * 1000)
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def write_captions(path: Path, events: list[dict], end: float) -> None:
    lines = ["WEBVTT", ""]
    for index, event in enumerate(events):
        start = float(event["t_video"])
        following = float(events[index + 1]["t_video"]) if index + 1 < len(events) else end
        finish = min(max(start + 1.2, following), start + 4.0)
        lines += [f"{_stamp(start)} --> {_stamp(finish)}", event["caption"], ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def burn_captions(video: Path, captions: Path, output: Path) -> Path | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not video.exists():
        return None
    escaped = str(captions.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-vf", f"subtitles='{escaped}'", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)],
        capture_output=True, text=True,
    )
    return output if result.returncode == 0 else None


def compose_focus_videos(videos: list[Path], output: Path, width: int = 1280, height: int = 720) -> Path | None:
    """Normalize stage clips to one canvas and join them with hard cuts."""
    ffmpeg = shutil.which("ffmpeg")
    videos = [Path(video) for video in videos if Path(video).exists()]
    if not ffmpeg or not videos:
        return None
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for index, video in enumerate(videos):
        inputs += ["-i", str(video)]
        label = f"v{index}"
        labels.append(f"[{label}]")
        filters.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30[{label}]"
        )
    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[outv]")
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
         "-filter_complex", ";".join(filters), "-map", "[outv]",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)],
        capture_output=True, text=True,
    )
    return output if result.returncode == 0 else None
