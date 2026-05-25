"""Open AutoPanel /netdisk/add, wait for user to type standalone password (manual),
then automatically: select Quark from dropdown, paste cookie, click 添加.
Captures the bind POST + response."""
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def log(msg):
    print(f"[autobind2] {msg}", flush=True)


def main():
    from kuake.browser.session import launch_browser

    state_path = Path("/tmp/kuake_probe_state.json")
    cookie_path = Path("C:/Users/mie/.quark/cookie.txt")
    if not cookie_path.exists():
        log("FATAL: ~/.quark/cookie.txt missing")
        return 2
    quark_cookie = cookie_path.read_text(encoding="utf-8").strip()
    log(f"Loaded Quark cookie: {len(quark_cookie)} chars")

    AUTOPANEL_BASE = "https://a412422-befa-127e6e29.westc.seetacloud.com:8443"
    JUPYTER_TOKEN = "jupyter-autodl-container-34894dbefa-127e6e29-b401e4c498eaf45bda66a78a45678e494391f59ded31a4224869c74fa266beb58"

    log("launching browser")
    with launch_browser(headless=False, storage_state=state_path) as (ctx, _p):
        page = ctx.new_page()

        bind_posts = []

        def on_request(request):
            if "/autopanel/v1/" not in request.url:
                return
            if any(skip in request.url for skip in ("task/doing", "monitor", "version", "qrcode")):
                return
            method = request.method
            url = request.url
            body = request.post_data or "" if method == "POST" else ""
            line = f"{method} ...{url[-90:]} body={body[:400]!r}"
            log(line)
            if method == "POST" and "netdisk" in url:
                bind_posts.append(line)

        def on_response(response):
            url = response.url
            if "/autopanel/v1/" not in url:
                return
            if any(skip in url for skip in ("task/doing", "monitor", "version", "qrcode")):
                return
            try:
                if "json" in (response.headers.get("content-type") or ""):
                    body = response.body().decode("utf-8", "replace")
                    log(f"  → {response.status} body={body[:400]!r}")
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        log("STEP 1: navigating to AutoPanel /netdisk/add")
        log("STEP 1: PLEASE ENTER YOUR STANDALONE PASSWORD in the visible browser")
        page.goto(f"{AUTOPANEL_BASE}/?token={JUPYTER_TOKEN}",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        page.goto(f"{AUTOPANEL_BASE}/netdisk/add",
                  wait_until="domcontentloaded", timeout=30000)

        # Wait for /netdisk/add to actually load (not redirected to authFail)
        log("STEP 2: waiting up to 180s for you to log in (then page lands on /netdisk/add)")
        deadline = time.time() + 180
        loaded = False
        while time.time() < deadline:
            page.wait_for_timeout(2000)
            current = page.url
            if "/netdisk/add" in current and "authFail" not in current:
                # Also check the dropdown is rendered
                try:
                    dropdown = page.locator(".el-select").first
                    if dropdown.count() > 0 and dropdown.is_visible():
                        loaded = True
                        break
                except Exception:
                    pass
        if not loaded:
            log(f"FAIL_LOAD: current url={page.url}, dropdown not found")
            return 5
        log(f"  /netdisk/add loaded; current url={page.url}")

        log("STEP 3: clicking dropdown to open options")
        try:
            dropdown_input = page.locator(".el-select__inner, .el-input__inner").first
            dropdown_input.click()
            page.wait_for_timeout(1500)

            log("STEP 4: selecting 夸克网盘 from options")
            quark_option = page.locator("li.el-select-dropdown__item:has-text('夸克网盘')").first
            if quark_option.count() == 0:
                # fallback: try plain text match in list
                quark_option = page.locator("li:has-text('夸克网盘')").first
            quark_option.click()
            page.wait_for_timeout(2000)
        except Exception as e:
            log(f"FAIL_SELECT_QUARK: {e}")
            return 6

        log("STEP 5: fill Cookie input")
        try:
            # Find the cookie textarea or input — it appears after Quark is selected
            cookie_input = page.locator("textarea, input.el-input__inner").last
            cookie_input.fill(quark_cookie)
            page.wait_for_timeout(1000)
        except Exception as e:
            log(f"FAIL_FILL_COOKIE: {e}")
            return 7

        log("STEP 6: clicking 添加 button")
        try:
            add_btn = page.locator("button:has-text('添加')").first
            add_btn.click()
            page.wait_for_timeout(5000)  # let bind POST happen
        except Exception as e:
            log(f"FAIL_CLICK_ADD: {e}")
            return 8

        log("STEP 7: waiting 5s more for response")
        page.wait_for_timeout(5000)

        log(f"CAPTURED bind POSTs ({len(bind_posts)}):")
        for p in bind_posts:
            log(f"  {p}")

        return 0


if __name__ == "__main__":
    sys.exit(main())
