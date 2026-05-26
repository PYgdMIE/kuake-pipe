"""First-run wizard. Drives Playwright through AutoDL + Quark login and configures everything."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

from rich.prompt import Prompt

from kuake.concurrency import FileLock, LockBusy
from kuake.config import (
    Config,
    Credentials,
    config_paths,
    write_config,
    write_credentials,
)
from kuake.errors import ConcurrencyLock, ScraperFailed, UserInputError
from kuake.progress import console, info, ok, warn
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
    Loops on invalid input; falls back to default on stdin EOF."""
    while True:
        try:
            raw = Prompt.ask(prompt, default=str(default))
        except (EOFError, KeyboardInterrupt):
            warn(f"stdin 关闭,用默认值 {default}")
            return default - 1
        try:
            v = int(raw)
        except ValueError:
            warn(f"请输入 1-{n} 之间的数字")
            continue
        if 1 <= v <= n:
            return v - 1
        warn(f"超出范围 1-{n}")


def _safe_prompt(prompt: str, default: str = "") -> str:
    """Prompt.ask with EOF fallback to default."""
    try:
        return Prompt.ask(prompt, default=default)
    except (EOFError, KeyboardInterrupt):
        warn(f"stdin 关闭,用默认值 {default!r}")
        return default


def run(no_smoke: bool = False, ssh_key: bool = False,
        use_system_chrome: bool = False,
        instance_idx: int | None = None,
        autopanel_password: str | None = None,
        cloud_dir: str | None = None) -> None:
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
        from kuake.browser import autodl_scraper, quark_scraper
        from kuake.browser.session import launch_browser, save_storage_state

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
            # save storage_state ASAP after AutoDL login so future runs
            # don't need a re-scan even if init aborts later
            try:
                save_storage_state(ctx, paths.storage_state)
            except Exception:
                pass

            # 4. list & pick instance
            rows = autodl_scraper.list_instances(page)
            running_indices = [i for i, r in enumerate(rows) if r.get("running")]
            console.print("\n[bold]检测到 AutoDL 实例:[/bold]")
            for i, r in enumerate(rows, 1):
                name = r.get("name", "")[:30]
                gpu = r.get("gpu", "")[:20]
                status = r.get("status", "未知")
                color = "green" if "运行中" in status else "yellow"
                console.print(
                    f"  [{i}] [bold]{name}[/bold]  "
                    f"[dim]{gpu}[/dim]  "
                    f"[{color}]{status}[/{color}]"
                )
            if not running_indices:
                raise UserInputError(
                    "所有实例都已关机 — 请到 AutoDL 控制台开机后重跑 `kuake init`"
                )
            default_idx = running_indices[0] + 1  # 1-based
            if instance_idx is not None:
                if not (1 <= instance_idx <= len(rows)):
                    raise UserInputError(
                        f"--instance {instance_idx} 超出范围 1-{len(rows)}"
                    )
                idx = instance_idx - 1
                console.print(f"[dim]使用 --instance {instance_idx}:[/dim] "
                              f"{rows[idx].get('name', '')}")
            else:
                console.print(f"[dim]提示:默认选第一个运行中的实例 [{default_idx}][/dim]")
                idx = _prompt_index("选择实例", len(rows), default=default_idx)
            chosen = rows[idx]
            if not chosen.get("running"):
                raise UserInputError(
                    f"实例 {chosen.get('name')} 当前是 {chosen.get('status')},无法抓取 SSH 信息;请改选运行中的"
                )

            # 5. extract SSH + AutoPanel URL
            instance = autodl_scraper.extract_instance_details(
                page, idx, chosen["selector"]
            )
            ok(f"  SSH: {instance.ssh_user}@{instance.ssh_host}:{instance.ssh_port}")
            if instance.autopanel_url:
                ok(f"  AutoPanel: {instance.autopanel_url}")

            # 6. auth mode: --ssh-key 显式选密钥模式;否则默认 password.
            # v0.4 起不再弹 Confirm prompt — 想用密钥就传 --ssh-key.
            use_key = ssh_key

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

            # 7. AutoPanel auth — open in browser, user types standalone password,
            #    we intercept the /sign_in POST body (contains SHA1) and response (token)
            if not instance.autopanel_url:
                instance_url = Prompt.ask("未自动检测到 AutoPanel URL,请粘贴:")
                instance.autopanel_url = instance_url
            panel_base, jupyter_token = _parse_jupyter_token(instance.autopanel_url)
            ok(f"  AutoPanel base: {panel_base}")

            if autopanel_password:
                info("\n[autopanel] 打开 AutoPanel, 自动填入独立密码...")
            else:
                info("\n[在浏览器里] 打开 AutoPanel,如果显示登录页请输入独立密码...")
                info("[在浏览器里] 如果已经直接进 AutoPanel 主页,则无需任何操作")

            captured = {"pwd_sha1": "", "token": ""}

            def on_request(request):
                """Capture either sign_in body (to save sha1) OR any authenticated request."""
                url = request.url
                if "/autopanel/v1/" not in url:
                    return
                # 1. sign_in POST contains the password sha1
                if url.endswith("/sign_in") and request.method == "POST":
                    try:
                        body = request.post_data
                        if body:
                            import json as _json
                            j = _json.loads(body)
                            if isinstance(j, dict) and j.get("password"):
                                captured["pwd_sha1"] = j["password"]
                    except Exception:
                        pass
                    return
                # 2. any other request with non-null Authorization gives us the token
                if captured["token"]:
                    return
                h = {k.lower(): v for k, v in request.headers.items()}
                auth_val = h.get("authorization", "")
                if auth_val and auth_val.lower() != "null" and len(auth_val) > 10:
                    captured["token"] = auth_val

            def on_response(response):
                """If sign_in succeeded, capture token from response body."""
                if "/autopanel/v1/sign_in" not in response.url:
                    return
                try:
                    body = response.json()
                    if body.get("code") in ("success", "Success") and body.get("data"):
                        captured["token"] = body["data"]
                except Exception:
                    pass

            page.on("request", on_request)
            page.on("response", on_response)
            page.goto(instance.autopanel_url,
                      wait_until="domcontentloaded", timeout=30000)

            # 自动填密码 (如果提供了 --autopanel-password / env var)
            if autopanel_password and not captured["token"]:
                page.wait_for_timeout(2000)  # 让 SPA 渲染登录表单
                try:
                    # AutoPanel 用普通 password input + 回车提交
                    pwd_input = page.locator(
                        'input[type="password"], input[placeholder*="密码"], '
                        'input[placeholder*="独立"]'
                    ).first
                    pwd_input.fill(autopanel_password, timeout=8000)
                    page.wait_for_timeout(300)
                    pwd_input.press("Enter")
                    ok("  自动提交独立密码")
                except Exception as e:
                    warn(f"  自动填密码失败 ({e}),回退到手动输入")

            import time as _time
            deadline = _time.time() + (
                60 if autopanel_password else 180
            )  # 自动填模式应该几秒就拿到 token
            while _time.time() < deadline and not captured["token"]:
                page.wait_for_timeout(2000)
            try:
                page.remove_listener("request", on_request)
                page.remove_listener("response", on_response)
            except Exception:
                pass

            if not captured["token"]:
                raise UserInputError(
                    "180s 内未捕获 AutoPanel 鉴权 token,请确认你已经登录 AutoPanel"
                )
            pwd_sha1 = captured["pwd_sha1"]  # may be empty if already logged in
            session_token = captured["token"]
            ok(f"  AutoPanel token captured (len={len(session_token)})")
            if not pwd_sha1:
                warn("  未抓到 sign_in 密码哈希 — refresh 将无法自动重登,届时需重跑 init")

            from kuake.panel_api import PanelClient
            from kuake.proxy import requests_proxies
            panel = PanelClient(
                base=panel_base,
                authorization=session_token,
                autodl_token=jupyter_token,
                fs_id="quark1",
                proxies=requests_proxies(),
            )

            # 8. Quark login (visible browser, may auto-pass via saved session)
            quark_scraper.wait_login(page)
            try:
                save_storage_state(ctx, paths.storage_state)
            except Exception:
                pass

            # 8.1 extract Quark cookie from browser
            from kuake.browser.quark_cookie import extract_quark_cookie_header
            quark_cookie = extract_quark_cookie_header(ctx)
            if not quark_cookie:
                raise ScraperFailed("Could not extract Quark cookies from browser session")
            info(f"  抓到 Quark cookie ({len(quark_cookie)} chars)")

            # 8.2 bind to AutoPanel (供 stage 3 服务器侧下载使用)
            try:
                existing = panel.netdisk_list()
                if existing:
                    ok(f"  AutoPanel 已绑定 {len(existing)} 个网盘,跳过绑定")
                else:
                    info("  AutoPanel 上没有网盘,自动绑定 Quark...")
                    panel.bind_quark(quark_cookie)
                    ok("  Quark 网盘已绑定 AutoPanel")
            except Exception as e:
                # AutoPanel 绑定失败不致命 — push stage 2 (上传) 不需要 AutoPanel,
                # 只有 stage 3 (服务器侧下载) 需要,届时会再次报错
                warn(f"  AutoPanel 绑定/查询失败 ({e}),稍后跑 push 时再处理")

            # 9. cloud upload target — v0.4 起不再依赖夸克 PC 客户端备份目录,
            #    直接用 API 上传到自定义路径,默认 /kuake-uploads
            if cloud_dir is not None:
                cloud_backup_path = cloud_dir
                ok(f"  使用 --cloud-dir: {cloud_backup_path}")
            else:
                cloud_backup_path = _safe_prompt(
                    "云端上传目录 (会自动创建,不需先在客户端配置)",
                    default="/kuake-uploads",
                )
            if not cloud_backup_path.startswith("/"):
                cloud_backup_path = "/" + cloud_backup_path

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

            # 12. smoke test — 直接上传 1KB 文件验证 Quark API + cookie 可用
            if not no_smoke:
                from kuake.browser.smoke_test import run_smoke_test
                if not run_smoke_test(quark_cookie, cloud_backup_path):
                    warn("Smoke test 未通过 — 配置已保存,但首次 push 可能失败")
            else:
                info("已跳过 smoke test (--no-smoke)")

        ok("kuake init 完成。下一步: `kuake push <task> <src>`")
