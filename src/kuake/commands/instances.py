"""List AutoDL instances with their current power status.

--json 走 AutoDL API 直查 (快 + 结构化, 给 CC/Codex 解析)。
默认走 DOM scrape (人类可读)。
"""
from __future__ import annotations

import json

from kuake.config import config_paths
from kuake.errors import ConfigMissing, NetworkError
from kuake.progress import console, info, set_json_mode


def run(json_output: bool = False) -> None:
    paths = config_paths()
    if not paths.storage_state.exists():
        raise ConfigMissing(
            f"storage_state missing: {paths.storage_state}; run `kuake init` first"
        )

    if json_output:
        set_json_mode(True)
        # API path: 快 + 结构化
        from kuake.autodl_api import AutoDLClient, load_jwt_from_storage_state
        try:
            client = AutoDLClient(jwt=load_jwt_from_storage_state())
            api_list = client.list_instances()
        except NetworkError as e:
            raise ConfigMissing(str(e)) from e
        out = [{
            "index": i + 1,
            "uuid": inst.get("uuid", ""),
            "machine_alias": inst.get("machine_alias", ""),
            "region_name": inst.get("region_name", ""),
            "gpu_name": inst.get("snapshot_gpu_alias_name", ""),
            "gpu_count": inst.get("req_gpu_amount", 1),
            "status": inst.get("status", ""),
            "image": inst.get("image", ""),
        } for i, inst in enumerate(api_list)]
        print(json.dumps(out, ensure_ascii=False))
        return

    from kuake.browser import autodl_actions
    from kuake.browser.session import launch_browser

    info("启动 headless 浏览器查询实例列表...")
    with launch_browser(headless=True, storage_state=paths.storage_state) as (ctx, _p):
        page = ctx.new_page()
        rows = autodl_actions.list_full(page)

    console.print("\n[bold]AutoDL 实例:[/bold]")
    for i, r in enumerate(rows, 1):
        first_line = r["label"].splitlines()[0][:80] if r["label"] else ""
        status = r["status"]
        color = "green" if any(k in status for k in ("运行", "已开", "Running")) else "yellow"
        console.print(f"  [{i}] [{color}]{status}[/{color}]  {first_line}")
