"""Extract Quark cookies from a Playwright browser context as a Cookie header string."""
from __future__ import annotations
from typing import List


def extract_quark_cookie_header(context, domain_hint: str = "quark.cn") -> str:
    """Get all cookies whose domain contains `domain_hint` and format them as a
    standard Cookie header value (`k1=v1; k2=v2; ...`).
    Returns empty string if no cookies match."""
    try:
        cookies = context.cookies()
    except Exception:
        return ""
    parts: List[str] = []
    seen_names = set()
    for c in cookies:
        domain = c.get("domain", "")
        if domain_hint not in domain:
            continue
        name = c.get("name", "")
        value = c.get("value", "")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        parts.append(f"{name}={value}")
    return "; ".join(parts)
