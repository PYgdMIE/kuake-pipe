"""List AutoDL instances with their current power status."""
from __future__ import annotations

from kuake.config import config_paths
from kuake.errors import ConfigMissing
from kuake.progress import info, console


def run() -> None:
    paths = config_paths()
    if not paths.storage_state.exists():
        raise ConfigMissing(
            f"storage_state missing: {paths.storage_state}; run `kuake init` first"
        )

    from kuake.browser.session import launch_browser
    from kuake.browser import autodl_actions

    info("启动 headless 浏览器查询实例列表...")
    with launch_browser(headless=True, storage_state=paths.storage_state) as (ctx, _p):
        page = ctx.new_page()
        rows = autodl_actions.list_full(page)

    console.print("\n[bold]AutoDL 实例:[/bold]")
    for i, r in enumerate(rows, 1):
        first_line = r["label"].splitlines()[0][:80] if r["label"] else ""
        status = r["status"]
        color = "green" if any(k in status for k in ("运行", "已开", "Running")) else "yellow"
        console.print(f"  [{i}] [{color}]{status}[/{color}]  {first_line}")
