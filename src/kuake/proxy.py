"""HTTPS_PROXY detection helpers."""
from __future__ import annotations
import os
from typing import Optional


def get_https_proxy() -> Optional[str]:
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


def get_http_proxy() -> Optional[str]:
    return os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")


def requests_proxies() -> dict:
    """For requests.Session.proxies. Empty dict if no proxy."""
    p = get_https_proxy()
    if p:
        return {"http": p, "https": p}
    return {}
