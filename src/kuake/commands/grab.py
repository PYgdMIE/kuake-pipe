"""Poll AutoDL market for GPU/CPU/region matches and build a create PLAN.

v0.4+: 默认 dry-run, **绝不下单**。
- 找到匹配机器后,生成完整 POST 请求 body
- 打印 plan 供你审计
- 落盘到 ~/.kuake/plans/<timestamp>.json
- 想真下单, 跑 `kuake confirm-create --plan-file ...`(需要二次确认 + 已扣费风险提示)

Usage:
  kuake grab                            # 任何 GPU,任何区,1 张空闲
  kuake grab --gpu "RTX 5090"           # 仅 RTX 5090
  kuake grab --gpu "RTX PRO 6000" --gpu "RTX 5090"
  kuake grab --any-region               # 显式声明不限制区(其实默认就不限)
  kuake grab --region west-B --region west-D
  kuake grab --cpu-ok                   # 也接受 CPU
  kuake grab --min-idle 2               # 至少 2 张空闲卡
  kuake grab --gpu-count 2              # 创建时要 2 张
  kuake grab --expand-data-disk 100     # 扩 100 GB 数据盘
  kuake grab --system-disk-expand 20    # 扩 20 GB 系统盘
  kuake grab --poll 3 --max-iter 100
"""
from __future__ import annotations

import time
from datetime import datetime

from kuake.autodl_api import AutoDLClient, load_jwt_from_storage_state
from kuake.autodl_planner import (
    InstancePlan,
    format_plan,
    plan_from_match,
    save_plan,
)
from kuake.config import config_paths
from kuake.errors import ConfigMissing, NetworkError
from kuake.progress import console, info, ok, warn


def run(
    gpu_types: list[str] | None = None,
    regions: list[str] | None = None,
    cpu_ok: bool = False,
    min_idle_gpu: int = 1,
    gpu_count: int = 1,
    expand_data_disk_gb: int = 0,
    system_disk_change_size_gb: int = 0,
    image: str | None = None,
    poll_seconds: int = 5,
    max_iterations: int = 0,
    **_legacy_flags,  # 吞掉旧的 dry_run / auto_create
) -> None:
    """Poll until matching machine found, build PLAN, print + save, exit (no submit)."""
    try:
        jwt = load_jwt_from_storage_state()
    except NetworkError as e:
        raise ConfigMissing(str(e)) from e

    client = AutoDLClient(jwt=jwt)

    target = f"GPU={gpu_types or 'any'}, region={regions or 'any'}, min_idle={min_idle_gpu}"
    if cpu_ok:
        target += ", CPU 也接受"
    info(f"轮询 AutoDL 市场: {target} (每 {poll_seconds}s)")
    info(f"匹配后生成 PLAN (gpu_count={gpu_count}, "
         f"+{expand_data_disk_gb}G 数据盘, +{system_disk_change_size_gb}G 系统盘)")
    info("⚠ 仅生成 plan,不下单。Ctrl+C 退出。")

    it = 0
    while True:
        it += 1
        try:
            matches = client.list_available(
                gpu_type_names=gpu_types,
                region_sign_list=regions,
                min_idle_gpu=min_idle_gpu,
            )
        except NetworkError as e:
            warn(f"poll #{it}: {e}")
            if max_iterations and it >= max_iterations:
                return
            time.sleep(poll_seconds)
            continue

        if not cpu_ok:
            matches = [m for m in matches if m.chip_corp.lower() != "cpu"]

        if matches:
            console.print()
            ok(f"找到 {len(matches)} 台匹配:")
            for m in matches:
                console.print(f"  • {m}")

            chosen = matches[0]
            plan = plan_from_match(
                chosen,
                gpu_count=gpu_count,
                image=image,
                expand_data_disk_gb=expand_data_disk_gb,
                system_disk_change_size_gb=system_disk_change_size_gb,
            )
            _output_plan(plan)
            return

        console.print(f"[dim]poll #{it}: 暂无匹配 ({poll_seconds}s 后重试)[/dim]",
                      end="\r")
        if max_iterations and it >= max_iterations:
            console.print()
            warn(f"达到最大轮询次数 ({max_iterations}),退出")
            return
        time.sleep(poll_seconds)


def _output_plan(plan: InstancePlan) -> None:
    console.print(format_plan(plan))
    # 落盘
    plans_dir = config_paths().home / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    plan_path = plans_dir / f"plan_{stamp}.json"
    save_plan(plan, str(plan_path))
    ok(f"PLAN 已落盘: {plan_path}")
    info("→ 真下单需要: kuake confirm-create --plan-file " + str(plan_path))
