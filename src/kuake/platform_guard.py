"""Platform helpers: ACL enforcement on POSIX/Windows.

v0.4 起,不再有平台限制(夸克 PC 客户端依赖已砍掉)。
保留 ensure_supported() 作为占位,以兼容 CLI 入口和测试。
"""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path


def ensure_supported() -> None:
    """No-op since v0.4. Kept for backward compatibility with CLI entrypoint."""
    return None


def harden_file_acl(path: Path) -> None:
    """Set file permissions to owner-only.
    POSIX: chmod 600
    Windows: icacls
    No-op if file does not exist (e.g., not yet written)."""
    path = Path(path)
    if not path.exists():
        return
    if sys.platform == "win32":
        try:
            user = getpass.getuser()
            subprocess.run(
                ["icacls", str(path), "/inheritance:r",
                 "/grant:r", f"{user}:(R,W)"],
                check=False, capture_output=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
