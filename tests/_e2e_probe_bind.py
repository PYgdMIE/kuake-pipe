"""Watch all /autopanel/v1/* requests while user manually binds Quark in browser.
Goal: discover the exact API endpoint + payload format used to add a Quark disk."""
import sys
import time
sys.path.insert(0, "src")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def log(msg):
    print(f"[bind] {msg}", flush=True)


def main():
    from pathlib import Path
    from kuake.browser.session import launch_browser

    state_path = Path("/tmp/kuake_probe_state.json")
    if not state_path.exists():
        log("FATAL: storage_state missing, run main probe first to log in")
        return 1

    AUTOPANEL_URL = "https://a412422-befa-127e6e29.westc.seetacloud.com:8443/?token=jupyter-autodl-container-34894dbefa-127e6e29-b401e4c498eaf45bda66a78a45678e494391f59ded31a4224869c74fa266beb58"

    captured_requests = []

    log("launching browser to AutoPanel")
    log("INSTRUCTIONS: in the visible browser:")
    log("  1. wait for AutoPanel to load")
    log("  2. find '网盘' / 'Add netdisk' menu (sidebar)")
    log("  3. click '添加' / 'Add' button")
    log("  4. choose 'Quark' / '夸克' option")
    log("  5. complete the Quark login/binding flow")
    log("  6. I will print every /autopanel/v1/* request I see")
    log("  7. when done, press Ctrl+C in this terminal")
    log("")

    with launch_browser(headless=False, storage_state=state_path) as (ctx, _p):
        page = ctx.new_page()

        def on_request(request):
            if "/autopanel/v1/" not in request.url:
                return
            method = request.method
            url = request.url
            # Don't print all repetitive monitor calls
            if "monitor" in url:
                return
            # Show headers + body
            h = {k.lower(): v for k, v in request.headers.items()}
            post_body = ""
            try:
                if method == "POST":
                    post_body = request.post_data or ""
            except Exception:
                pass
            line = f"{method} ...{url[-80:]} body={post_body[:300]!r}"
            captured_requests.append(line)
            log(line)

        page.on("request", on_request)

        def on_response(response):
            url = response.url
            if "/autopanel/v1/" not in url:
                return
            if "monitor" in url:
                return
            try:
                if "json" in (response.headers.get("content-type") or ""):
                    body = response.body().decode("utf-8", "replace")
                    log(f"  → {response.status} body={body[:200]!r}")
            except Exception:
                pass

        page.on("response", on_response)

        try:
            page.goto(AUTOPANEL_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            log(f"goto failed: {e}")

        log("WATCHING for 600s (10 min). Drive the binding flow in the browser.")
        log("Press Ctrl+C when you've completed Quark binding.")
        try:
            for _ in range(600):
                page.wait_for_timeout(1000)
        except KeyboardInterrupt:
            log("ABORTED_BY_USER")

        log(f"CAPTURED_TOTAL: {len(captured_requests)} requests")
        return 0


if __name__ == "__main__":
    sys.exit(main())
