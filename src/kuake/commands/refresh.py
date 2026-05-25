"""Force re-fetch panel auth using saved storage_state (headless if possible)."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timedelta

from kuake.config import (
    config_paths, read_config, read_credentials,
    write_credentials, write_config, Config, Credentials,
)
from kuake.concurrency import FileLock, LockBusy
from kuake.errors import ConcurrencyLock, SessionDead
from kuake.progress import info, ok


def run(headless: bool = True) -> None:
    paths = config_paths()
    try:
        lock_ctx = FileLock(paths.lock_file)
    except LockBusy as e:
        raise ConcurrencyLock() from e

    with lock_ctx:
        cfg = read_config()
        cred = read_credentials()

        if not cfg.panel_base:
            raise SessionDead("No panel URL configured")

        from kuake.browser.session import launch_browser, save_storage_state
        from kuake.browser.panel_scraper import capture_auth

        info(f"启动 {'headless' if headless else 'headed'} 浏览器,使用已保存的登录态...")
        try:
            with launch_browser(headless=headless, storage_state=paths.storage_state) as (ctx, _p):
                page = ctx.new_page()
                auth = capture_auth(page, cfg.panel_base)
                save_storage_state(ctx, paths.storage_state)
        except Exception as e:
            raise SessionDead(f"Refresh failed (session may be dead): {e}") from e

        new_cred = Credentials(
            ssh_password=cred.ssh_password,
            ssh_key_path=cred.ssh_key_path,
            panel_authorization=auth.authorization,
            panel_autodl_token=auth.autodl_token,
            expires_estimate=(datetime.now() + timedelta(days=30)).isoformat(timespec="seconds"),
        )
        write_credentials(new_cred)

        new_cfg = Config(
            **{**asdict(cfg), "last_refresh": datetime.now().isoformat(timespec="seconds")}
        )
        write_config(new_cfg)
        ok("Panel token 已刷新")
