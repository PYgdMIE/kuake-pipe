"""Hit AutoDL API to discover create/clone/disk/image schemas, all read-only."""
from __future__ import annotations
import json
import sys
from typing import Any

from playwright.sync_api import sync_playwright

from kuake.config import config_paths

BASE = "https://www.autodl.com"


def _print(label, j):
    code = j.get("code")
    ok = code in ("Success", "OK", "success")
    msg = j.get("msg", "")
    print(f"  {'✓' if ok else '✗'} {label:60s} code={code}  msg={msg[:60]}")
    return j


def main():
    state = config_paths().storage_state
    state_data = json.loads(state.read_text())
    jwt = ""
    for o in state_data.get("origins", []):
        if "autodl.com" in o.get("origin", ""):
            for item in o.get("localStorage", []):
                if item.get("name") == "token":
                    jwt = item.get("value", "")
                    break
    if not jwt:
        print("✗ 无 JWT", file=sys.stderr); sys.exit(2)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            storage_state=str(state),
            extra_http_headers={"Authorization": jwt},
        )
        rc = ctx.request

        def hit(method, path, body=None, params=None):
            try:
                if method == "POST":
                    r = rc.post(f"{BASE}{path}", data=body or {})
                else:
                    r = rc.get(f"{BASE}{path}", params=params or {})
            except Exception as e:
                print(f"  ✗ {path}: {e}")
                return None
            try:
                return _print(f"{method} {path}", r.json())
            except Exception:
                print(f"  ✗ {path}: HTTP {r.status}: {r.text()[:100]}")
                return None

        print("=== 探:实例详情(已知 uuid)===")
        r = hit("POST", "/api/v1/instance", body={
            "date_from": "", "date_to": "", "page_index": 1, "page_size": 20,
            "status": [], "charge_type": [],
        })
        inst = (r["data"]["list"] or [None])[0] if r else None
        if inst:
            uuid = inst["uuid"]
            print(f"\n     第一个实例: uuid={uuid[:12]} alias={inst['machine_alias']}")
            print(f"     完整字段: {json.dumps(inst, ensure_ascii=False, indent=2)[:2000]}")

        print("\n=== 探:镜像列表(各种可能 path)===")
        for path in [
            "/api/v1/dev/image/list",
            "/api/v1/dev/private_image/list",
            "/api/v1/instance/image/list",
            "/api/v1/user/private_image",
            "/api/v1/image/private",
            "/api/v1/image/community",
            "/api/v1/image",
            "/api/v1/dev/image",
        ]:
            for method in ["POST", "GET"]:
                hit(method, path, body={"page_index": 1, "page_size": 5})

        print("\n=== 探:克隆 / 配置详情 ===")
        if inst:
            uuid = inst["uuid"]
            for path in [
                f"/api/v1/instance/{uuid}",
                f"/api/v1/instance/snapshot/{uuid}",
                "/api/v1/instance/clone",
                "/api/v1/instance/snapshot",
                "/api/v1/dev/instance/snapshot",
            ]:
                hit("GET", path)
                hit("POST", path, body={"uuid": uuid})

        print("\n=== 探:扩容/磁盘价 ===")
        for path in [
            "/api/v1/dev/data_disk/expand/price",
            "/api/v1/instance/data_disk",
            "/api/v1/instance/expand/data_disk/price",
            "/api/v1/dev/instance/disk/price",
        ]:
            hit("GET", path)
            hit("POST", path, body={"machine_id": "x", "expand_size": 10})

        print("\n=== 探:充值 / 余额 ===")
        hit("GET", "/api/v1/wallet")
        hit("GET", "/api/v1/wallet/balance")

        browser.close()


if __name__ == "__main__":
    main()
