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
    """Visit AutoPanel and capture Authorization + AutodlAutoPanelToken from first API request."""
    info("访问 AutoPanel,拦截鉴权请求...")
    captured: dict = {}

    def on_request(request):
        if "/autopanel/v1/" not in request.url:
            return
        h = {k.lower(): v for k, v in request.headers.items()}
        if "authorization" in h and "autodlautopaneltoken" in h:
            captured["authorization"] = h["authorization"]
            captured["autodl_token"] = h["autodlautopaneltoken"]
            captured["base"] = request.url.split("/autopanel/")[0]

    page.on("request", on_request)
    try:
        page.goto(autopanel_url, wait_until="networkidle", timeout=timeout_ms)
    except Exception:
        pass
    page.wait_for_timeout(2000)
    try:
        page.remove_listener("request", on_request)
    except Exception:
        pass

    if not captured:
        raise ScraperFailed("Did not intercept any /autopanel/v1/* request with auth headers")
    ok("已抓取 AutoPanel 鉴权头")
    return PanelAuth(**captured)
