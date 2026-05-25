"""Playwright session lifecycle + storage_state IO."""
from __future__ import annotations
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from kuake.config import config_paths


def system_chrome_user_data_dir() -> Optional[Path]:
    """Return the path to the user's normal Chrome profile, if it exists.
    Useful for `--use-system-chrome` to reuse already-logged-in sessions.

    NOTE: Chrome must be CLOSED before Playwright can use this profile."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    else:
        return None
    if base.exists() and (base / "Default").exists():
        return base
    return None


@contextmanager
def launch_browser(
    headless: bool = False,
    storage_state: Optional[Path] = None,
    use_system_chrome: bool = False,
) -> Iterator:
    """Launch Chromium and yield (browser_context, playwright_instance).
    - Default: isolated Chromium with our own storage_state.
    - use_system_chrome=True: launch with user's actual Chrome profile (Chrome
      must be CLOSED first, or the profile is locked).

    Loads storage_state if provided and exists (only in default mode).
    Grants clipboard read/write so the scraper can pull SSH info from copy icons."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        if use_system_chrome:
            user_data = system_chrome_user_data_dir()
            if user_data is None:
                raise RuntimeError("System Chrome profile not found")
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(user_data),
                headless=headless,
                channel="chrome",
            )
            try:
                context.grant_permissions(["clipboard-read", "clipboard-write"])
            except Exception:
                pass
            try:
                yield context, p
            finally:
                try:
                    context.close()
                except Exception:
                    pass
        else:
            browser = p.chromium.launch(headless=headless)
            ctx_kwargs = {}
            if storage_state and Path(storage_state).exists():
                ctx_kwargs["storage_state"] = str(storage_state)
            context = browser.new_context(**ctx_kwargs)
            try:
                context.grant_permissions(["clipboard-read", "clipboard-write"])
            except Exception:
                pass
            try:
                yield context, p
            finally:
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass


def save_storage_state(context, path: Optional[Path] = None) -> Path:
    """Atomic write storage_state.json. Default path: ~/.kuake/state/storage_state.json"""
    if path is None:
        path = config_paths().storage_state
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    state = context.storage_state()
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path
