"""Clear ~/.kuake/ with confirmation."""
from __future__ import annotations

import shutil

from kuake.config import config_paths
from kuake.progress import info, ok, warn


def run(keep_credentials: bool = False) -> None:
    paths = config_paths()
    if not paths.home.exists():
        info("~/.kuake/ 不存在,无需清理")
        return

    ans = input(f"确认清空 {paths.home} ? [y/N]: ").strip().lower()
    if ans != "y":
        warn("已取消")
        return

    if keep_credentials and paths.credentials_file.exists():
        backup = paths.credentials_file.read_bytes()
        shutil.rmtree(paths.home)
        paths.home.mkdir(parents=True, exist_ok=True)
        paths.credentials_file.write_bytes(backup)
        ok(f"已清空(保留 credentials.toml): {paths.home}")
    else:
        shutil.rmtree(paths.home)
        ok(f"已清空: {paths.home}")
