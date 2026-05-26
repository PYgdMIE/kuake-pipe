"""AutoDL.com web API client (separate from AutoPanel).

Discovered endpoints (2026-05):
  POST /api/v1/instance              — list user's existing instances
  POST /api/v1/user/machine/list     — list available machines (filter by region/GPU)
  POST /api/v1/machine/region/gpu_type — region-level GPU quotas
  GET  /api/v1/region/list           — region enum
  POST /api/v1/order/instance/create/payg — create PAYG instance (BILLED!)

Auth: 需要 JWT in `Authorization` header(在 localStorage.token 里),
单纯 cookies 不够,会 `AuthorizeFailed: 登录超时`。

用法:
  from kuake.autodl_api import AutoDLClient, load_jwt_from_storage_state
  client = AutoDLClient(jwt=load_jwt_from_storage_state())
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from kuake.errors import NetworkError

AUTODL_BASE = "https://www.autodl.com"


def load_jwt_from_storage_state(storage_state_path: Path | None = None) -> str:
    """从 Playwright storage_state JSON 抽取 localStorage.token (AutoDL JWT)。

    storage_state_path 默认走 KUAKE_HOME/state/storage_state.json。
    """
    if storage_state_path is None:
        from kuake.config import config_paths
        storage_state_path = config_paths().storage_state
    if not storage_state_path.exists():
        raise NetworkError(
            f"storage_state missing: {storage_state_path}; run `kuake init` first"
        )
    data = json.loads(storage_state_path.read_text(encoding="utf-8"))
    for o in data.get("origins", []):
        if "autodl.com" in o.get("origin", ""):
            for item in o.get("localStorage", []):
                if item.get("name") == "token":
                    return item.get("value", "")
    raise NetworkError(
        "未在 storage_state.localStorage 找到 AutoDL token — 跑 `kuake init` 重扫"
    )


@dataclass
class MachineMatch:
    machine_id: str
    machine_alias: str
    region_name: str
    region_sign: str
    gpu_name: str
    gpu_total: int
    gpu_idle: int
    chip_corp: str  # 'nvidia' / 'cpu'
    payg_price: int = 0          # 单位:厘,即 1/1000 元(API 原样字段)
    cpu_limit: int = 0
    mem_limit_in_byte: int = 0
    raw: dict[str, Any] | None = None  # 原始 dict (含未明确暴露字段)

    def __str__(self) -> str:
        price_yuan = self.payg_price / 1000 if self.payg_price else 0
        return (
            f"{self.region_name}/{self.machine_alias}  "
            f"{self.gpu_name} ({self.gpu_idle}/{self.gpu_total} free)  "
            f"¥{price_yuan:.2f}/h"
        )


class AutoDLClient:
    """Lightweight client for the AutoDL.com web API."""

    def __init__(self, jwt: str | None = None, cookies: dict | None = None,
                 timeout: int = 15):
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
        if jwt:
            self.s.headers["Authorization"] = jwt
        self.timeout = timeout

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = self.s.post(f"{AUTODL_BASE}{path}", json=body, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"AutoDL {path} failed: {e}") from e
        r.raise_for_status()
        j = r.json()
        if j.get("code") not in ("Success", "OK", "success"):
            raise NetworkError(f"AutoDL {path}: {j.get('msg')} (code={j.get('code')})")
        return j.get("data") or {}

    def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            r = self.s.get(f"{AUTODL_BASE}{path}", params=params or {},
                           timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"AutoDL {path} failed: {e}") from e
        r.raise_for_status()
        j = r.json()
        if j.get("code") not in ("Success", "OK", "success"):
            raise NetworkError(f"AutoDL {path}: {j.get('msg')} (code={j.get('code')})")
        return j.get("data") or {}

    def list_instances(self, page_size: int = 50) -> list[dict]:
        """List user's existing AutoDL instances (full detail dict per item)."""
        data = self._post("/api/v1/instance", {
            "date_from": "", "date_to": "", "page_index": 1, "page_size": page_size,
            "status": [], "charge_type": [],
        })
        return data.get("list") or []

    def get_instance(self, uuid: str) -> dict | None:
        """Get one instance by uuid (returned shape same as list entry).
        Returns None if not found."""
        for inst in self.list_instances():
            if inst.get("uuid") == uuid:
                return inst
        return None

    def wallet_balance(self) -> dict:
        """Returns wallet info {balance_xxx, ...} for dry-run cost preview."""
        return self._get("/api/v1/wallet/balance")

    # ── Default Docker images per chip (PyTorch latest) ─────────────────
    DEFAULT_IMAGE_NVIDIA = (
        "hub.kce.ksyun.com/autodl-image/torch:"
        "cuda12.8-cudnn-devel-ubuntu22.04-py312-torch2.8.0"
    )
    DEFAULT_IMAGE_CPU = (
        "hub.kce.ksyun.com/autodl-image/miniconda3:"
        "py311-ubuntu22.04"
    )

    def create_payg_instance(
        self,
        machine_id: str,
        req_gpu_amount: int = 1,
        image: str | None = None,
        chip_corp: str = "nvidia",
    ) -> dict:
        """POST /api/v1/order/instance/create/payg — create a pay-as-you-go instance.
        Returns the response data (instance details on success).

        WARNING: This actually creates a billed instance. Use only when sure.
        Full body schema may include more fields — fill in as discovered."""
        if image is None:
            image = self.DEFAULT_IMAGE_CPU if chip_corp == "cpu" else self.DEFAULT_IMAGE_NVIDIA
        body = {
            "instance_info": {
                "machine_id": machine_id,
                "charge_type": "payg",
                "req_gpu_amount": req_gpu_amount,
                "image": image,
                "private_image_uuid": "",
                "reproduction_uuid": "",
                "cg_application_uuid": "",
                "cg_application_info": {"app_name": "", "current_version": ""},
                "expand_data_disk": 0,
                "system_disk_change_size": 0,
                "coupon_id_list": [],
                "duration": 1,
                "num": 1,
            },
        }
        try:
            r = self.s.post(
                f"{AUTODL_BASE}/api/v1/order/instance/create/payg",
                json=body, timeout=self.timeout,
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"AutoDL create instance failed: {e}") from e
        r.raise_for_status()
        j = r.json()
        if j.get("code") not in ("Success", "OK", "success"):
            raise NetworkError(f"AutoDL create instance error: {j}")
        return j.get("data", {})

    def list_available(
        self,
        gpu_type_names: list[str] | None = None,
        region_sign_list: list[str] | None = None,
        min_idle_gpu: int = 1,
        charge_type: str = "payg",
        page_size: int = 20,
    ) -> list[MachineMatch]:
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
        out: list[MachineMatch] = []
        for m in items:
            idle = int(m.get("gpu_idle_num", 0))
            if idle >= min_idle_gpu:
                out.append(MachineMatch(
                    machine_id=m.get("machine_id", ""),
                    machine_alias=m.get("machine_alias", ""),
                    region_name=m.get("region_name", ""),
                    region_sign=m.get("region_sign", ""),
                    gpu_name=m.get("gpu_name", ""),
                    gpu_total=int(m.get("gpu_number", 0)),
                    gpu_idle=idle,
                    chip_corp=m.get("chip_corp", ""),
                    payg_price=int(m.get("payg_price", 0)),
                    cpu_limit=int(m.get("cpu_limit", 0)),
                    mem_limit_in_byte=int(m.get("mem_limit_in_byte", 0)),
                    raw=m,
                ))
        return out
