"""AutoDL instance lifecycle actions via headless browser + saved storage_state."""
from __future__ import annotations

import time

from kuake.browser.selectors import (
    AUTODL_CONFIRM_BUTTON,
    AUTODL_CONSOLE_URL,
    AUTODL_INSTANCE_ROW,
    AUTODL_INSTANCE_STATUS,
    AUTODL_POWER_OFF_BUTTON,
    AUTODL_POWER_ON_BUTTON,
    try_locators,
)
from kuake.errors import ScraperFailed
from kuake.progress import info, ok, warn


def list_full(page) -> list[dict]:
    """Return all instances with index, label, and best-effort status string."""
    page.goto(AUTODL_CONSOLE_URL, wait_until="domcontentloaded", timeout=60000)
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
                    label = loc.inner_text()[:200]
                    status = _extract_status(loc) or _infer_status_from_label(label)
                    rows.append({
                        "index": i,
                        "selector": strategy,
                        "label": label,
                        "status": status,
                    })
                break
        except Exception:
            continue

    if not rows:
        raise ScraperFailed("No AutoDL instances detected — page DOM may have changed")
    return rows


def _extract_status(row_locator) -> str | None:
    """Try to read status from within a row locator."""
    for strategy in AUTODL_INSTANCE_STATUS.strategies:
        try:
            txt = row_locator.locator(strategy).first.inner_text(timeout=1000)
            if txt:
                return txt.strip()[:30]
        except Exception:
            continue
    return None


def _infer_status_from_label(label: str) -> str:
    """Fallback: scan label text for known status keywords."""
    keywords = ["运行中", "已开机", "关机中", "已关机", "开机中", "Running", "Stopped"]
    for kw in keywords:
        if kw in label:
            return kw
    return "unknown"


def power_action(page, row_index: int, row_selector: str, action: str,
                 wait_seconds: int = 30) -> str:
    """Click power on/off button on the given row. action ∈ {'start', 'stop'}.
    Returns the new status string after wait_seconds (best-effort)."""
    if action not in ("start", "stop"):
        raise ValueError(f"Invalid action: {action!r}")

    row = page.locator(row_selector).nth(row_index)
    btn_set = AUTODL_POWER_ON_BUTTON if action == "start" else AUTODL_POWER_OFF_BUTTON

    clicked = False
    for strategy in btn_set.strategies:
        try:
            btn = row.locator(strategy).first
            btn.wait_for(state="visible", timeout=3000)
            btn.click()
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        # Try clicking the row first, then look on the detail page
        row.click()
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        for strategy in btn_set.strategies:
            try:
                btn = page.locator(strategy).first
                btn.wait_for(state="visible", timeout=3000)
                btn.click()
                clicked = True
                break
            except Exception:
                continue
    if not clicked:
        raise ScraperFailed(f"Cannot find {action} button on instance row")

    info(f"已点击 {action} 按钮,等待状态变化...")

    # Handle confirmation dialog if it pops up
    confirm = try_locators(page, AUTODL_CONFIRM_BUTTON, timeout=3000)
    if confirm:
        try:
            confirm.click()
        except Exception:
            pass

    # Wait for status to settle
    deadline = time.time() + wait_seconds
    last_status = "unknown"
    while time.time() < deadline:
        try:
            page.reload(wait_until="networkidle", timeout=10000)
        except Exception:
            pass
        try:
            rows = list_full(page)
            if row_index < len(rows):
                last_status = rows[row_index]["status"]
                target_keywords = (
                    ("运行", "已开", "Running") if action == "start"
                    else ("已关", "Stopped")
                )
                if any(k in last_status for k in target_keywords):
                    ok(f"实例状态: {last_status}")
                    return last_status
        except Exception:
            pass
        time.sleep(3)

    warn(f"等待超时,最后看到状态: {last_status}")
    return last_status
