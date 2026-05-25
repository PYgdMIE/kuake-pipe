"""End-to-end DOM probe — runs the same scraper paths as `kuake init` but
without any interactive prompts. Use to verify selectors hit on real DOM.

Run:  python tests/_e2e_probe.py
You will see a Chromium window. Scan AutoDL QR code when prompted. Output goes
to stdout (line-buffered) so an external Monitor can stream it.
"""
import sys
import time

sys.path.insert(0, "src")


def log(msg: str) -> None:
    print(f"[probe] {msg}", flush=True)


# Reconfigure stdout to UTF-8 so the rich Console inside scrapers doesn't
# choke on emoji/checkmark in GBK locales (Windows default).
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    import os
    from pathlib import Path
    from kuake.browser.session import launch_browser, save_storage_state
    from kuake.browser import autodl_scraper, quark_scraper, panel_scraper
    from kuake.browser.selectors import (
        AUTODL_LOGGED_IN, AUTODL_INSTANCE_ROW, try_locators,
    )
    from kuake.errors import ScraperFailed

    state_path = Path("/tmp/kuake_probe_state.json")
    state_existed = state_path.exists()
    log(f"step 0: storage_state path={state_path} exists={state_existed}")

    log("step 1: launching headed Chromium")
    with launch_browser(
        headless=False,
        storage_state=state_path if state_existed else None,
    ) as (ctx, _p):
        page = ctx.new_page()

        if not state_existed:
            log("step 2: navigating to AutoDL login")
            page.goto("https://www.autodl.com/login",
                      wait_until="domcontentloaded", timeout=60000)
            log(f"  url={page.url}")

            log("step 3: waiting for you to scan AutoDL QR (up to 300s)")
            loc = try_locators(page, AUTODL_LOGGED_IN, timeout=300000)
            if loc is None:
                log("FAIL_AUTODL_LOGIN: AUTODL_LOGGED_IN never matched after 300s")
                log("FIX_HINT: check src/kuake/browser/selectors.py AUTODL_LOGGED_IN strategies")
                return 1
            log(f"  AUTODL_LOGGED_IN matched, current url={page.url}")
            save_storage_state(ctx, state_path)
            log(f"  saved storage_state to {state_path}")
        else:
            log("step 2-3: reusing saved login from previous run (no QR needed)")
            page.goto("https://www.autodl.com/console/homepage/personal",
                      wait_until="domcontentloaded", timeout=60000)
            log(f"  url={page.url}")

        log("step 3.5: DISCOVERY MODE — enumerate nav links")
        try:
            anchors = page.locator("a[href]").all()
            seen = set()
            for a in anchors[:80]:
                try:
                    href = a.get_attribute("href") or ""
                    if "/console" in href or "instance" in href.lower() or "container" in href.lower():
                        text = a.inner_text()[:40]
                        if href not in seen:
                            seen.add(href)
                            log(f"  LINK href={href!r}  text={text!r}")
                except Exception:
                    continue
            log("  --- enumerating clickable elements with 实例/容器 text ---")
            for keyword in ["我的实例", "实例列表", "容器实例", "我的容器", "容器列表", "Container", "Instance"]:
                try:
                    matches = page.get_by_text(keyword, exact=False).all()
                    for m in matches[:3]:
                        try:
                            tag = m.evaluate("e => e.tagName")
                            txt = m.inner_text()[:40]
                            log(f"  CLICKABLE_TEXT keyword={keyword!r} tag={tag} text={txt!r}")
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as e:
            log(f"  discovery error: {e}")

        log("step 3.6: DOM INSPECT — go to instance/list and dump table structure")
        page.goto("https://www.autodl.com/console/instance/list",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        log(f"  url={page.url}")

        # Probe common Ant/Element/custom table row patterns
        row_candidates = [
            "tr.ant-table-row",
            "[class*='ant-table-row']",
            ".ant-table-tbody tr",
            "tbody tr",
            "tr[data-row-key]",
            "[class*='instance-row']",
            "[class*='InstanceRow']",
            "[class*='instance-item']",
            "[class*='InstanceItem']",
            "[class*='instance-card']",
            "[class*='InstanceCard']",
            ".el-table__row",
            "[role='row']",
        ]
        for sel in row_candidates:
            try:
                n = page.locator(sel).count()
                log(f"  ROW_SEL {sel!r} → count={n}")
                if 0 < n < 20:
                    sample = page.locator(sel).nth(0).inner_text(timeout=2000)[:120]
                    log(f"    sample={sample!r}")
            except Exception as e:
                log(f"  ROW_SEL {sel!r} → ERROR {type(e).__name__}")

        log("step 3.7: dump tables found")
        try:
            tables = page.locator("table").all()
            log(f"  found {len(tables)} <table> elements")
            for i, t in enumerate(tables[:3]):
                cls = t.get_attribute("class") or ""
                tr_count = t.locator("tr").count()
                log(f"    table[{i}] class={cls!r} tr_count={tr_count}")
        except Exception as e:
            log(f"  tables probe error: {e}")

        log("step 3.8: text search for known instance name '小猪猪'")
        try:
            for kw in ["小猪猪", "实例ID", "ssh -p"]:
                cnt = page.locator(f"text=/{kw}/").count()
                log(f"  TEXT_PROBE {kw!r} → count={cnt}")
                if cnt > 0:
                    loc = page.locator(f"text=/{kw}/").first
                    # walk up to find ancestor with class
                    for level in range(8):
                        try:
                            cls = loc.evaluate(f"e => {{let n=e; for(let i=0;i<{level};i++) n=n.parentElement; return n ? (n.tagName + '.' + (n.className || '')) : null;}}")
                            if cls:
                                log(f"    ANC[{level}] {cls!r}")
                        except Exception:
                            break
        except Exception as e:
            log(f"  text search error: {e}")

        log("step 4: navigate to console + list instances (with updated selectors)")
        try:
            rows = autodl_scraper.list_instances(page)
            log(f"  PASS_LIST_INSTANCES: found {len(rows)} instances")
            for i, r in enumerate(rows):
                first_line = r["label"].splitlines()[0][:80] if r["label"] else ""
                log(f"    [{i}] selector={r['selector']!r}  label={first_line!r}")
        except ScraperFailed as e:
            log(f"FAIL_LIST_INSTANCES: {e}")
            log("FIX_HINT: AUTODL_INSTANCE_ROW selectors need a new fallback")
            try:
                from kuake.browser.selectors import AUTODL_CONSOLE_URL
                page.goto(AUTODL_CONSOLE_URL, timeout=10000)
                body_text = page.locator("body").inner_text(timeout=3000)[:400]
                log(f"BODY_TEXT_SAMPLE: {body_text!r}")
            except Exception as e2:
                log(f"  could not dump body: {e2}")
            return 2

        # find vGPU-32GB instance (or fall back to first if not found)
        TARGET_KEYWORD = os.environ.get("PROBE_TARGET", "vGPU-32GB")
        target_idx = 0
        for i, r in enumerate(rows):
            if TARGET_KEYWORD.lower() in r["label"].lower():
                target_idx = i
                log(f"  TARGET_FOUND: {TARGET_KEYWORD!r} at index {i}, label={r['label'][:60]!r}")
                break
        else:
            log(f"  TARGET_NOT_FOUND: {TARGET_KEYWORD!r} not in any label, using index 0")

        log(f"step 5: REAL extract_instance_details on row {target_idx}")
        try:
            info = autodl_scraper.extract_instance_details(page, target_idx, rows[target_idx]["selector"])
            log(f"  PASS_EXTRACT: host={info.ssh_host} port={info.ssh_port} user={info.ssh_user}")
            log(f"    password_len={len(info.ssh_password)}")
            log(f"    autopanel_url={info.autopanel_url!r}")
        except ScraperFailed as e:
            log(f"FAIL_EXTRACT: {e}")
            return 3
        except Exception as e:
            log(f"UNEXPECTED in extract: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
            return 99

        log(f"step 6: panel_scraper.capture_auth on {info.autopanel_url}")
        try:
            auth = panel_scraper.capture_auth(page, info.autopanel_url, timeout_ms=30000)
            log(f"  PASS_CAPTURE_AUTH: base={auth.base!r}")
            log(f"    authorization_prefix={auth.authorization[:30]!r}... (len={len(auth.authorization)})")
            log(f"    autodl_token_prefix={auth.autodl_token[:30]!r}... (len={len(auth.autodl_token)})")
        except Exception as e:
            log(f"FAIL_CAPTURE_AUTH: {e}")
            import traceback; traceback.print_exc()
            return 4

        log("step 6.5: WAIT for authenticated /autopanel/v1/* request (you may need to log into AutoPanel)")
        post_login_captured = {}
        sample_requests = []

        def on_authed_request(request):
            if "/autopanel/v1/" not in request.url:
                return
            h = {k.lower(): v for k, v in request.headers.items()}
            auth_val = h.get("authorization", "")
            token_val = h.get("autodlautopaneltoken", "")
            # store full values now
            sample_requests.append({"url": request.url, "auth": auth_val, "token": token_val})
            if not auth_val or auth_val.lower() == "null":
                return
            if not token_val or token_val.lower() == "null":
                return
            post_login_captured["authorization"] = auth_val
            post_login_captured["autodl_token"] = token_val
            post_login_captured["base"] = request.url.split("/autopanel/")[0]

        page.on("request", on_authed_request)
        try:
            page.goto(info.autopanel_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        log("  waiting up to 180s for authed request...")
        deadline = time.time() + 180
        while time.time() < deadline and not post_login_captured:
            page.wait_for_timeout(2000)
        try:
            page.remove_listener("request", on_authed_request)
        except Exception:
            pass

        if not post_login_captured:
            log("FAIL_AUTHED_REQ: no authed request. last_samples:")
            for s in sample_requests[-5:]:
                log(f"  url={s['url'][-80:]!r} auth_len={len(s['auth'])} auth={s['auth']!r} token={s['token']!r}")
            return 5
        log(f"  PASS_AUTHED:")
        log(f"    base={post_login_captured['base']!r}")
        log(f"    authorization_full={post_login_captured['authorization']!r}")
        log(f"    authorization_len={len(post_login_captured['authorization'])}")
        log(f"    autodl_token_len={len(post_login_captured['autodl_token'])}")

        # Capture cookies for this domain
        cookies = ctx.cookies(post_login_captured["base"])
        log(f"  COOKIE_COUNT for base: {len(cookies)}")
        for c in cookies:
            log(f"    cookie: name={c['name']!r} value_len={len(c.get('value', ''))} domain={c.get('domain')!r}")

        auth.base = post_login_captured["base"]
        auth.authorization = post_login_captured["authorization"]
        auth.autodl_token = post_login_captured["autodl_token"]
        captured_cookies = cookies

        log("step 7: REAL panel_api call WITH cookies injected")
        try:
            from kuake.panel_api import PanelClient
            client = PanelClient(
                base=auth.base,
                authorization=auth.authorization,
                autodl_token=auth.autodl_token,
                fs_id="quark1",
            )
            # Inject cookies into the requests Session
            for c in captured_cookies:
                client.s.cookies.set(
                    c["name"], c.get("value", ""),
                    domain=c.get("domain", ""),
                    path=c.get("path", "/"),
                )

            wd = client.workdir()
            log(f"  PASS_PANEL_WORKDIR: {wd!r}")
            top = client.list_dir("0")
            log(f"  PASS_PANEL_LIST_ROOT: {len(top)} entries")
            for item in top[:10]:
                log(f"    - name={item.get('name')!r} is_dir={item.get('is_dir')} size={item.get('size', 0)}")
        except Exception as e:
            log(f"FAIL_PANEL_API: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
            return 7

        log("PROBE_COMPLETE_v10")
        return 0

        # legacy debug paths below — keep for future reference but unreachable
        log("step 4.5: dump row 0 full text (the actual instance content)")
        try:
            row0 = page.locator(".instance-table .el-table__row").nth(0)
            full = row0.inner_text(timeout=3000)
            log(f"  ROW0_TEXT (sanitized): {[part.strip() for part in full.split(chr(10)) if part.strip()]!r}"[:500])
            # try to find status / instance_id within the row
            cells = row0.locator("td").all()
            log(f"  ROW0 has {len(cells)} <td> cells")
            for i, cell in enumerate(cells):
                try:
                    txt = cell.inner_text(timeout=500).strip()
                    log(f"    cell[{i}]: {txt!r}"[:160])
                except Exception:
                    pass
        except Exception as e:
            log(f"  row inspection error: {e}")

        log("step 4.55: dump icon-fuzhi attributes (data-clipboard hidden values)")
        try:
            cell7 = row0.locator("td").nth(7)
            icons = cell7.locator(".icon-fuzhi").all()
            log(f"  CELL7 has {len(icons)} icon-fuzhi (copy icons)")
            for i, icon in enumerate(icons):
                try:
                    attrs = icon.evaluate("""e => {
                        const a = {};
                        for (const attr of e.attributes) a[attr.name] = attr.value;
                        a.outerHTML = e.outerHTML.slice(0, 300);
                        return a;
                    }""")
                    log(f"    icon[{i}] attrs={attrs}")
                except Exception as ex:
                    log(f"    icon[{i}] err: {ex}")

            log("step 4.56: try click copy icon + read clipboard")
            try:
                ctx.grant_permissions(["clipboard-read", "clipboard-write"])
                # first icon = ssh; second = password
                icons[0].click()
                page.wait_for_timeout(800)
                ssh_text = page.evaluate("() => navigator.clipboard.readText()")
                log(f"  CLIPBOARD_SSH: {ssh_text!r}"[:300])

                icons[1].click()
                page.wait_for_timeout(800)
                pwd_text = page.evaluate("() => navigator.clipboard.readText()")
                log(f"  CLIPBOARD_PWD: {pwd_text!r}"[:300])
            except Exception as ex:
                log(f"  clipboard probe error: {ex}")
        except Exception as e:
            log(f"  cell7 probe error: {e}")

        log("step 4.6: click '登录指令' button → look for SSH command")
        try:
            login_btn = page.locator("text=/登录指令/").first
            login_btn.click()
            page.wait_for_timeout(3000)
            for kw in ["ssh -p", "root@", "密码", "Password"]:
                cnt = page.locator(f"text=/{kw}/").count()
                log(f"  AFTER_LOGIN_CLICK {kw!r} → count={cnt}")
                if cnt > 0:
                    loc = page.locator(f"text=/{kw}/").first
                    try:
                        txt = loc.inner_text(timeout=1000)
                        log(f"    matched_text: {txt!r}"[:200])
                        # find enclosing modal/dialog
                        for level in range(8):
                            try:
                                cls = loc.evaluate(f"e => {{let n=e; for(let i=0;i<{level};i++) n=n.parentElement; return n ? (n.tagName + '.' + (n.className || '')) : null;}}")
                                if cls and ('dialog' in cls.lower() or 'modal' in cls.lower() or 'popover' in cls.lower() or 'el-dialog' in cls.lower()):
                                    log(f"    MODAL_FOUND at ANC[{level}]: {cls!r}")
                                    break
                                if cls:
                                    log(f"    ssh_anc[{level}] {cls!r}")
                            except Exception:
                                break
                    except Exception:
                        pass
        except Exception as e:
            log(f"  login click error: {e}")

        log("step 4.7: try AutoPanel button — see what happens")
        try:
            # Close any existing modal first
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                pass

            # Watch for new pages (popup tab)
            new_pages = []
            ctx.on("page", lambda p: new_pages.append(p))

            panel_btn = page.locator("button.el-button:has-text('AutoPanel')").first
            log(f"  AutoPanel button visible: {panel_btn.is_visible(timeout=2000)}")
            panel_btn.click()
            page.wait_for_timeout(4000)
            log(f"  main page url after click: {page.url}")
            log(f"  new_pages opened: {len(new_pages)}")
            for np in new_pages:
                try:
                    np.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                log(f"    NEW_PAGE url={np.url}")
        except Exception as e:
            log(f"  AutoPanel click error: {e}")

        log("PROBE_COMPLETE")
        return 0  # exit before going to quark — we want to focus on AutoDL first

        log("step 5: extract details of instance [0]")
        try:
            info = autodl_scraper.extract_instance_details(page, 0, rows[0]["selector"])
            log(f"  PASS_EXTRACT_DETAILS: host={info.ssh_host} port={info.ssh_port} "
                f"user={info.ssh_user} password={'(set)' if info.ssh_password else '(empty)'} "
                f"autopanel={info.autopanel_url!r}")
        except ScraperFailed as e:
            log(f"FAIL_EXTRACT_DETAILS: {e}")
            log("FIX_HINT: AUTODL_INSTANCE_SSH / AUTODL_INSTANCE_PASSWORD / "
                "AUTODL_AUTOPANEL_LINK selectors need fallbacks")
            return 3

        if not info.autopanel_url:
            log("WARN_NO_AUTOPANEL_URL: extracted SSH info but no AutoPanel URL")
            log("SKIP_PANEL_PROBE")
        else:
            log(f"step 6: probe AutoPanel auth interception @ {info.autopanel_url}")
            try:
                auth = panel_scraper.capture_auth(page, info.autopanel_url)
                log(f"  PASS_CAPTURE_AUTH: base={auth.base} authorization=...({len(auth.authorization)} chars) "
                    f"autodl_token=...({len(auth.autodl_token)} chars)")
            except ScraperFailed as e:
                log(f"FAIL_CAPTURE_AUTH: {e}")
                log("FIX_HINT: AutoPanel URL or AUTOPANEL_API_PATTERN may have changed")
                return 4

        log("step 7: please scan Quark QR in the browser (window will navigate)")
        page.goto("https://pan.quark.cn",
                  wait_until="domcontentloaded", timeout=60000)
        log("  waiting up to 300s for Quark login...")
        from kuake.browser.selectors import QUARK_LOGGED_IN
        qloc = try_locators(page, QUARK_LOGGED_IN, timeout=300000)
        if qloc is None:
            log("FAIL_QUARK_LOGIN: QUARK_LOGGED_IN never matched after 300s")
            log("FIX_HINT: src/kuake/browser/selectors.py QUARK_LOGGED_IN strategies")
            return 5
        log(f"  QUARK_LOGGED_IN matched, current url={page.url}")

        log("step 8: list /我的备份/ folders")
        try:
            folders = quark_scraper.list_backup_folders(page)
            log(f"  PASS_LIST_BACKUP_FOLDERS: found {len(folders)} folders")
            for i, n in enumerate(folders):
                log(f"    [{i}] {n!r}")
        except ScraperFailed as e:
            log(f"FAIL_LIST_BACKUP_FOLDERS: {e}")
            log("FIX_HINT: QUARK_BACKUP_FOLDER selectors need a new fallback")
            try:
                body_text = page.locator("body").inner_text(timeout=3000)[:400]
                log(f"BODY_TEXT_SAMPLE: {body_text!r}")
            except Exception:
                pass
            return 6

        log("ALL_PROBES_PASSED")
        log("you can now safely run `kuake init` — selectors are all verified")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("ABORTED_BY_USER")
        sys.exit(130)
    except Exception as e:
        import traceback
        log(f"UNEXPECTED: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(99)
