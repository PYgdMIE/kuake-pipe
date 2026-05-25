"""Playwright session lifecycle + storage_state IO."""
from __future__ import annotations
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from kuake.config import config_paths


@contextmanager
def launch_browser(headless: bool = False, storage_state: Optional[Path] = None) -> Iterator:
    """Launch Chromium and yield (browser_context, playwright_instance).
    Caller closes context. Loads storage_state if provided and exists.
    Grants clipboard read/write so the scraper can pull SSH info from copy icons."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
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
