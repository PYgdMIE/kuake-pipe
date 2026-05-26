"""Probe AutoDL API endpoints via Playwright's request context (preserves CSRF/JWT).

Run: .venv/bin/python scripts/probe_autodl_api.py
"""
from __future__ import annotations
import json
import sys
from typing import Any

from playwright.sync_api import sync_playwright

from kuake.config import config_paths

BASE = "https://www.autodl.com"


def _probe(rc, method: str, path: str, body: dict | None = None,
           label: str | None = None) -> Any:
    label = label or path
    url = f"{BASE}{path}"
    try:
        if method == "POST":
            r = rc.post(url, data=body or {})
        else:
            r = rc.get(url, params=body or {})
    except Exception as e:
        print(f"  ✗ {label}: {e}")
        return None
    try:
        j = r.json()
    except Exception:
        print(f"  ✗ {label}: HTTP {r.status}, body: {r.text()[:200]}")
        return None
    code = j.get("code")
    ok = code in ("Success", "OK", "success")
    msg = j.get("msg", "")
    data = j.get("data")
    n_items = (
        len(data.get("list", [])) if isinstance(data, dict) and "list" in data
        else len(data) if isinstance(data, list)
        else "—"
    )
    print(f"  {'✓' if ok else '✗'} {label:50s} code={code}  items={n_items}  msg={msg[:50]}")
    return j


def main():
    state = config_paths().storage_state
    if not state.exists():
        print(f"✗ storage_state missing: {state}", file=sys.stderr)
        sys.exit(2)

    # 提取 JWT (在 localStorage.token)
    state_data = json.loads(state.read_text())
    jwt = ""
    for o in state_data.get("origins", []):
        if "autodl.com" in o.get("origin", ""):
            for item in o.get("localStorage", []):
                if item.get("name") == "token":
                    jwt = item.get("value", "")
                    break
    if not jwt:
        print("✗ 未在 storage_state 找到 AutoDL JWT (localStorage.token)", file=sys.stderr)
        sys.exit(2)
    print(f"✓ JWT 拿到 (len={len(jwt)})")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            storage_state=str(state),
            extra_http_headers={"Authorization": jwt},
        )
        rc = ctx.request

        print("=== 用户 / 实例 ===")
        r = _probe(rc, "POST", "/api/v1/instance", body={
            "date_from": "", "date_to": "", "page_index": 1, "page_size": 20,
            "status": [], "charge_type": [],
        }, label="instance/list")
        if r and r.get("data"):
            for inst in (r["data"].get("list") or [])[:5]:
                uuid = inst.get('uuid', '?')[:8]
                print(f"     uuid={uuid}.. alias={inst.get('machine_alias','?')} "
                      f"status={inst.get('status','?')} "
                      f"gpu={inst.get('snapshot_gpu_name','?')} "
                      f"image_uuid={inst.get('image_uuid','?')[:12]}")

        print("\n=== 市场列表 PayG ===")
        r = _probe(rc, "POST", "/api/v1/user/machine/list", body={
            "charge_type": "payg", "region_sign": "", "gpu_type_name": [],
            "machine_tag_name": [], "gpu_idle_num": 1, "mount_net_disk": False,
            "instance_disk_size_order": "", "date_range": "", "date_from": "", "date_to": "",
            "page_index": 1, "page_size": 5, "pay_price_order": "",
            "gpu_idle_type": "", "default_order": True, "region_sign_list": [],
        }, label="user/machine/list (payg)")
        if r and r.get("data"):
            for m in (r["data"].get("list") or [])[:5]:
                print(f"     {m.get('region_name','?')}/{m.get('machine_alias','?')} "
                      f"GPU={m.get('gpu_name','?')} "
                      f"idle={m.get('gpu_idle_num',0)}/{m.get('gpu_number',0)} "
                      f"machine_id={m.get('machine_id','?')[:12]}")

        print("\n=== 镜像列表 (社区 / 私有 / 公共) ===")
        r = _probe(rc, "POST", "/api/v1/private_image/list",
                   body={"page_index": 1, "page_size": 10}, label="private_image/list")
        if r and r.get("data"):
            for img in (r["data"].get("list") or [])[:5]:
                print(f"     [私有] uuid={img.get('uuid','?')[:12]}.. "
                      f"name={img.get('name','?')} cuda={img.get('cuda','?')}")
        r = _probe(rc, "POST", "/api/v1/community/image/list",
                   body={"page_index": 1, "page_size": 10, "tag_id_list": []},
                   label="community/image/list")
        if r and r.get("data"):
            for img in (r["data"].get("list") or [])[:5]:
                print(f"     [社区] uuid={img.get('uuid','?')[:12]}.. "
                      f"name={img.get('name','?')} cuda={img.get('cuda','?')}")
        # 试试 public image (官方)
        _probe(rc, "POST", "/api/v1/image/list",
               body={"page_index": 1, "page_size": 10}, label="image/list (public)")

        print("\n=== 区域 / GPU 类型 ===")
        _probe(rc, "GET", "/api/v1/region/list", label="region/list")
        r = _probe(rc, "POST", "/api/v1/machine/region/gpu_type",
                   body={"charge_type": "payg"}, label="machine/region/gpu_type")
        if r and r.get("data"):
            data = r["data"]
            if isinstance(data, list):
                seen = set()
                for entry in data[:30]:
                    gpu = entry.get("gpu_name") or entry.get("gpu_type_name")
                    seen.add(gpu)
                print(f"     GPU 类型样本: {sorted(seen)[:15]}")

        print("\n=== 扩容 / 数据盘 ===")
        _probe(rc, "GET", "/api/v1/instance/data_disk/expand/price/info",
               label="data_disk/expand/price/info")
        _probe(rc, "GET", "/api/v1/instance/system_disk/expand/price",
               label="system_disk/expand/price")

        print("\n=== 优惠券 ===")
        _probe(rc, "POST", "/api/v1/coupon/list",
               body={"page_index": 1, "page_size": 5, "scene": "instance_create"},
               label="coupon/list")

        print("\n=== 克隆 ===")
        # 先随便挑一个实例,看克隆 info 长啥样 (read-only)
        r = _probe(rc, "POST", "/api/v1/instance", body={
            "date_from": "", "date_to": "", "page_index": 1, "page_size": 1,
            "status": [], "charge_type": [],
        }, label="instance/list (for clone probe)")
        if r and r.get("data"):
            instances = r["data"].get("list") or []
            if instances:
                inst_uuid = instances[0].get("uuid", "")
                if inst_uuid:
                    print(f"     用 instance uuid={inst_uuid[:12]} 试 clone info...")
                    _probe(rc, "GET", "/api/v1/instance/clone/info",
                           body={"uuid": inst_uuid}, label="instance/clone/info?uuid=...")

        browser.close()


if __name__ == "__main__":
    main()
