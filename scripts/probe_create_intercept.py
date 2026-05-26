"""Intercept the real AutoDL create-instance POST without actually submitting.

用法:
  python scripts/probe_create_intercept.py

行为:
  1. 用 storage_state 打开 headed Chromium 到 AutoDL 算力市场
  2. route 拦截 /api/v1/order/instance/create/payg
  3. 你手动选机器 → 立即购买 → 配置 → 点最后那个 立即购买 / 创建按钮
  4. 拦到 POST 立刻 abort + 打印 body,AutoDL 永远收不到这一发,不扣费
  5. 退出
"""
from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

from kuake.config import config_paths

BASE = "https://www.autodl.com"
TARGET_PATH = "/api/v1/order/instance/create/payg"


def main() -> int:
    state = config_paths().storage_state
    if not state.exists():
        print(f"✗ storage_state missing: {state}", file=sys.stderr)
        return 2

    captured: list[dict] = []

    def handle_route(route, request):
        body_raw = request.post_data or ""
        try:
            body = json.loads(body_raw)
        except Exception:
            body = body_raw
        captured.append({
            "headers": dict(request.headers),
            "body": body,
        })
        print("\n" + "=" * 60)
        print("捕获到 create POST,abort 中(不会真发到 AutoDL)")
        print("=" * 60)
        print(json.dumps(body, ensure_ascii=False, indent=2))
        print("=" * 60)
        route.abort()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(storage_state=str(state))
        ctx.route(f"**{TARGET_PATH}", handle_route)
        page = ctx.new_page()

        print(f"打开 {BASE}/market/list — 你自己点机器 → 立即购买 → 配置 → 点最后的购买按钮")
        page.goto(f"{BASE}/market/list", wait_until="domcontentloaded", timeout=60000)
        print("等你操作(最多 5 分钟,Ctrl+C 提前停)...")

        for _ in range(300):  # 5 min budget
            if captured:
                break
            page.wait_for_timeout(1000)

        if captured:
            print(f"\n✓ 抓到 {len(captured)} 次 POST,保存到 trace 文件")
            trace = config_paths().home / "create_payload.json"
            with open(trace, "w", encoding="utf-8") as f:
                json.dump(captured[-1], f, ensure_ascii=False, indent=2)
            print(f"  → {trace}")
        else:
            print("\n✗ 5 分钟内没拦到 — 退出")

        browser.close()
    return 0 if captured else 1


if __name__ == "__main__":
    sys.exit(main())
