"""Scrape AutoDL console: login wait, instance list, SSH info, AutoPanel URL."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from kuake.browser.selectors import (
    AUTODL_LOGIN_URL, AUTODL_CONSOLE_URL,
    AUTODL_LOGGED_IN, AUTODL_INSTANCE_ROW,
    AUTODL_INSTANCE_SSH, AUTODL_INSTANCE_PASSWORD,
    AUTODL_AUTOPANEL_LINK, AUTODL_QR_TAB,
    AUTODL_WECHAT_FAST_LOGIN, try_locators,
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


def _parse_row_meta(row_text: str) -> dict:
    """Extract name / gpu / status from the multi-line row text."""
    lines = [s.strip() for s in row_text.splitlines() if s.strip()]
    meta = {"name": "", "gpu": "", "status": "未知"}
    if lines:
        meta["name"] = lines[0][:40]  # e.g. "西北B区 / 034机"
    for ln in lines:
        if any(k in ln for k in ("运行中", "已关机", "关机中", "开机中")):
            meta["status"] = ln.strip()[:6]
            break
    for ln in lines:
        if "卡" in ln and ("*" in ln or "x" in ln.lower()):
            meta["gpu"] = ln.strip()[:30]
            break
    return meta


def wait_login(page, timeout_seconds: int = 180) -> None:
    """Navigate to login page and wait until logged-in indicator appears.
    Auto-switches to WeChat QR tab if the page defaults to password mode."""
    info("打开 AutoDL 登录页...")
    page.goto(AUTODL_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

    # Already logged in via saved storage_state?
    quick = try_locators(page, AUTODL_LOGGED_IN, timeout=2000)
    if quick is not None:
        ok("AutoDL 已通过保存的 session 登录")
        return

    # Try to auto-switch to QR tab (best-effort, default to password mode)
    qr_tab = try_locators(page, AUTODL_QR_TAB, timeout=3000)
    if qr_tab is not None:
        try:
            qr_tab.click()
            info("已自动切换到微信扫码模式")
            page.wait_for_timeout(1500)
        except Exception:
            pass
    else:
        info("未找到扫码标签,按当前页面提示登录(密码或手机号)")

    # On /wx-login there's also a "微信快捷登录" button that opens the larger
    # open.weixin.qq.com QR page — click it for a cleaner scan UX.
    fast = try_locators(page, AUTODL_WECHAT_FAST_LOGIN, timeout=2000)
    if fast is not None:
        try:
            fast.click()
            info("已跳转微信官方大 QR 页")
            page.wait_for_timeout(1500)
        except Exception:
            pass

    info("请扫码登录(浏览器右上角的二维码)...")
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
                    text = loc.inner_text()[:300]
                    meta = _parse_row_meta(text)
                    rows.append({
                        "index": i, "selector": strategy, "label": text,
                        "name": meta["name"], "gpu": meta["gpu"], "status": meta["status"],
                        "running": "运行中" in meta["status"],
                    })
                break
        except Exception:
            continue
    if not rows:
        raise ScraperFailed("No AutoDL instances detected — page DOM may have changed")
    return rows


def extract_instance_details(page, row_index: int, row_selector: str) -> InstanceInfo:
    """Extract SSH command + password + AutoPanel URL from the AutoDL instance row.

    The row is an Element UI <tr.el-table__row> with 10 <td> cells:
      cell[0]: 实例ID/名称/区域
      cell[1]: 状态
      ...
      cell[7]: 登录指令 (ssh masked + password masked, with 2 copy icons)
      cell[8]: 操作 (JupyterLab / AutoPanel / 监控 / 自定义服务 buttons)

    Strategy:
      1. Click ssh copy icon → read clipboard → ssh command
      2. Click password copy icon → read clipboard → password
      3. Click AutoPanel button → intercept new-page event → capture URL
    """
    row = page.locator(row_selector).nth(row_index)
    try:
        row.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass

    # Detect stopped/booting instances: they show no SSH info, no AutoPanel button.
    try:
        full_text = row.inner_text(timeout=2000)
        if "已关机" in full_text or "关机中" in full_text:
            raise ScraperFailed(
                "该实例已关机 — 请先到 AutoDL 控制台开机,或选另一个运行中(运行中)的实例"
            )
        if "开机中" in full_text:
            raise ScraperFailed(
                "该实例正在开机中 — 请等 1-2 分钟开机完成后重跑 `kuake init`"
            )
    except ScraperFailed:
        raise
    except Exception:
        pass

    # SSH + password via clipboard
    cell_login = row.locator("td").nth(7)
    icons = cell_login.locator(".icon-fuzhi").all()
    if len(icons) < 2:
        raise ScraperFailed(
            f"Expected 2 copy icons in cell[7], found {len(icons)} — "
            "可能实例未运行,或 AutoDL DOM 改版了"
        )

    try:
        icons[0].click()
        page.wait_for_timeout(600)
        ssh_text = page.evaluate("() => navigator.clipboard.readText()")
    except Exception as e:
        raise ScraperFailed(f"Could not read SSH from clipboard: {e}") from e

    try:
        icons[1].click()
        page.wait_for_timeout(600)
        password = page.evaluate("() => navigator.clipboard.readText()")
    except Exception as e:
        raise ScraperFailed(f"Could not read password from clipboard: {e}") from e

    host, port, user = parse_ssh_command(ssh_text)

    # AutoPanel URL via new-page interception (button opens new tab)
    autopanel_url: Optional[str] = None
    try:
        cell_actions = row.locator("td").nth(8)
        panel_btn = cell_actions.locator("button:has-text('AutoPanel')").first
        ctx = page.context
        with ctx.expect_page(timeout=10000) as new_page_info:
            panel_btn.click()
        new_page = new_page_info.value
        try:
            new_page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        autopanel_url = new_page.url
        try:
            new_page.close()
        except Exception:
            pass
    except Exception:
        pass  # AutoPanel URL is optional; if it fails we ask user to paste

    return InstanceInfo(
        label=ssh_text[:80],
        ssh_host=host, ssh_port=port, ssh_user=user,
        ssh_password=password,
        autopanel_url=autopanel_url,
    )
