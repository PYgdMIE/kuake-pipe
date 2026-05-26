"""Remove a task directory remotely + local zip (从 v0.4 staging dir)."""
from __future__ import annotations

import re
from pathlib import Path

from rich.prompt import Confirm

from kuake.config import config_paths, read_config, read_credentials
from kuake.errors import UserInputError
from kuake.progress import ok, warn
from kuake.ssh_exec import SshExec

TASK_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def run(task: str, *, assume_yes: bool = False) -> None:
    if not TASK_RE.match(task):
        raise UserInputError(f"Invalid task name: {task!r}")

    cfg = read_config()
    cred = read_credentials()
    if not assume_yes and not Confirm.ask(
        f"将删除远端 {cfg.remote_tmp_dir}/{task}/ 和本地 zip,确认?",
        default=False,
    ):
        warn("已取消")
        return

    # remote
    with SshExec(
        host=cfg.host, port=cfg.port, user=cfg.user,
        password=cred.ssh_password if cfg.auth_mode == "password" else None,
        key_path=cred.ssh_key_path if cfg.auth_mode == "key" else None,
    ) as s:
        s.run(
            f"rm -rf {cfg.remote_tmp_dir}/{task} "
            f"{cfg.remote_tmp_dir}/{task}.zip",
            check=False,
        )
    ok(f"远端已删除 {cfg.remote_tmp_dir}/{task}/")

    # local zip — v0.4 staging dir;旧 0.3 兼容:也清 local_backup_dir 里的
    candidates = [config_paths().home / "staging" / f"{task}.zip"]
    if cfg.local_backup_dir:
        candidates.append(Path(cfg.local_backup_dir) / f"{task}.zip")
    for local_zip in candidates:
        if local_zip.exists():
            try:
                local_zip.unlink()
                ok(f"本地已删除 {local_zip}")
            except OSError as e:
                warn(f"本地 zip 删除失败: {e}")
