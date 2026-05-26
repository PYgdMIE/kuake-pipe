"""Drive AutoDL create-instance UI via Playwright, intercept all /api/v1/ calls.

只观察,不点最后下单按钮。输出 trace 文件供分析真实 endpoint。
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from kuake.config import config_paths

BASE = "https://www.autodl.com"
TRACE_FILE = Path("/tmp/kuake-autodl-trace.jsonl")


def main():
    state = config_paths().storage_state
    if not state.exists():
        print(f"✗ storage_state missing: {state}", file=sys.stderr)
        sys.exit(2)

    events = []

    def on_request(req):
        url = req.url
        if "/api/v1/" not in url:
            return
        body = ""
        try:
            body = req.post_data or ""
            if len(body) > 600:
                body = body[:600] + "...(truncated)"
        except Exception:
            pass
        events.append({
            "type": "req",
            "ts": time.time(),
            "method": req.method,
            "url": url.split("?")[0],
            "query": url.split("?", 1)[1] if "?" in url else "",
            "body": body,
        })

    def on_response(resp):
        url = resp.url
        if "/api/v1/" not in url:
            return
        body = ""
        try:
            ct = (resp.headers.get("content-type") or "").lower()
            if "json" in ct:
                body = resp.text()
                if len(body) > 600:
                    body = body[:600] + "...(truncated)"
        except Exception:
            pass
        events.append({
            "type": "resp", "ts": time.time(),
            "status": resp.status, "url": url.split("?")[0],
            "body": body,
        })

    if TRACE_FILE.exists():
        TRACE_FILE.unlink()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(storage_state=str(state))
        ctx.on("request", on_request)
        ctx.on("response", on_response)
        page = ctx.new_page()

        print("[1] 打开 console/instance 列表")
        page.goto(f"{BASE}/console/instance/list", wait_until="domcontentloaded",
                  timeout=60000)
        page.wait_for_timeout(3000)

        print("[2] 点 创建实例 (导航到购买/创建页面)")
        # 优先找侧栏 / 顶部入口
        clicked = False
        for selector_or_text in [
            "我要租用",
            "新建实例",
            "立即购买",
            "创建实例",
        ]:
            try:
                btn = page.get_by_text(selector_or_text, exact=False).first
                if btn.count():
                    btn.click(timeout=4000)
                    clicked = True
                    print(f"  ✓ 点了 [{selector_or_text}]")
                    break
            except Exception:
                pass
        if not clicked:
            print("  ⚠ 没找到入口, 改直接 goto /market/list")
            page.goto(f"{BASE}/market/list", wait_until="domcontentloaded",
                      timeout=30000)
        page.wait_for_timeout(4000)

        print("[3] 在 market 列表上点第一个有空闲的机器")
        # 试看页面上有没有可用机器卡片 + 立即购买按钮
        try:
            buy_btn = page.get_by_text("立即购买", exact=False).first
            if buy_btn.count():
                buy_btn.click(timeout=5000)
                print("  ✓ 点了 立即购买 进入实例配置页")
                page.wait_for_timeout(5000)
            else:
                print("  ⚠ 当前没空闲机器, 无法进配置页")
        except Exception as e:
            print(f"  ⚠ 点 立即购买 失败: {e}")

        print("[4] 在配置页停 12 秒, 让用户/页面自己滚动展示镜像/数据盘/扩容选项")
        page.wait_for_timeout(12000)

        # 落盘
        with open(TRACE_FILE, "w") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        print(f"\n✓ trace 写入 {TRACE_FILE} ({len(events)} 事件)")

        # 按 URL 聚合
        urls = {}
        for ev in events:
            url = ev.get("url", "?")
            urls.setdefault(url, {"req": 0, "resp": 0, "ok": 0})
            if ev["type"] == "req":
                urls[url]["req"] += 1
            else:
                urls[url]["resp"] += 1
                if 200 <= ev.get("status", 0) < 300:
                    urls[url]["ok"] += 1

        print("\n按 endpoint 统计:")
        for url, c in sorted(urls.items()):
            print(f"  {url:60s} req={c['req']:2d} ok={c['ok']:2d}")

        browser.close()


if __name__ == "__main__":
    main()
