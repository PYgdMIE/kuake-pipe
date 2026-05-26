"""List remote tasks under /root/autodl-tmp/ with size."""
from __future__ import annotations

from kuake.config import read_config, read_credentials
from kuake.progress import console, info
from kuake.ssh_exec import SshExec


def run() -> None:
    cfg = read_config()
    cred = read_credentials()
    info(f"远端目录 {cfg.remote_tmp_dir}/:")
    with SshExec(
        host=cfg.host, port=cfg.port, user=cfg.user,
        password=cred.ssh_password if cfg.auth_mode == "password" else None,
        key_path=cred.ssh_key_path if cfg.auth_mode == "key" else None,
    ) as s:
        _, listing, _ = s.run(
            f"ls -la {cfg.remote_tmp_dir} 2>/dev/null && echo --- && "
            f"du -sh {cfg.remote_tmp_dir}/* 2>/dev/null | head -50",
            check=False,
        )
    console.print(listing)
