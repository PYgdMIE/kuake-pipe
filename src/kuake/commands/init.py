"""First-run wizard. Drives Playwright through AutoDL + Quark login and configures everything."""
from __future__ import annotations
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

from rich.prompt import Prompt, Confirm

from kuake.config import (
    Config, Credentials, config_paths, write_config, write_credentials,
)
from kuake.concurrency import FileLock, LockBusy
from kuake.errors import ConcurrencyLock, UserInputError, ScraperFailed
from kuake.progress import info, ok, warn, console
from kuake.ssh_exec import SshExec, generate_ed25519_keypair


def _parse_jupyter_token(autopanel_url: str) -> tuple[str, str]:
    """Return (base, jupyter_token) from an AutoPanel URL.
    URL format: https://<host>:8443/?token=jupyter-autodl-container-..."""
    p = urlparse(autopanel_url)
    base = f"{p.scheme}://{p.netloc}"
    q = parse_qs(p.query)
    token = (q.get("token", [""]) or [""])[0]
    if not token:
        raise ScraperFailed(f"AutoPanel URL missing token query param: {autopanel_url!r}")
    return base, token


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _prompt_index(prompt: str, n: int, default: int = 1) -> int:
    """Ask user for 1-based index in [1, n]. Returns 0-based.
    Loops on invalid input; never raises."""
    while True:
        raw = Prompt.ask(prompt, default=str(default))
        try:
            v = int(raw)
        except ValueError:
            warn(f"请输入 1-{n} 之间的数字")
            continue
        if 1 <= v <= n:
            return v - 1
        warn(f"超出范围 1-{n}")


def run(no_smoke: bool = False, ssh_key: bool = False,
        use_system_chrome: bool = False) -> None:
    paths = config_paths()
    paths.home.mkdir(parents=True, exist_ok=True)
    paths.state_dir.mkdir(parents=True, exist_ok=True)

    try:
        lock_ctx = FileLock(paths.lock_file)
    except LockBusy as e:
        raise ConcurrencyLock() from e

    with lock_ctx:
        # 1. ensure chromium
        from kuake.browser.installer import ensure_chromium
        ensure_chromium()

        # 2. browser session + scrapers (lazy import)
        from kuake.browser.session import launch_browser, save_storage_state
        from kuake.browser import autodl_scraper, panel_scraper, quark_scraper

        if use_system_chrome:
            info("启动系统 Chrome (使用你已登录的 profile,Chrome 必须先关闭)...")
        else:
            info("启动浏览器(可见模式)...")
        with launch_browser(
            headless=False,
            storage_state=paths.storage_state,
            use_system_chrome=use_system_chrome,
        ) as (ctx, _p):
            page = ctx.new_page()

            # 3. AutoDL login
            autodl_scraper.wait_login(page)

            # 4. list & pick instance
            rows = autodl_scraper.list_instances(page)
            console.print("\n[bold]检测到 AutoDL 实例:[/bold]")
            for i, r in enumerate(rows, 1):
                console.print(f"  [{i}] {r['label'][:80]}")
            idx = _prompt_index("选择实例", len(rows))
            chosen = rows[idx]

            # 5. extract SSH + AutoPanel URL
            instance = autodl_scraper.extract_instance_details(
                page, idx, chosen["selector"]
            )
            ok(f"  SSH: {instance.ssh_user}@{instance.ssh_host}:{instance.ssh_port}")
            if instance.autopanel_url:
                ok(f"  AutoPanel: {instance.autopanel_url}")

            # 6. auth mode choice
            use_key = ssh_key
            if not use_key:
                use_key = Confirm.ask(
                    "使用 SSH 密钥模式 (推荐)?", default=False
                )

            ssh_password = None
            ssh_key_path = None
            if use_key:
                key_file = paths.home / "id_ed25519"
                priv, pub_str = generate_ed25519_keypair(key_file)
                info(f"  已生成密钥: {priv}")
                if not instance.ssh_password:
                    raise UserInputError(
                        "AutoDL did not provide a password; cannot install pubkey"
                    )
                with SshExec(
                    host=instance.ssh_host, port=instance.ssh_port,
                    user=instance.ssh_user, password=instance.ssh_password,
                ) as s:
                    s.run("mkdir -p ~/.ssh && chmod 700 ~/.ssh")
                    s.run(
                        f"echo {repr(pub_str)} >> ~/.ssh/authorized_keys && "
                        f"chmod 600 ~/.ssh/authorized_keys"
                    )
                ssh_key_path = str(priv)
                ok("  公钥已安装到服务器")
            else:
                ssh_password = instance.ssh_password

            # 7. AutoPanel auth — sign_in with standalone password (no more F12)
            if not instance.autopanel_url:
                instance_url = Prompt.ask("未自动检测到 AutoPanel URL,请粘贴:")
                instance.autopanel_url = instance_url
            panel_base, jupyter_token = _parse_jupyter_token(instance.autopanel_url)
            ok(f"  AutoPanel base: {panel_base}")

            console.print("\n[bold]AutoPanel 独立密码登录[/bold]")
            console.print("[dim]这是你在 AutoDL 控制台「自定义服务」里设的密码（旧文件 ~/.quark/autopanel_pwd.txt 里那个）[/dim]")
            standalone_pwd = Prompt.ask("请输入独立密码（明文）", password=True)
            pwd_sha1 = _sha1(standalone_pwd)

            from kuake.panel_api import PanelClient
            from kuake.proxy import requests_proxies
            panel = PanelClient(
                base=panel_base,
                authorization="null",
                autodl_token=jupyter_token,
                fs_id="quark1",
                proxies=requests_proxies(),
            )
            try:
                session_token = panel.sign_in(pwd_sha1)
                ok(f"  AutoPanel 登录成功(session_token len={len(session_token)})")
            except Exception as e:
                raise UserInputError(f"AutoPanel 登录失败,可能独立密码错: {e}")

            # 8. Quark login (visible browser, may auto-pass via saved session)
            quark_scraper.wait_login(page)

            # 8.1 extract Quark cookie from browser and bind to AutoPanel
            from kuake.browser.quark_cookie import extract_quark_cookie_header
            quark_cookie = extract_quark_cookie_header(ctx)
            if not quark_cookie:
                raise ScraperFailed("Could not extract Quark cookies from browser session")
            info(f"  抓到 Quark cookie ({len(quark_cookie)} chars)")

            existing = panel.netdisk_list()
            if existing:
                ok(f"  AutoPanel 已绑定 {len(existing)} 个网盘,跳过绑定")
            else:
                info("  AutoPanel 上没有网盘,自动绑定 Quark...")
                try:
                    panel.bind_quark(quark_cookie)
                    ok("  Quark 网盘已绑定 AutoPanel")
                except Exception as e:
                    raise UserInputError(f"Quark 绑定失败(cookie 可能过期): {e}")
                # verify
                after = panel.netdisk_list()
                if not after:
                    raise ScraperFailed("绑定后 netdisk_list 仍为空")

            folders = quark_scraper.list_backup_folders(page)
            console.print("\n[bold]检测到夸克备份目录:[/bold]")
            for i, n in enumerate(folders, 1):
                console.print(f"  [{i}] {n}")
            qidx = _prompt_index("选择 PC 备份目录", len(folders))
            pc_folder = folders[qidx]
            subname = Prompt.ask(
                "备份子目录名 (本地夸克客户端备份的目录名)", default="UPLOAD"
            )
            cloud_backup_path = f"/我的备份/{pc_folder}/{subname}"

            # 9. local backup dir
            default_local = str(Path.home() / "Downloads" / subname)
            local_backup_dir = Prompt.ask(
                "本地夸克客户端备份目录", default=default_local
            )
            Path(local_backup_dir).mkdir(parents=True, exist_ok=True)

            # 10. test SSH
            info("测试 SSH 连接...")
            with SshExec(
                host=instance.ssh_host, port=instance.ssh_port,
                user=instance.ssh_user,
                password=ssh_password, key_path=ssh_key_path,
            ) as s:
                result = s.test_connection()
                ok(f"  whoami={result['whoami']}")

            # 11. write config
            cfg = Config(
                host=instance.ssh_host, port=instance.ssh_port,
                user=instance.ssh_user,
                auth_mode="key" if use_key else "password",
                panel_base=panel_base, fs_id="quark1",
                local_backup_dir=local_backup_dir,
                cloud_backup_path=cloud_backup_path,
                remote_tmp_dir="/root/autodl-tmp",
                created_at=datetime.now().isoformat(timespec="seconds"),
                last_refresh=datetime.now().isoformat(timespec="seconds"),
            )
            cred = Credentials(
                ssh_password=ssh_password, ssh_key_path=ssh_key_path,
                panel_authorization=session_token,
                panel_autodl_token=jupyter_token,
                expires_estimate=(datetime.now() + timedelta(days=30)).isoformat(timespec="seconds"),
                standalone_password_sha1=pwd_sha1,
                quark_cookie=quark_cookie,
            )
            write_config(cfg)
            write_credentials(cred)
            save_storage_state(ctx, paths.storage_state)
            ok(f"配置已写入 {paths.home}")

            # 12. smoke test (reuse already-signed-in panel client)
            if not no_smoke:
                from kuake.browser.smoke_test import run_smoke_test
                if run_smoke_test(Path(local_backup_dir), cloud_backup_path, panel):
                    ok("Smoke test 通过 — 配置可用")
                else:
                    warn("Smoke test 未通过 — 请检查夸克客户端,但配置已保存")
            else:
                info("已跳过 smoke test (--no-smoke)")

        ok("kuake init 完成。下一步: `kuake push <task> <src>`")
