"""Scrape AutoDL console: login wait, instance list, SSH info, AutoPanel URL."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from kuake.browser.selectors import (
    AUTODL_LOGIN_URL, AUTODL_CONSOLE_URL,
    AUTODL_LOGGED_IN, AUTODL_INSTANCE_ROW,
    AUTODL_INSTANCE_SSH, AUTODL_INSTANCE_PASSWORD,
    AUTODL_AUTOPANEL_LINK, try_locators,
)
from kuake.errors import ScraperFailed
from kuake.progress import info, ok


@dataclass
class InstanceInfo:
    label: str
    ssh_host: str
    ssh_port: int
    ssh_user: str
    ssh_password: str
    autopanel_url: Optional[str]


def wait_login(page, timeout_seconds: int = 180) -> None:
    """Navigate to login page and wait until logged-in indicator appears."""
    info("打开 AutoDL 登录页,请在浏览器里完成扫码/SMS 登录...")
    page.goto(AUTODL_LOGIN_URL)
    loc = try_locators(page, AUTODL_LOGGED_IN, timeout=timeout_seconds * 1000)
    if loc is None:
        raise ScraperFailed(
            f"AutoDL login timeout — no logged-in indicator after {timeout_seconds}s"
        )
    ok("AutoDL 已登录")


def parse_ssh_command(cmd: str) -> tuple[str, int, str]:
    """Parse 'ssh -p 12345 root@host.example' → (host, port, user)."""
    m = re.search(r"ssh\s+-p\s+(\d+)\s+(\w+)@([\w.\-]+)", cmd)
    if not m:
        raise ScraperFailed(f"Cannot parse SSH command: {cmd!r}")
    port, user, host = int(m.group(1)), m.group(2), m.group(3)
    return host, port, user


def list_instances(page) -> list[dict]:
    """Return raw instance metadata. Just identifiers + display text."""
    page.goto(AUTODL_CONSOLE_URL)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    rows: list[dict] = []
    for strategy in AUTODL_INSTANCE_ROW.strategies:
        try:
            count = page.locator(strategy).count()
            if count > 0:
                for i in range(count):
                    loc = page.locator(strategy).nth(i)
                    text = loc.inner_text()[:200]
                    rows.append({"index": i, "selector": strategy, "label": text})
                break
        except Exception:
            continue
    if not rows:
        raise ScraperFailed("No AutoDL instances detected — page DOM may have changed")
    return rows


def extract_instance_details(page, row_index: int, row_selector: str) -> InstanceInfo:
    """Click into instance row, scrape SSH command + password + AutoPanel URL."""
    row = page.locator(row_selector).nth(row_index)
    row.click()
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    ssh_loc = try_locators(page, AUTODL_INSTANCE_SSH, timeout=8000)
    if ssh_loc is None:
        raise ScraperFailed("Cannot locate SSH command in instance detail")
    ssh_text = ssh_loc.inner_text().strip()
    host, port, user = parse_ssh_command(ssh_text)

    pwd_loc = try_locators(page, AUTODL_INSTANCE_PASSWORD, timeout=3000)
    password = pwd_loc.inner_text().strip() if pwd_loc else ""

    autopanel_url: Optional[str] = None
    panel_loc = try_locators(page, AUTODL_AUTOPANEL_LINK, timeout=3000)
    if panel_loc:
        try:
            autopanel_url = panel_loc.get_attribute("href")
        except Exception:
            pass

    return InstanceInfo(
        label=ssh_text[:80],
        ssh_host=host, ssh_port=port, ssh_user=user,
        ssh_password=password,
        autopanel_url=autopanel_url,
    )
