"""Watch /api/* and /market/* calls on autodl.com/market/list to discover the
listing + instance-creation APIs."""
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
    print(f"[market] {msg}", flush=True)


def main():
    from kuake.browser.session import launch_browser

    state_candidates = [
        Path("/tmp/kuake-test/state/storage_state.json"),
        Path("/tmp/kuake_probe_state.json"),
    ]
    state_path = next((p for p in state_candidates if p.exists()), None)
    if state_path:
        log(f"reusing saved session at {state_path}")
    else:
        log("no saved session — you'll need to log in inside the browser")

    log("launching browser")
    with launch_browser(headless=False, storage_state=state_path) as (ctx, _p):
        page = ctx.new_page()

        captured = []

        def on_request(request):
            url = request.url
            if "autodl.com" not in url:
                return
            method = request.method
            if method not in ("POST", "GET") or not any(
                k in url for k in ("/api/", "market", "instance", "create", "rent")
            ):
                return
            body = request.post_data or ""
            line = f"{method} {url[:120]} body={body[:300]!r}"
            captured.append(line)
            log(line)

        def on_response(response):
            url = response.url
            if "autodl.com" not in url:
                return
            if not any(k in url for k in ("/api/", "market", "instance", "create", "rent")):
                return
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    body = response.body().decode("utf-8", "replace")
                    log(f"  → {response.status} body={body[:400]!r}")
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        log("navigating to market/list")
        page.goto("https://www.autodl.com/market/list",
                  wait_until="domcontentloaded", timeout=30000)
        log("PLEASE click around filters in the browser (region/GPU/count)")
        log("when done, press Ctrl+C")

        try:
            for _ in range(600):
                page.wait_for_timeout(1000)
        except KeyboardInterrupt:
            log("EXIT")

        # save state for next time
        try:
            from kuake.browser.session import save_storage_state
            save_storage_state(ctx, Path("/tmp/kuake_market_state.json"))
            log("saved storage_state to /tmp/kuake_market_state.json")
        except Exception:
            pass

        log(f"CAPTURED {len(captured)} requests")


if __name__ == "__main__":
    sys.exit(main() or 0)
