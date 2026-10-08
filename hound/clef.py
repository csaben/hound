from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import requests

from .errors import HoundError
from .util import user_root

DEFAULT_PORT = 8791  # not Wrangler's 8787, so other `wrangler dev` sessions do not collide
DEFAULT_URL = f"http://127.0.0.1:{DEFAULT_PORT}/v1/systemone"
WRANGLER = "wrangler@4.148.0"
PROXY_FILES = ("worker.mjs", "wrangler.jsonc")


def proxy_running(url: str = DEFAULT_URL) -> bool:
    """Return whether Hound's local CLEF proxy answers at ``url``."""
    try:
        response = requests.get(url, timeout=0.5)
        return response.status_code == 405 and response.json().get("error") == "post_required"
    except (requests.RequestException, ValueError):
        return False


def _npx() -> str:
    npx = shutil.which("npx")
    if not npx:
        raise HoundError(
            "CLEF's local proxy needs Node.js 20 or newer for Cloudflare Wrangler; "
            "install it (for example `winget install OpenJS.NodeJS.LTS`) and rerun `hound clef serve`"
        )
    return npx


def _prepare() -> Path:
    target = user_root() / "clef-proxy"
    target.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_name("clef_proxy")
    for name in PROXY_FILES:
        shutil.copyfile(source / name, target / name)
    return target


def serve(port: int = DEFAULT_PORT) -> int:
    """Sign in to Cloudflare if needed, then run the local-only CLEF proxy in the foreground."""
    url = f"http://127.0.0.1:{port}/v1/systemone"
    if proxy_running(url):
        print(f"CLEF proxy is already running at {url}.", flush=True)
        return 0
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise HoundError(f"port {port} is already in use; choose another with `hound clef serve --port N`")
    npx = _npx()
    wrangler = os.environ.get("HOUND_WRANGLER", WRANGLER)
    directory = _prepare()
    whoami = subprocess.run(
        [npx, "--yes", wrangler, "whoami"], cwd=directory, capture_output=True, encoding="utf-8", errors="replace"
    )
    if whoami.returncode != 0 or "not authenticated" in (whoami.stdout + whoami.stderr).lower():
        print("Opening a browser to sign in to Cloudflare (Workers AI runs on your account)...", flush=True)
        if subprocess.call([npx, "--yes", wrangler, "login"], cwd=directory) != 0:
            raise HoundError("Cloudflare sign-in did not complete; rerun `hound clef serve`")
    print(f"CLEF proxy starting at {url}; keep this terminal open and use `--driver clef`.", flush=True)
    if port != DEFAULT_PORT:
        print(f"Set CLEF_URL={url} in the shell that runs Hound.", flush=True)
    return subprocess.call(
        [npx, "--yes", wrangler, "dev", "--config", "wrangler.jsonc", "--ip", "127.0.0.1", "--port", str(port)],
        cwd=directory,
    )
