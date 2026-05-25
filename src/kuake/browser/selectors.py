"""Centralized DOM selectors with multi-tier fallback.
Edit this file when AutoDL/Quark UI changes — no other file should hardcode selectors."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SelectorSet:
    """A selector with multiple fallback strategies.
    Strategies tried in order until one matches."""
    name: str
    strategies: tuple[str, ...]


# --- AutoDL ---
AUTODL_LOGIN_URL = "https://www.autodl.com/login"
AUTODL_CONSOLE_URL = "https://www.autodl.com/console/instance/list"

AUTODL_LOGGED_IN = SelectorSet(
    "autodl_logged_in",
    (
        "a[href*='/console']",          # generic console nav link
        "text=控制台",                  # text "console"
        "[class*='user-avatar']",       # avatar class
    ),
)

AUTODL_INSTANCE_ROW = SelectorSet(
    "autodl_instance_row",
    (
        "[class*='instance-item']",
        "[class*='InstanceItem']",
        "tr[data-instance-id]",
        "[data-testid='instance-row']",
    ),
)

AUTODL_INSTANCE_SSH = SelectorSet(
    "autodl_instance_ssh",
    (
        "[class*='ssh-command']",
        "[class*='SshCommand']",
        "text=/ssh.*-p.*root@/",
    ),
)

AUTODL_INSTANCE_PASSWORD = SelectorSet(
    "autodl_instance_password",
    (
        "[class*='ssh-password']",
        "[class*='SshPassword']",
        "[data-testid='ssh-password']",
    ),
)

AUTODL_AUTOPANEL_LINK = SelectorSet(
    "autodl_autopanel_link",
    (
        "a[href*='autopanel']",
        "text=AutoPanel",
        "[class*='autopanel-link']",
    ),
)

# --- Quark ---
QUARK_LOGIN_URL = "https://pan.quark.cn"
QUARK_BACKUP_URL = "https://pan.quark.cn/list#/list/backup"

QUARK_LOGGED_IN = SelectorSet(
    "quark_logged_in",
    (
        "[class*='user-info']",
        "[class*='nav-user']",
        "text=/我的网盘|个人中心/",
    ),
)

QUARK_BACKUP_FOLDER = SelectorSet(
    "quark_backup_folder",
    (
        "[class*='backup-folder']",
        "[class*='folder-item']",
        "[role='listitem']",
    ),
)

# --- AutoPanel page (any URL on AutoPanel) ---
AUTOPANEL_API_PATTERN = "**/autopanel/v1/**"


def try_locators(page, selector_set: SelectorSet, timeout: int = 5000):
    """Try each strategy in order. Return first matching Locator, or None."""
    for strategy in selector_set.strategies:
        try:
            loc = page.locator(strategy).first
            loc.wait_for(state="attached", timeout=timeout)
            return loc
        except Exception:
            continue
    return None
