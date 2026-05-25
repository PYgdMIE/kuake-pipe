"""Full-stack health check."""
from __future__ import annotations
import os
import sys
from pathlib import Path

import requests

from kuake.config import config_paths, read_config, read_credentials
from kuake.errors import KuakeError
from kuake.progress import ok, warn, err, console
from kuake.proxy import requests_proxies


def run() -> None:
    issues = 0
    warnings = 0

    paths = config_paths()

    # 1. config exists
    if paths.config_file.exists() and paths.credentials_file.exists():
        ok("[1/12] 配置文件存在")
    else:
        err(f"[1/12] 配置文件缺失: {paths.config_file} / {paths.credentials_file}")
        err("  → 运行 `kuake init`")
        sys.exit(2)

    # 2. parseable
    try:
        cfg = read_config()
        cred = read_credentials()
        ok("[2/12] 配置可解析")
    except KuakeError as e:
        err(f"[2/12] 配置损坏: {e}")
        sys.exit(2)

    # 3. local backup dir writable
    local = Path(cfg.local_backup_dir)
    if local.exists() and os.access(local, os.W_OK):
        ok(f"[3/12] 本地备份目录可写: {local}")
    else:
        err(f"[3/12] 本地备份目录不可写: {local}")
        issues += 1

    # 4. Quark reachable
    proxies = requests_proxies()
    try:
        r = requests.head("https://pan.quark.cn", timeout=5, proxies=proxies)
        ok(f"[4/12] 夸克网盘可达 ({r.status_code})")
    except Exception as e:
        err(f"[4/12] 夸克网盘不可达: {e}")
        issues += 1

    # 5. AutoPanel reachable
    try:
        r = requests.head(cfg.panel_base, timeout=5, proxies=proxies)
        ok(f"[5/12] AutoPanel 可达 ({r.status_code})")
    except Exception as e:
        err(f"[5/12] AutoPanel 不可达: {e}")
        issues += 1

    # 6. Panel token valid
    from kuake.panel_api import PanelClient
    try:
        panel = PanelClient(
            base=cfg.panel_base,
            authorization=cred.panel_authorization,
            autodl_token=cred.panel_autodl_token,
            fs_id=cfg.fs_id,
            proxies=proxies,
        )
        panel.workdir()
        ok("[6/12] AutoPanel token 有效")
        # also verify Quark netdisk binding
        try:
            disks = panel.netdisk_list()
            if disks:
                names = ", ".join(d.get("type", "?") for d in disks)
                ok(f"        Quark 网盘已绑定 ({names})")
            else:
                warn("        AutoPanel 上未绑定任何网盘 — 跑 `kuake init` 重新绑定")
                warnings += 1
        except Exception as e:
            warn(f"        无法查询网盘列表: {e}")
            warnings += 1
    except Exception as e:
        warn(f"[6/12] AutoPanel token 可能过期: {e}")
        warnings += 1

    # 7-9. SSH tests
    from kuake.ssh_exec import SshExec
    ssh_kwargs = dict(
        host=cfg.host, port=cfg.port, user=cfg.user,
        password=cred.ssh_password if cfg.auth_mode == "password" else None,
        key_path=cred.ssh_key_path if cfg.auth_mode == "key" else None,
        timeout=10,
    )
    try:
        with SshExec(**ssh_kwargs) as s:
            _, who, _ = s.run("whoami")
        ok(f"[7/12] SSH 可达 (whoami={who.strip()})")

        with SshExec(**ssh_kwargs) as s:
            _, df, _ = s.run(
                f"df -h {cfg.remote_tmp_dir} 2>/dev/null || df -h /root",
                check=False,
            )
        last_line = df.strip().splitlines()[-1] if df.strip() else "unknown"
        ok(f"[8/12] 服务器磁盘: {last_line}")

        with SshExec(**ssh_kwargs) as s:
            code, _, _ = s.run("which unzip", check=False)
        if code == 0:
            ok("[9/12] 服务器有 unzip")
        else:
            warn("[9/12] 服务器无 unzip,将用 apt install 或 python3 zipfile 兜底")
            warnings += 1
    except Exception as e:
        err(f"[7-9/12] SSH 失败: {e}")
        issues += 1

    # 10. Chromium presence
    from kuake.browser.installer import chromium_installed
    if chromium_installed():
        ok("[10/12] Playwright Chromium 已安装")
    else:
        warn("[10/12] Chromium 未安装,init/refresh 时会自动装")
        warnings += 1

    # 11. storage_state
    if paths.storage_state.exists() and paths.storage_state.stat().st_size > 100:
        ok(f"[11/12] storage_state 存在 ({paths.storage_state.stat().st_size} bytes)")
    else:
        warn("[11/12] storage_state 缺失或太小,refresh 会失败,需要 `kuake init` 重登")
        warnings += 1

    # 12. lock free
    from kuake.concurrency import FileLock, LockBusy
    try:
        with FileLock(paths.lock_file):
            pass
        ok("[12/12] 锁文件未被占用")
    except LockBusy:
        warn("[12/12] 锁文件被占用 (另一 kuake 进程在跑?)")
        warnings += 1

    console.print()
    if issues:
        err(f"自检发现 {issues} 个错误, {warnings} 个警告")
        sys.exit(2)
    elif warnings:
        warn(f"自检通过但有 {warnings} 个警告")
        sys.exit(1)
    else:
        ok("自检全部通过")
