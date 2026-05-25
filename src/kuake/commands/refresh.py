"""Force re-acquire AutoPanel session_token via sign_in API.

Pure HTTP (no browser) — relies on saved standalone_password_sha1.
If sha1 is missing or sign_in fails, raises SessionDead so user runs `kuake init`.
"""
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
from kuake.proxy import requests_proxies


def run(headless: bool = True) -> None:
    paths = config_paths()
    try:
        lock_ctx = FileLock(paths.lock_file)
    except LockBusy as e:
        raise ConcurrencyLock() from e

    with lock_ctx:
        cfg = read_config()
        cred = read_credentials()

        if not cfg.panel_base or not cred.panel_autodl_token:
            raise SessionDead("No AutoPanel URL or JupyterLab token configured")
        if not cred.standalone_password_sha1:
            raise SessionDead(
                "standalone_password_sha1 missing — please run `kuake init` again"
            )

        from kuake.panel_api import PanelClient
        info("用保存的密码哈希重新登录 AutoPanel...")
        panel = PanelClient(
            base=cfg.panel_base,
            authorization="null",
            autodl_token=cred.panel_autodl_token,
            fs_id=cfg.fs_id,
            proxies=requests_proxies(),
        )
        try:
            new_token = panel.sign_in(cred.standalone_password_sha1)
        except Exception as e:
            raise SessionDead(f"AutoPanel sign_in failed: {e}") from e

        new_cred = Credentials(
            ssh_password=cred.ssh_password,
            ssh_key_path=cred.ssh_key_path,
            panel_authorization=new_token,
            panel_autodl_token=cred.panel_autodl_token,
            expires_estimate=(datetime.now() + timedelta(days=30)).isoformat(timespec="seconds"),
            standalone_password_sha1=cred.standalone_password_sha1,
            quark_cookie=cred.quark_cookie,
        )
        write_credentials(new_cred)

        new_cfg = Config(
            **{**asdict(cfg), "last_refresh": datetime.now().isoformat(timespec="seconds")}
        )
        write_config(new_cfg)
        ok(f"Panel session 已刷新 (token len={len(new_token)})")
