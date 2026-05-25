"""Main pipeline: pack → wait cloud → trigger download → server unzip."""
from __future__ import annotations
import re
import time
from pathlib import Path

from kuake.config import (
    config_paths, read_config, read_credentials, Config, Credentials,
)
from kuake.concurrency import FileLock, LockBusy
from kuake.errors import (
    ConcurrencyLock, UserInputError, CloudTimeout, AuthExpired,
)
from kuake.pack import make_zip, md5sum
from kuake.panel_api import PanelClient
from kuake.ssh_exec import SshExec
from kuake.progress import info, ok, warn, stage, console
from kuake.proxy import requests_proxies

TASK_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def run(task: str, src: str, no_unzip: bool = False, keep_zip: bool = False) -> None:
    if not TASK_NAME_RE.match(task):
        raise UserInputError(
            f"Invalid task name: {task!r} (use [a-zA-Z0-9_-]+, ≤64 chars)"
        )

    src_path = Path(src).resolve()
    if not src_path.exists():
        raise UserInputError(f"Source not found: {src_path}")

    paths = config_paths()
    try:
        lock_ctx = FileLock(paths.lock_file)
    except LockBusy as e:
        raise ConcurrencyLock() from e

    with lock_ctx:
        cfg = read_config()
        cred = read_credentials()

        zip_path = Path(cfg.local_backup_dir) / f"{task}.zip"

        # Stage 1: pack
        info(f"[1/4] 打包 {src_path} → {zip_path}")
        with stage("Zipping"):
            make_zip(src_path, zip_path)
        size = zip_path.stat().st_size
        digest = md5sum(zip_path)
        ok(f"  size={size:,}  md5={digest}")

        _stages_2_to_4(task, zip_path, size, cfg, cred, no_unzip, keep_zip)


def run_existing_zip(task: str) -> None:
    """retry entry point: assume UPLOAD/<task>.zip exists; run stages 2-4."""
    paths = config_paths()
    try:
        lock_ctx = FileLock(paths.lock_file)
    except LockBusy as e:
        raise ConcurrencyLock() from e

    with lock_ctx:
        cfg = read_config()
        cred = read_credentials()
        zip_path = Path(cfg.local_backup_dir) / f"{task}.zip"
        if not zip_path.exists():
            raise UserInputError(f"No existing zip: {zip_path}")
        size = zip_path.stat().st_size
        info(f"[0] 使用已有 {zip_path} size={size:,}")
        _stages_2_to_4(task, zip_path, size, cfg, cred, no_unzip=False, keep_zip=True)


def _build_panel(cfg: Config, cred: Credentials) -> PanelClient:
    """Build a PanelClient with auto-refresh hook wired."""
    def refresh_cb():
        from kuake.commands import refresh as refresh_cmd
        # push already holds the lock — refresh must not try to re-acquire
        refresh_cmd.run(headless=True, _hold_lock=False)
        new_cred = read_credentials()
        return PanelClient(
            base=cfg.panel_base,
            authorization=new_cred.panel_authorization,
            autodl_token=new_cred.panel_autodl_token,
            fs_id=cfg.fs_id,
            proxies=requests_proxies(),
        )

    return PanelClient(
        base=cfg.panel_base,
        authorization=cred.panel_authorization,
        autodl_token=cred.panel_autodl_token,
        fs_id=cfg.fs_id,
        refresh_callback=refresh_cb,
        proxies=requests_proxies(),
    )


def _stages_2_to_4(
    task: str, zip_path: Path, expected_size: int,
    cfg: Config, cred: Credentials,
    no_unzip: bool, keep_zip: bool,
) -> None:
    panel = _build_panel(cfg, cred)

    # Stage 2: wait cloud
    cloud_target = cfg.cloud_backup_path.rstrip("/") + f"/{task}.zip"
    info(f"[2/4] 等夸克客户端上行 → {cloud_target}")
    deadline = time.time() + 3600
    item = None
    while time.time() < deadline:
        try:
            item = panel.find_by_path(cloud_target)
            if item:
                cur = int(item.get("size", 0))
                if cur >= expected_size:
                    break
                info(f"  云端可见但未传完: {cur:,}/{expected_size:,}")
        except AuthExpired:
            raise
        except Exception as e:
            info(f"  轮询出错 (将重试): {e}")
        time.sleep(8)
    else:
        raise CloudTimeout(f"Cloud sync timeout for {cloud_target}")
    ok(f"  云端可见 size={item.get('size')}")

    # Stage 3: trigger panel download
    info("[3/4] 触发 AutoPanel 下载到服务器")
    panel.trigger_download(item, src_path=cloud_target, dst_path="")
    with stage("Downloading on server"):
        panel.wait_task(f"{task}.zip")
    ok("  服务器下载完成")

    # Stage 4: server unzip
    if no_unzip:
        info("[4/4] 跳过解压 (--no-unzip)")
        ok(f"完成。zip 保留在服务器 {cfg.remote_tmp_dir}/{task}.zip")
        return

    info(f"[4/4] 服务器解压 → {cfg.remote_tmp_dir}/{task}/")
    listing = ""
    with SshExec(
        host=cfg.host, port=cfg.port, user=cfg.user,
        password=cred.ssh_password if cfg.auth_mode == "password" else None,
        key_path=cred.ssh_key_path if cfg.auth_mode == "key" else None,
    ) as ssh:
        src_zip = f"{cfg.remote_tmp_dir}/{task}.zip"
        dest = f"{cfg.remote_tmp_dir}/{task}"
        ssh.run(f"test -f {src_zip}")
        ssh.run(f"mkdir -p {dest}")
        ssh.run(f"mv {src_zip} {dest}/")
        zip_inside = f"{dest}/{task}.zip"
        ssh.unzip_remote(zip_inside, dest)
        _, listing, _ = ssh.run(f"ls -la {dest}", check=False)

    if not keep_zip and zip_path.exists():
        try:
            zip_path.unlink()
        except OSError:
            pass

    ok(f"完成。服务器 {cfg.remote_tmp_dir}/{task}/")
    if listing:
        console.print(f"[dim]{listing.strip()}[/dim]")
