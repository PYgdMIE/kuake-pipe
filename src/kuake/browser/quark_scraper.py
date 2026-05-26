"""Quark Pan: login wait + enumerate /我的备份/ subdirs."""
from __future__ import annotations

from kuake.browser.selectors import (
    QUARK_BACKUP_FOLDER,
    QUARK_BACKUP_URL,
    QUARK_LOGGED_IN,
    QUARK_LOGIN_URL,
    try_locators,
)
from kuake.errors import ScraperFailed
from kuake.progress import info, ok


def wait_login(page, timeout_seconds: int = 180) -> None:
    info("打开夸克网盘,请在浏览器里扫码登录...")
    page.goto(QUARK_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    loc = try_locators(page, QUARK_LOGGED_IN, timeout=timeout_seconds * 1000)
    if loc is None:
        raise ScraperFailed("Quark login timeout — no logged-in indicator")
    ok("夸克网盘已登录")


def list_backup_folders(page) -> list[str]:
    """Return display names under /我的备份/."""
    page.goto(QUARK_BACKUP_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    # Give SPA time to render the folder list
    page.wait_for_timeout(3000)

    names: list[str] = []
    # Try harder: look for text starting with "来自" (typical PC backup folder prefix)
    extra_strategies = [
        "text=/^来自/",                      # "来自:xxx 电脑备份"
        "[class*='file-list-item']",
        "[class*='list-item']",
        "[class*='item-name']",
        "[class*='ant-list-item']",
        ".file-name",
    ]
    all_strategies = list(QUARK_BACKUP_FOLDER.strategies) + extra_strategies
    for strategy in all_strategies:
        try:
            count = page.locator(strategy).count()
            if count > 0:
                for i in range(count):
                    text = page.locator(strategy).nth(i).inner_text().split("\n")[0].strip()
                    if text and text not in names:
                        names.append(text)
                if names:
                    break
        except Exception:
            continue
    if not names:
        # Dump some context to help debugging on the caller side
        try:
            body = page.locator("body").inner_text(timeout=2000)[:400]
            raise ScraperFailed(
                f"No /我的备份/ subfolders detected. URL={page.url} BODY_SAMPLE={body!r}"
            )
        except Exception:
            raise ScraperFailed("No /我的备份/ subfolders detected (and could not read body)")
    return names
