"""Navigate to AutoPanel URL, intercept first /autopanel/v1/* request, extract auth headers."""
from __future__ import annotations
from dataclasses import dataclass

from kuake.errors import ScraperFailed
from kuake.progress import info, ok


@dataclass
class PanelAuth:
    base: str
    authorization: str
    autodl_token: str


def capture_auth(page, autopanel_url: str, timeout_ms: int = 30000) -> PanelAuth:
    """Visit AutoPanel; wait for user to enter the AutoPanel standalone password
    (the '独立访问密码' configured in AutoDL console), then capture the post-login
    Authorization header from any /autopanel/v1/* request.

    Auth model (verified 2026-05):
      - Pre-login:  Authorization='null'    AutodlAutoPanelToken=<jupyter-token>
      - Post-login: Authorization=<32-hex>  AutodlAutoPanelToken=<jupyter-token>

    We keep watching until a non-'null' Authorization shows up. If user takes too
    long (timeout_ms), raise — they probably haven't entered the password yet."""
    info("访问 AutoPanel,等待你输入独立密码登录...")
    captured: dict = {}
    seen_urls: list = []

    def on_request(request):
        if "/autopanel/v1/" not in request.url:
            return
        h = {k.lower(): v for k, v in request.headers.items()}
        auth_val = h.get("authorization", "") or ""
        token_val = h.get("autodlautopaneltoken", "") or ""
        seen_urls.append((request.url[-60:], auth_val[:30], token_val[:30]))
        if not token_val or token_val.lower() == "null":
            return
        # Accept any non-null Authorization (Bearer prefix optional)
        if not auth_val or auth_val.lower() == "null":
            return
        captured["authorization"] = auth_val
        captured["autodl_token"] = token_val
        captured["base"] = request.url.split("/autopanel/")[0]

    page.on("request", on_request)
    try:
        page.goto(autopanel_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass

    import time
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline and not captured:
        page.wait_for_timeout(2000)

    try:
        page.remove_listener("request", on_request)
    except Exception:
        pass

    if not captured:
        last_seen = "; ".join(f"url=...{u} auth={a!r} token={t!r}" for u, a, t in seen_urls[-3:])
        raise ScraperFailed(
            "Did not see an authenticated /autopanel/v1/* request — did you enter the standalone password? "
            f"Last 3 seen: {last_seen}"
        )
    ok("已抓取 AutoPanel 鉴权头")
    return PanelAuth(**captured)
