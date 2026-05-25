"""Platform-specific guards: Linux early exit; Windows/macOS ACL enforcement."""
from __future__ import annotations
import getpass
import os
import subprocess
import sys
from pathlib import Path

from kuake.errors import PlatformUnsupported


def ensure_supported() -> None:
    """Call at CLI entry. Raises if platform unsupported."""
    if sys.platform not in ("win32", "darwin"):
        raise PlatformUnsupported(
            f"Unsupported platform: {sys.platform}. Only Windows and macOS are supported."
        )


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
