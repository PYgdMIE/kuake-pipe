"""Fully automated: navigate AutoPanel /netdisk/add, select 夸克网盘, fill Quark
cookie from ~/.quark/cookie.txt, click 添加, capture the bind POST request."""
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
    print(f"[autobind] {msg}", flush=True)


def main():
    from kuake.browser.session import launch_browser

    state_path = Path("/tmp/kuake_probe_state.json")
    if not state_path.exists():
        log("FATAL: storage_state missing")
        return 1

    cookie_path = Path("C:/Users/mie/.quark/cookie.txt")
    if not cookie_path.exists():
        log("FATAL: ~/.quark/cookie.txt missing")
        return 2
    quark_cookie = cookie_path.read_text(encoding="utf-8").strip()
    log(f"Loaded Quark cookie: {len(quark_cookie)} chars")

    AUTOPANEL_BASE = "https://a412422-befa-127e6e29.westc.seetacloud.com:8443"
    SIGN_IN_HASH = "db5f448352915fd9de8e2f7f5389c7e6b7e839fd"
    JUPYTER_TOKEN = "jupyter-autodl-container-34894dbefa-127e6e29-b401e4c498eaf45bda66a78a45678e494391f59ded31a4224869c74fa266beb58"

    captured_posts = []

    log("launching browser")
    with launch_browser(headless=False, storage_state=state_path) as (ctx, _p):
        page = ctx.new_page()

        def on_request(request):
            if "/autopanel/v1/" not in request.url:
                return
            if "task/doing" in request.url or "monitor" in request.url:
                return
            method = request.method
            url = request.url
            body = request.post_data or "" if method == "POST" else ""
            line = f"{method} ...{url[-80:]} body={body[:300]!r}"
            captured_posts.append(line)
            log(line)

        def on_response(response):
            url = response.url
            if "/autopanel/v1/" not in url:
                return
            if "task/doing" in url or "monitor" in url:
                return
            try:
                if "json" in (response.headers.get("content-type") or ""):
                    body = response.body().decode("utf-8", "replace")
                    log(f"  → {response.status} body={body[:400]!r}")
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        # Step 0: load AutoPanel URL with JupyterLab token (sets cookies / context)
        log("step 0: load AutoPanel with JupyterLab token")
        page.goto(f"{AUTOPANEL_BASE}/?token={JUPYTER_TOKEN}",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Step 1: sign in to AutoPanel via API call (replay known hash with JupyterLab token)
        log("step 1: replaying sign_in with known hash + AutodlAutoPanelToken")
        try:
            resp = page.evaluate(f"""
            async () => {{
                const r = await fetch('{AUTOPANEL_BASE}/autopanel/v1/sign_in', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Accept': '*/*',
                        'AutodlAutoPanelToken': '{JUPYTER_TOKEN}',
                        'Authorization': 'null'
                    }},
                    body: JSON.stringify({{ password: '{SIGN_IN_HASH}' }})
                }});
                return await r.text();
            }}
            """)
            log(f"  sign_in response: {resp[:200]!r}")
            import json
            j = json.loads(resp)
            session_token = j.get("data")
            if not session_token:
                log(f"FAIL_SIGN_IN: {j}")
                return 3
            log(f"  PASS_SIGN_IN: session_token={session_token!r}")
        except Exception as e:
            log(f"FAIL_SIGN_IN: {e}")
            return 3

        # Step 2: navigate to /netdisk/add
        log("step 2: navigate to /netdisk/add")
        page.goto(f"{AUTOPANEL_BASE}/netdisk/add",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # The page may show a sign-in prompt. Inject the token into localStorage to bypass
        log("step 3: inject session_token via localStorage")
        try:
            page.evaluate(f"""
            () => {{
                localStorage.setItem('autopanel_token', '{session_token}');
                localStorage.setItem('Authorization', '{session_token}');
            }}
            """)
            page.reload(wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception as e:
            log(f"  localStorage inject error: {e}")

        # Step 4: select 夸克网盘 in the dropdown and fill cookie
        log("step 4: find form elements (dropdown + cookie input)")
        log(f"  current url: {page.url}")
        # dump form structure
        try:
            forms = page.evaluate("""
            () => {
                const inputs = Array.from(document.querySelectorAll('input,textarea,.el-select__inner')).map(e => ({
                    tag: e.tagName,
                    cls: e.className,
                    placeholder: e.placeholder || '',
                    name: e.name || '',
                    value: e.value || ''
                }));
                const buttons = Array.from(document.querySelectorAll('button')).map(b => ({
                    cls: b.className,
                    text: (b.innerText || '').slice(0, 20)
                }));
                return { inputs, buttons };
            }
            """)
            log(f"  inputs: {forms['inputs']}")
            log(f"  buttons: {forms['buttons']}")
        except Exception as e:
            log(f"  form dump error: {e}")

        log("step 5: NOT auto-clicking add; press Ctrl+C to exit after manual verify")
        try:
            for _ in range(300):
                page.wait_for_timeout(1000)
        except KeyboardInterrupt:
            log("EXIT_BY_USER")

        log(f"CAPTURED_POSTS: {len(captured_posts)}")
        for p in captured_posts:
            log(f"  {p}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
