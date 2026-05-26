"""Show AutoDL user info + wallet balance (read-only)."""
from __future__ import annotations

import json

from kuake.autodl_api import AutoDLClient, load_jwt_from_storage_state
from kuake.errors import ConfigMissing, NetworkError
from kuake.progress import console, info, ok, set_json_mode


def run(json_output: bool = False) -> None:
    if json_output:
        set_json_mode(True)

    try:
        jwt = load_jwt_from_storage_state()
    except NetworkError as e:
        raise ConfigMissing(str(e)) from e

    client = AutoDLClient(jwt=jwt)
    try:
        wallet = client.wallet_balance()
    except Exception as e:  # 钱包查询失败不阻断,显示 0 实例就行
        info(f"无法查钱包: {e}")
        wallet = {}

    try:
        instances = client.list_instances()
    except Exception as e:
        info(f"无法列实例: {e}")
        instances = []

    running = sum(1 for i in instances if i.get("status") == "running")

    if json_output:
        out = {
            "wallet": {
                "assets_yuan": wallet.get("assets", 0) / 100,
                "blocked_asset_yuan": wallet.get("blocked_asset", 0) / 100,
                "accumulate_yuan": wallet.get("accumulate", 0) / 100,
                "voucher_balance_yuan": wallet.get("voucher_balance", 0) / 100,
                "available_coupon_num": wallet.get("available_coupon_num", 0),
            },
            "instances": {
                "total": len(instances),
                "running": running,
            },
        }
        print(json.dumps(out, ensure_ascii=False))
        return

    console.print()
    ok("AutoDL 账号信息")
    if wallet:
        # 字段 (已通过真账号确认): assets, blocked_asset, accumulate, voucher_balance — 分
        assets = wallet.get("assets", 0) / 100
        blocked = wallet.get("blocked_asset", 0) / 100
        accumulate = wallet.get("accumulate", 0) / 100
        voucher = wallet.get("voucher_balance", 0) / 100
        coupon_num = wallet.get("available_coupon_num", 0)
        console.print(f"  现金余额  : ¥{assets:.2f}")
        if blocked > 0:
            console.print(f"  冻结金额  : ¥{blocked:.2f}")
        if voucher > 0:
            console.print(f"  代金券余额: ¥{voucher:.2f}")
        if coupon_num:
            console.print(f"  可用优惠券: {coupon_num} 张")
        console.print(f"  累计消费  : ¥{accumulate:.2f}")
    else:
        console.print("  [dim]钱包数据未读取[/dim]")

    console.print(f"  实例总数  : {len(instances)} (运行中 {running} 台)")
