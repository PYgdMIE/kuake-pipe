"""Post-init smoke test: write tiny file to local backup dir, poll cloud for ≤60s."""
from __future__ import annotations
import time
import zipfile
from datetime import datetime
from pathlib import Path

from kuake.panel_api import PanelClient
from kuake.progress import info, ok, warn, err


def run_smoke_test(
    local_backup_dir: Path,
    cloud_backup_path: str,
    panel: PanelClient,
    timeout: int = 60,
) -> bool:
    """Write 1KB test zip, poll cloud. Returns True on success.
    On failure, prints detailed diagnostic per spec §10.A."""
    local_backup_dir = Path(local_backup_dir)
    local_backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"kuake_smoke_{stamp}"
    local_zip = local_backup_dir / f"{name}.zip"

    info(f"Smoke test: 写入 {local_zip.name} → 等待夸克客户端同步 (≤{timeout}s)")
    with zipfile.ZipFile(local_zip, "w") as zf:
        zf.writestr("smoke.txt", "x" * 1024)

    cloud_target = cloud_backup_path.rstrip("/") + f"/{local_zip.name}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            item = panel.find_by_path(cloud_target)
            if item:
                ok(f"夸克客户端同步链路畅通 (云端可见 {item.get('size','?')} bytes)")
                try:
                    local_zip.unlink(missing_ok=True)
                except OSError:
                    pass
                return True
        except Exception:
            pass
        time.sleep(5)

    _diagnose_smoke_failure(local_zip)
    return False


def _diagnose_smoke_failure(local_zip: Path):
    err("夸克客户端同步链路异常")
    if local_zip.exists():
        warn(f"本地 {local_zip} 仍在 — 夸克客户端可能未运行,或未监听该目录")
        warn(f"操作: 打开夸克 PC 客户端,确认「备份」功能开启,目标目录为 {local_zip.parent}")
    else:
        warn(f"本地 {local_zip} 已被取走但云端不可见 — 客户端可能未配置该目录为备份")
        warn("操作: 在夸克客户端「备份」设置里添加该目录")
