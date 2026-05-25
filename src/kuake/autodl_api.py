"""AutoDL.com web API client (separate from AutoPanel).

Discovered endpoints:
  POST /api/v1/user/machine/list  — list available machines (filter by region/GPU)
  POST /api/v1/machine/region/gpu_type — region-level GPU quotas
  POST /api/v1/instance/create — TBD (capture by clicking 立即购买)

Auth: relies on session cookies from a logged-in browser (AutoDL session).
Pass them via the `cookies` arg or extract from a Playwright context.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import List, Optional

import requests

from kuake.errors import NetworkError


AUTODL_BASE = "https://www.autodl.com"


@dataclass
class MachineMatch:
    machine_id: str
    machine_alias: str
    region_name: str
    gpu_name: str
    gpu_total: int
    gpu_idle: int
    chip_corp: str  # 'nvidia' / 'cpu'

    def __str__(self) -> str:
        return (
            f"{self.region_name}/{self.machine_alias}  "
            f"{self.gpu_name} ({self.gpu_idle}/{self.gpu_total} free)"
        )


class AutoDLClient:
    """Lightweight client for the AutoDL.com web API."""

    def __init__(self, cookies: Optional[dict] = None, timeout: int = 15):
        self.s = requests.Session()
        if cookies:
            for k, v in cookies.items():
                self.s.cookies.set(k, v, domain=".autodl.com")
        self.s.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": AUTODL_BASE,
            "Referer": f"{AUTODL_BASE}/market/list",
            "User-Agent": "Mozilla/5.0 (kuake-pipe) Chrome/148.0.0.0",
        })
        self.timeout = timeout

    def list_available(
        self,
        gpu_type_names: Optional[List[str]] = None,
        region_sign_list: Optional[List[str]] = None,
        min_idle_gpu: int = 1,
        charge_type: str = "payg",
        page_size: int = 20,
    ) -> List[MachineMatch]:
        """List machines matching the filters. Returns only those with
        gpu_idle_num >= min_idle_gpu."""
        body = {
            "charge_type": charge_type,
            "region_sign": "",
            "gpu_type_name": gpu_type_names or [],
            "machine_tag_name": [],
            "gpu_idle_num": min_idle_gpu,
            "mount_net_disk": False,
            "instance_disk_size_order": "",
            "date_range": "",
            "date_from": "",
            "date_to": "",
            "page_index": 1,
            "page_size": page_size,
            "pay_price_order": "",
            "gpu_idle_type": "",
            "default_order": True,
            "region_sign_list": region_sign_list or [],
        }
        try:
            r = self.s.post(
                f"{AUTODL_BASE}/api/v1/user/machine/list",
                json=body, timeout=self.timeout,
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"AutoDL market list failed: {e}") from e

        r.raise_for_status()
        try:
            j = r.json()
        except ValueError as e:
            raise NetworkError(f"AutoDL market list returned non-JSON: {e}") from e
        if j.get("code") not in ("Success", "OK", "success"):
            raise NetworkError(f"AutoDL market list error: {j}")
        items = (j.get("data", {}) or {}).get("list", []) or []
        out: List[MachineMatch] = []
        for m in items:
            idle = int(m.get("gpu_idle_num", 0))
            if idle >= min_idle_gpu:
                out.append(MachineMatch(
                    machine_id=m.get("machine_id", ""),
                    machine_alias=m.get("machine_alias", ""),
                    region_name=m.get("region_name", ""),
                    gpu_name=m.get("gpu_name", ""),
                    gpu_total=int(m.get("gpu_number", 0)),
                    gpu_idle=idle,
                    chip_corp=m.get("chip_corp", ""),
                ))
        return out
