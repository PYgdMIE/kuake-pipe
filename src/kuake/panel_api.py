"""AutoPanel HTTP API client + expiry detection + auto-refresh hook."""
from __future__ import annotations
import time
from typing import Any, Callable, Optional

import requests

from kuake.errors import AuthExpired, NetworkError


def is_expired_response(resp) -> bool:
    """3-state expiry detection per spec §5.3."""
    if resp.status_code == 401:
        return True
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "html" in ct:
        return True
    try:
        j = resp.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        return False
    code = j.get("code", "")
    if code in ("success", "ok"):
        return False
    code_str = str(code).lower()
    if "expired" in code_str or "unauthorized" in code_str:
        return True
    return False


class PanelClient:
    """AutoPanel HTTP client. Pass a refresh_callback to enable transparent auto-refresh."""

    def __init__(
        self,
        base: str,
        authorization: str,
        autodl_token: str,
        fs_id: str = "quark1",
        refresh_callback: Optional[Callable[[], "PanelClient"]] = None,
        timeout: int = 30,
        proxies: Optional[dict] = None,
    ):
        self.base = base.rstrip("/")
        self.fs_id = fs_id
        self.timeout = timeout
        self._refresh_callback = refresh_callback
        self._refresh_attempted = False
        self.s = requests.Session()
        if proxies:
            self.s.proxies.update(proxies)
        self._set_headers(authorization, autodl_token)

    def _set_headers(self, authorization: str, autodl_token: str):
        self.s.headers.update({
            "Accept": "*/*",
            "Authorization": authorization,
            "AutodlAutoPanelToken": autodl_token,
            "Referer": f"{self.base}/netdisk/file?path=/&disk={self.fs_id}&type=AutoDL_Quark",
            "User-Agent": "Mozilla/5.0 (kuake-pipe) Chrome/148.0.0.0",
        })

    def _request(self, method: str, ep: str, **kwargs) -> dict:
        try:
            r = self.s.request(method, f"{self.base}{ep}", timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error calling {ep}: {e}") from e

        if is_expired_response(r):
            if self._refresh_callback and not self._refresh_attempted:
                self._refresh_attempted = True
                new_client = self._refresh_callback()
                self._set_headers(
                    new_client.s.headers["Authorization"],
                    new_client.s.headers["AutodlAutoPanelToken"],
                )
                try:
                    r = self.s.request(method, f"{self.base}{ep}", timeout=self.timeout, **kwargs)
                except requests.exceptions.RequestException as e:
                    raise NetworkError(f"Retry failed: {e}") from e
                if is_expired_response(r):
                    raise AuthExpired(f"Still expired after refresh: {ep}")
            else:
                raise AuthExpired(f"Auth expired: {ep}")

        r.raise_for_status()
        j = r.json()
        if j.get("code") != "success":
            raise NetworkError(f"API {ep} returned: {j}")
        return j["data"]

    def workdir(self) -> str:
        return self._request("GET", "/autopanel/v1/workdir")

    def list_dir(self, file_id: str = "0") -> list[dict]:
        d = self._request("GET", "/autopanel/v1/netdisk/file",
                          params={"fs_id": self.fs_id, "marker": "", "file_id": file_id})
        return d["list"]["List"]

    def find_by_path(self, path: str) -> Optional[dict]:
        parts = [p for p in path.strip("/").split("/") if p]
        parent = "0"
        current: Optional[dict] = None
        for name in parts:
            items = self.list_dir(parent)
            for item in items:
                if item["name"] == name:
                    current = item
                    parent = item["file_id"]
                    break
            else:
                return None
        return current

    def trigger_download(self, item: dict, src_path: str, dst_path: str = "") -> dict:
        body = {
            "dst_path": dst_path,
            "fsid": self.fs_id,
            "src_path": src_path if not item["is_dir"] else src_path.rstrip("/") + "/",
            "file_id": item["file_id"],
            "is_dir": item["is_dir"],
            "download_url": item.get("download_url", ""),
            "file_size": item.get("size", 0),
        }
        return self._request("POST", "/autopanel/v1/netdisk/download", json=body)

    def tasks(self, limit: int = 20) -> dict:
        return self._request("GET", "/autopanel/v1/netdisk/task", params={"limit": limit})

    def wait_task(
        self,
        file_name: str,
        timeout: int = 3600,
        poll: int = 5,
        on_progress: Optional[Callable[[str, Any], None]] = None,
    ) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            t = self.tasks()
            for tk in t.get("task_done", []):
                if tk.get("file_name") == file_name and tk.get("task_type") == 2:
                    return tk
            doing = t.get("task_doing", [])
            for d in doing:
                if d.get("file_name") == file_name and on_progress:
                    on_progress(file_name, d.get("progress", "?"))
            time.sleep(poll)
        raise TimeoutError(f"AutoPanel download timeout: {file_name}")
