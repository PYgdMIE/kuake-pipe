"""A1-1: 用 Playwright 抓 pan.quark.cn 网页版上传一个小文件,完整记录所有
请求/响应,作为后续逆向 endpoint 和签名方案的依据。

输出:
- trace.jsonl: 一行一个 request/response 事件
- session.har:  完整 HAR 格式(浏览器原生可读)
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from kuake.config import config_paths


def main():
    paths = config_paths()
    if not paths.storage_state.exists():
        print(f"✗ storage_state 不存在: {paths.storage_state}", file=sys.stderr)
        print("  请先运行 kuake init", file=sys.stderr)
        sys.exit(2)

    # 准备 1 个小测试文件 (5KB,小于 5MB 单分片路径)
    probe_dir = Path("/tmp/kuake-probe-upload")
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe_small = probe_dir / f"probe_{int(time.time())}.bin"
    probe_small.write_bytes(os.urandom(5 * 1024))
    print(f"测试文件: {probe_small} ({probe_small.stat().st_size} bytes)")

    trace_file = Path("/tmp/kuake-probe-trace.jsonl")
    har_file = Path("/tmp/kuake-probe.har")
    if trace_file.exists():
        trace_file.unlink()

    INTEREST_HOSTS = (
        "drive-pc.quark.cn", "drive-pc-pds.quark.cn",
        "aliyunpds.com", "aliyuncs.com", "uc.cn", "quark.cn",
    )

    def interesting(url: str) -> bool:
        return any(h in url for h in INTEREST_HOSTS)

    events = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            storage_state=str(paths.storage_state),
            record_har_path=str(har_file),
        )

        def on_request(req):
            if not interesting(req.url):
                return
            body = None
            try:
                body = req.post_data
                if body and len(body) > 2000:
                    body = body[:2000] + "...(truncated)"
            except Exception:
                pass
            events.append({
                "type": "req",
                "ts": time.time(),
                "method": req.method,
                "url": req.url,
                "headers": dict(req.headers),
                "post_data": body,
                "resource_type": req.resource_type,
            })

        def on_response(resp):
            if not interesting(resp.url):
                return
            body = None
            try:
                ct = (resp.headers.get("content-type") or "").lower()
                if any(k in ct for k in ("json", "xml", "text")):
                    body = resp.text()
                    if body and len(body) > 2000:
                        body = body[:2000] + "...(truncated)"
            except Exception:
                pass
            events.append({
                "type": "resp",
                "ts": time.time(),
                "status": resp.status,
                "url": resp.url,
                "headers": dict(resp.headers),
                "body": body,
            })

        ctx.on("request", on_request)
        ctx.on("response", on_response)

        page = ctx.new_page()

        print("[1] 打开 pan.quark.cn ...")
        page.goto("https://pan.quark.cn/", wait_until="domcontentloaded",
                  timeout=30000)
        # 等 SPA 渲染
        page.wait_for_timeout(5000)

        # 检查登录态
        if "登录" in page.content() or "扫码" in page.content():
            print("⚠ 没登录,需要先扫码")
            input("扫码登录后按回车继续...")

        print("[2] 导航到 /我的备份/.../UPLOAD/")
        # 直接用 SPA URL hash 跳: pan.quark.cn 用 fid 而非路径
        # 这里偷懒: 用前端搜索找 UPLOAD 目录,点进去
        try:
            # 找侧栏的"我的备份"
            page.get_by_text("我的备份", exact=False).first.click(timeout=10000)
            page.wait_for_timeout(2000)
            # 找电脑备份目录(名字带 Internati)
            elem = page.get_by_text("电脑备份", exact=False).first
            elem.dblclick(timeout=10000)
            page.wait_for_timeout(2000)
            page.get_by_text("UPLOAD", exact=False).first.dblclick(timeout=10000)
            page.wait_for_timeout(2000)
            print("  ✓ 进到 UPLOAD 目录")
        except Exception as e:
            print(f"⚠ 自动导航失败: {e}")
            input("请手动导航到目标 UPLOAD 目录后按回车继续...")

        print("[3] 触发文件上传 (用 input[type=file] 注入路径)")
        # 大部分 SPA 上传都有个隐藏的 input[type=file]
        try:
            file_inputs = page.locator('input[type="file"]').all()
            print(f"  找到 {len(file_inputs)} 个 file input")
            if file_inputs:
                file_inputs[0].set_input_files(str(probe_small))
                print(f"  ✓ 注入 {probe_small.name}")
            else:
                input("没找到 file input,请手动点上传按钮选择文件后按回车...")
        except Exception as e:
            print(f"⚠ 注入失败: {e}")
            input(f"请手动上传 {probe_small} 后按回车...")

        print("[4] 等待上传完成 (最多 60s)")
        deadline = time.time() + 60
        seen_finish = False
        while time.time() < deadline:
            for ev in events:
                if ev.get("type") == "resp" and "/file/upload_finish" in ev.get("url", ""):
                    seen_finish = True
                    break
            if seen_finish:
                break
            page.wait_for_timeout(2000)
        if seen_finish:
            print("  ✓ upload_finish 收到")
        else:
            print("  ⚠ 60s 没等到 upload_finish, 继续保存已抓到的")

        page.wait_for_timeout(3000)  # buffer
        ctx.close()
        browser.close()

    # 持久化
    with open(trace_file, "w") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(f"\n✓ trace 写入 {trace_file} ({len(events)} 个事件)")
    print(f"✓ HAR 写入 {har_file}")
    # 简要 stats
    hosts = {}
    for ev in events:
        host = ev["url"].split("/")[2] if "://" in ev["url"] else "?"
        hosts.setdefault(host, {"req": 0, "resp": 0})
        hosts[host][ev["type"]] = hosts[host].get(ev["type"], 0) + 1
    print("\n按 host 统计:")
    for h, c in sorted(hosts.items()):
        print(f"  {h:50s} req={c.get('req',0):3d}  resp={c.get('resp',0):3d}")


if __name__ == "__main__":
    main()
