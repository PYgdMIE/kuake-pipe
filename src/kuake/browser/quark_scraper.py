"""Quark Pan: login wait + enumerate /我的备份/ subdirs."""
from __future__ import annotations

from kuake.browser.selectors import (
    QUARK_LOGIN_URL, QUARK_BACKUP_URL, QUARK_LOGGED_IN,
    QUARK_BACKUP_FOLDER, try_locators,
)
from kuake.errors import ScraperFailed
from kuake.progress import info, ok


def wait_login(page, timeout_seconds: int = 180) -> None:
    info("打开夸克网盘,请在浏览器里扫码登录...")
    page.goto(QUARK_LOGIN_URL)
    loc = try_locators(page, QUARK_LOGGED_IN, timeout=timeout_seconds * 1000)
    if loc is None:
        raise ScraperFailed("Quark login timeout — no logged-in indicator")
    ok("夸克网盘已登录")


def list_backup_folders(page) -> list[str]:
    """Return display names under /我的备份/."""
    page.goto(QUARK_BACKUP_URL)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    names: list[str] = []
    for strategy in QUARK_BACKUP_FOLDER.strategies:
        try:
            count = page.locator(strategy).count()
            if count > 0:
                for i in range(count):
                    text = page.locator(strategy).nth(i).inner_text().split("\n")[0].strip()
                    if text and text not in names:
                        names.append(text)
                break
        except Exception:
            continue
    if not names:
        raise ScraperFailed("No /我的备份/ subfolders detected")
    return names
