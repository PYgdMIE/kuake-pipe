"""Stop an AutoDL instance by number from `kuake instances`."""
from __future__ import annotations

from rich.prompt import Confirm

from kuake.commands.start import _resolve_target
from kuake.concurrency import FileLock, LockBusy
from kuake.config import config_paths
from kuake.errors import ConcurrencyLock, ConfigMissing
from kuake.progress import info, ok, warn


def run(target: str, yes: bool = False) -> None:
    paths = config_paths()
    if not paths.storage_state.exists():
        raise ConfigMissing(
            f"storage_state missing: {paths.storage_state}; run `kuake init` first"
        )

    try:
        lock_ctx = FileLock(paths.lock_file)
    except LockBusy as e:
        raise ConcurrencyLock() from e

    with lock_ctx:
        from kuake.browser import autodl_actions
        from kuake.browser.session import launch_browser

        info("启动 headless 浏览器...")
        with launch_browser(headless=True, storage_state=paths.storage_state) as (ctx, _p):
            page = ctx.new_page()
            rows = autodl_actions.list_full(page)

            idx = _resolve_target(target, rows)
            row = rows[idx]
            info(f"  目标实例 [{idx + 1}]: {row['label'].splitlines()[0][:80]}")
            info(f"  当前状态: {row['status']}")

            if not yes:
                if not Confirm.ask("确认关机?", default=False):
                    warn("已取消")
                    return

            status = autodl_actions.power_action(
                page, idx, row["selector"], action="stop"
            )
            ok(f"关机完成: {status}")
