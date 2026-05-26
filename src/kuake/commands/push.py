"""Main pipeline: pack → direct upload to Quark cloud → trigger AutoPanel download → server unzip.

v0.4+: Stage 2 改用 Quark Cloud API 直接上传 (kuake.quark_uploader),
不再依赖夸克 PC 客户端「备份」功能。Linux/headless 也能跑。
"""
from __future__ import annotations

import re
from pathlib import Path

from kuake.concurrency import FileLock, LockBusy
from kuake.config import (
    Config,
    Credentials,
    config_paths,
    read_config,
    read_credentials,
)
from kuake.errors import (
    CloudTimeout,
    ConcurrencyLock,
    UserInputError,
)
from kuake.pack import make_zip, md5sum
from kuake.panel_api import PanelClient
from kuake.progress import console, info, ok, stage
from kuake.proxy import requests_proxies
from kuake.quark_uploader import QuarkUploader
from kuake.ssh_exec import SshExec

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
        with FileLock(paths.lock_file):
            _run_with_lock(task, src_path, paths, no_unzip, keep_zip)
    except LockBusy as e:
        raise ConcurrencyLock() from e


def _run_with_lock(task: str, src_path: Path, paths, no_unzip: bool, keep_zip: bool):
    cfg = read_config()
    cred = read_credentials()

    staging = paths.home / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    zip_path = staging / f"{task}.zip"

    # Stage 1: pack
    info(f"[1/4] 打包 {src_path} → {zip_path}")
    with stage("Zipping"):
        make_zip(src_path, zip_path)
    size = zip_path.stat().st_size
    digest = md5sum(zip_path)
    ok(f"  size={size:,}  md5={digest}")

    _stages_2_to_4(task, zip_path, size, cfg, cred, no_unzip, keep_zip)


def run_existing_zip(task: str) -> None:
    """retry entry point: 如果 KUAKE_HOME/staging/<task>.zip 存在,跳过打包直接走 2-4。"""
    paths = config_paths()
    try:
        with FileLock(paths.lock_file):
            _retry_with_lock(task, paths)
    except LockBusy as e:
        raise ConcurrencyLock() from e


def _retry_with_lock(task: str, paths):
    cfg = read_config()
    cred = read_credentials()
    zip_path = paths.home / "staging" / f"{task}.zip"
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

    # Stage 2: 直接上传到 Quark cloud (走 cookie 鉴权的 HTTP API)
    cloud_target = cfg.cloud_backup_path.rstrip("/") + f"/{task}.zip"
    info(f"[2/4] 上传到夸克网盘 → {cloud_target}")
    uploader = QuarkUploader(cookie=cred.quark_cookie)
    target_folder_fid = uploader.resolve_or_create_folder(cfg.cloud_backup_path)

    def _on_progress(done: int, total: int, stage_label: str):
        if stage_label.startswith("parts"):
            pct = (done / total * 100) if total else 0
            info(f"  上传中 {stage_label} {done:,}/{total:,} ({pct:.0f}%)")

    with stage("Uploading to Quark"):
        result = uploader.upload(zip_path, target_folder_fid,
                                 on_progress=_on_progress)
    ok(f"  上传完成 fid={result.fid} size={result.size:,} md5={result.md5}")

    # 在 panel API 视角下找到该文件,拿 file_id 给 AutoPanel 触发下载
    item = panel.find_by_path(cloud_target)
    if not item:
        raise CloudTimeout(
            f"上传成功但 AutoPanel 看不到 {cloud_target} — 可能 AutoPanel 缓存滞后,稍后重试"
        )

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
