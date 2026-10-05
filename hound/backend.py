from __future__ import annotations

import ctypes
import ctypes.wintypes
import csv
import io
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .errors import BackendError
from .foxhound import ensure_helper


@dataclass(frozen=True)
class HumanState:
    foreground: int | None
    cursor: tuple[int, int] | None


def human_state() -> HumanState:
    if os.name != "nt":
        return HumanState(None, None)
    user32 = ctypes.windll.user32
    point = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return HumanState(int(user32.GetForegroundWindow()), (point.x, point.y))


class FoxhoundBackend:
    def __init__(self, target: dict[str, Any], timeout: float = 10):
        self.target = target
        self.external_helper = bool(target.get("helper_url"))
        if self.external_helper:
            self.url = str(target["helper_url"]).rstrip("/")
        else:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            self.url = f"http://127.0.0.1:{port}"
        self.timeout = timeout
        self.process: subprocess.Popen | None = None
        self.owned_app: subprocess.Popen | None = None
        self.owned_pids: set[int] = set()

    @staticmethod
    def _process_pids(image: str) -> set[int]:
        if os.name != "nt":
            return set()
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
        )
        out: set[int] = set()
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) > 1 and row[0].casefold() == image.casefold():
                try:
                    out.add(int(row[1]))
                except ValueError:
                    pass
        return out

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        try:
            response = requests.request(method, self.url + path, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise BackendError(f"Foxhound {path} failed: {exc}") from exc

    def _target_spec(self) -> dict[str, Any]:
        for key in ("hwnd", "pid", "title", "process"):
            if self.target.get(key) is not None:
                return {key: self.target[key]}
        raise BackendError("target needs one of process, pid, title, or hwnd")

    def _helper_path(self) -> str:
        return ensure_helper(self.target.get("helper_path"))

    def start(self) -> None:
        launch = self.target.get("launch")
        if launch:
            command = launch if isinstance(launch, list) else [launch]
            image = str(self.target.get("process") or Path(command[0]).name)
            before_pids = self._process_pids(image)
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            startupinfo = None
            if os.name == "nt":
                # Prevent a newly launched app from taking the human's foreground. Foxhound will
                # restore it without activation when the first capture is requested.
                ctypes.windll.user32.LockSetForegroundWindow(1)  # LSFW_LOCK
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 7  # SW_SHOWMINNOACTIVE
                creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            self.owned_app = subprocess.Popen(
                command, cwd=self.target.get("cwd"), creationflags=creationflags,
                startupinfo=startupinfo,
            )
            # Some packaged Windows apps (including current Notepad) immediately hand off to a
            # different process. Preserve an explicit process/title selector in that case; use the
            # launched PID only when the adapter did not provide a stable selector.
            if not any(self.target.get(key) is not None for key in ("process", "title", "hwnd")):
                self.target = {**self.target, "pid": self.owned_app.pid}
            time.sleep(float(self.target.get("launch_wait_s", 1)))
            self.owned_pids = self._process_pids(image) - before_pids
            # Prefer the uniquely created real process. This handles packaged applications whose
            # launcher immediately hands off to another PID without ever owning a window.
            if len(self.owned_pids) == 1:
                self.target = {**self.target, "pid": next(iter(self.owned_pids))}
        if self.external_helper:
            self._request("GET", "/health")
        else:
            if os.name != "nt":
                raise BackendError("Foxhound is currently a Windows backend")
            spec = self._target_spec()
            args = [self._helper_path()]
            key, value = next(iter(spec.items()))
            args += [f"--{key}", str(value)]
            port = self.url.rsplit(":", 1)[-1]
            args += ["--port", port]
            self.process = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                try:
                    self._request("GET", "/health")
                    break
                except BackendError:
                    time.sleep(0.1)
            else:
                raise BackendError("foxhound-helper did not become ready")
        self._request("POST", "/target", json=self._target_spec())
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            health = self._request("GET", "/health").json()
            if health.get("target"):
                return
            time.sleep(0.2)
        raise BackendError(f"Foxhound found no window for {self._target_spec()} within {self.timeout:g}s")

    def close(self) -> None:
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.owned_app and self.owned_app.poll() is None:
            self.owned_app.terminate()
            try:
                self.owned_app.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.owned_app.kill()
        for pid in self.owned_pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health").json()

    def windows(self) -> list[dict[str, Any]]:
        return self._request("GET", "/windows").json()

    def screenshot(self) -> bytes:
        return self._request("GET", "/screenshot").content

    def act(self, action: dict[str, Any]) -> dict[str, Any]:
        op = action["op"]
        if op == "click":
            body = {k: action[k] for k in ("x", "y", "button", "clicks") if k in action}
            return self._request("POST", "/click", json=body).json()
        if op == "key":
            if action.get("sequence"):
                replies = []
                keys = action["keys"] if isinstance(action["keys"], list) else [action["keys"]]
                for key in keys:
                    replies.append(self._request("POST", "/key", json={"keys": key}).json())
                    time.sleep(float(action.get("interval", 0.08)))
                return {"ok": True, "sequence": replies}
            return self._request("POST", "/key", json={"keys": action["keys"]}).json()
        if op == "type":
            return self._request("POST", "/type", json={"text": action["text"], "interval": action.get("interval", 0.01)}).json()
        if op == "scroll":
            body = {k: action[k] for k in ("amount", "x", "y", "horizontal") if k in action}
            return self._request("POST", "/scroll", json=body).json()
        if op == "wait":
            time.sleep(float(action.get("seconds", 1)))
            return {"ok": True}
        raise BackendError(f"backend cannot perform {op!r}")
