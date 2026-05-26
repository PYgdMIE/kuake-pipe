"""Actually submit an AutoDL instance create using a saved PLAN.

二次确认 + 输 "YES" 才会真发 POST。错过任意一关都拒绝。

非交互模式 (CC/Codex/kuake auto 用): --yes 跳过 stdin 等待, 但仍打 3s grace 让
Ctrl+C 抢救。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from kuake.autodl_api import AutoDLClient, load_jwt_from_storage_state
from kuake.errors import NetworkError, UserInputError
from kuake.progress import console, info, ok, warn


def run(plan_file: str | None = None, yes: bool = False) -> str | None:
    """Confirm + submit a saved PLAN to AutoDL.

    Returns the new instance uuid on success (kuake auto 用), None if cancelled。
    """
    if not plan_file:
        raise UserInputError("缺 --plan-file <path>")
    path = Path(plan_file)
    if not path.exists():
        raise UserInputError(f"PLAN 文件不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise UserInputError(f"PLAN 文件解析失败: {e}") from e

    p = data.get("plan", {})
    payload = data.get("payload", {})
    if not payload:
        raise UserInputError("PLAN 文件缺 payload 字段,无效")

    console.print("[bold red]⚠ 你将真的下单一台 AutoDL 实例,会立刻扣费![/bold red]")
    console.print(f"  机器: {p.get('machine_alias','?')} ({p.get('region_name','?')})")
    console.print(f"  GPU : {p.get('gpu_name','?')} × {p.get('req_gpu_amount','?')}")
    console.print(f"  单价: ¥{p.get('payg_price_yuan_per_hour', 0):.2f}/小时 PayG")
    console.print(f"  镜像: {p.get('image') or '[私有] ' + p.get('private_image_uuid', '?')}")
    console.print(f"  扩容: 数据盘+{p.get('expand_data_disk',0)}G,"
                  f" 系统盘+{p.get('system_disk_change_size',0)}G")
    console.print()

    if yes:
        console.print("[bold red]⚠ --yes 模式: 3 秒后自动下单, Ctrl+C 抢救[/bold red]")
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            warn("已取消")
            return None
    else:
        console.print("[yellow]输 'YES'(大写)继续, 其它任何输入会取消:[/yellow]")
        try:
            ans = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            warn("已取消(stdin 关闭)")
            return None
        if ans != "YES":
            warn("未输入 YES → 已取消")
            return None

    try:
        jwt = load_jwt_from_storage_state()
    except NetworkError as e:
        raise UserInputError(str(e)) from e
    client = AutoDLClient(jwt=jwt)

    info("发送 POST /api/v1/order/instance/create/payg ...")
    try:
        result = client._post("/api/v1/order/instance/create/payg", payload)
    except NetworkError as e:
        raise UserInputError(f"创建失败: {e}") from e

    ok("创建成功:")
    console.print(json.dumps(result, ensure_ascii=False, indent=2))
    info("→ 跑 `kuake instances` 查看新实例")
    # API 直接返回 uuid 字符串 (历史证实)
    return result if isinstance(result, str) else None
