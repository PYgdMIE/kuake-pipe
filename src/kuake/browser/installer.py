"""Detect Chromium presence; if absent, install via best-available mirror."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import requests

from kuake.errors import ChromiumMirrorUnreachable
from kuake.progress import info, ok, warn

MIRRORS = [
    "https://npmmirror.com/mirrors/playwright",
    "https://playwright.azureedge.net",
]


def chromium_installed() -> bool:
    """Check Playwright's standard cache for chromium."""
    if sys.platform == "win32":
        cache = Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "ms-playwright"
    elif sys.platform == "darwin":
        cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    else:
        cache = Path.home() / ".cache" / "ms-playwright"
    if not cache.exists():
        return False
    return any(p.name.startswith("chromium") for p in cache.iterdir())


def pick_mirror(timeout: float = 3.0) -> str | None:
    for url in MIRRORS:
        try:
            r = requests.head(url, timeout=timeout, allow_redirects=True)
            if r.status_code < 500:
                return url
        except requests.exceptions.RequestException:
            continue
    return None


def ensure_chromium() -> None:
    """Install chromium if not present. Raises ChromiumMirrorUnreachable if all mirrors fail."""
    if chromium_installed():
        ok("Playwright Chromium 已安装")
        return

    info("未检测到 Playwright Chromium,准备下载...")
    mirror = pick_mirror()
    if mirror is None:
        raise ChromiumMirrorUnreachable("All Playwright mirrors unreachable")

    info(f"使用镜像: {mirror}")
    env = {**os.environ, "PLAYWRIGHT_DOWNLOAD_HOST": mirror}
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        warn(f"Chromium 安装出错: {result.stderr[:500]}")
        raise ChromiumMirrorUnreachable(
            f"playwright install chromium failed (rc={result.returncode})"
        )
    ok("Chromium 安装完成")
