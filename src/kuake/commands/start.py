"""Start an AutoDL instance by number from `kuake instances`."""
from __future__ import annotations

from kuake.concurrency import FileLock, LockBusy
from kuake.config import config_paths
from kuake.errors import ConcurrencyLock, ConfigMissing, UserInputError
from kuake.progress import info, ok


def run(target: str) -> None:
    """target: 1-based index from `kuake instances` or 'default' for first."""
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
            status = autodl_actions.power_action(
                page, idx, row["selector"], action="start"
            )
            ok(f"开机完成: {status}")


def _resolve_target(target: str, rows: list[dict]) -> int:
    if target == "default":
        return 0
    try:
        idx = int(target) - 1
    except ValueError:
        raise UserInputError(
            f"Invalid instance number: {target!r}; run `kuake instances` to see numbers"
        )
    if idx < 0 or idx >= len(rows):
        raise UserInputError(
            f"Instance number {target} out of range (have {len(rows)})"
        )
    return idx
