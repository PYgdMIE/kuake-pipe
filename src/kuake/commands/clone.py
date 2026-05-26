"""Clone an existing AutoDL instance's config onto a fresh market machine.

适用场景:
- 已有实例 stop 了打不开 / 状态异常
- 想"开同款"换一台机器跑

v0.4 默认 dry-run,生成 plan 落盘,绝不下单。
"""
from __future__ import annotations

from datetime import datetime

from kuake.autodl_api import AutoDLClient, load_jwt_from_storage_state
from kuake.autodl_planner import (
    format_plan,
    plan_clone_from_instance,
    save_plan,
)
from kuake.config import config_paths
from kuake.errors import ConfigMissing, NetworkError, UserInputError
from kuake.progress import console, info, ok, warn


def run(
    source: str | None = None,
    *,
    same_region: bool = False,
    gpu_count: int | None = None,
    expand_data_disk_gb: int | None = None,
    system_disk_change_size_gb: int | None = None,
) -> None:
    """Generate a clone PLAN.

    source:  实例的 uuid 或 1-based 索引(见 kuake instances)。
             不传时弹列表让用户选。
    same_region: 只在源实例同区找空闲机器。
    """
    try:
        jwt = load_jwt_from_storage_state()
    except NetworkError as e:
        raise ConfigMissing(str(e)) from e
    client = AutoDLClient(jwt=jwt)

    instances = client.list_instances()
    if not instances:
        raise UserInputError("AutoDL 账号下没有任何实例,无源可克隆")

    # 解析 source
    src_inst: dict | None = None
    if source is None:
        console.print("\n你的 AutoDL 实例 (选择源实例编号):")
        for i, inst in enumerate(instances, 1):
            console.print(f"  [{i}] {inst.get('machine_alias','?'):8s} "
                          f"GPU={inst.get('snapshot_gpu_alias_name','?'):14s} "
                          f"状态={inst.get('status','?'):10s} "
                          f"uuid={inst.get('uuid','?')[:12]}")
        try:
            idx = int(input("源实例编号 (1-N): ").strip())
            src_inst = instances[idx - 1]
        except (ValueError, IndexError) as e:
            raise UserInputError(f"无效编号: {e}") from e
    else:
        # 尝试 1-based 索引
        if source.isdigit():
            idx = int(source)
            if 1 <= idx <= len(instances):
                src_inst = instances[idx - 1]
        if src_inst is None:
            # 尝试 uuid
            for inst in instances:
                if inst.get("uuid", "").startswith(source):
                    src_inst = inst
                    break
        if src_inst is None:
            raise UserInputError(
                f"找不到 source={source!r} (既不是 1-{len(instances)} 索引,也不匹配任何 uuid 前缀)"
            )

    info(f"源实例: {src_inst.get('machine_alias','?')} "
         f"(uuid={src_inst.get('uuid','?')[:12]}) "
         f"GPU={src_inst.get('snapshot_gpu_alias_name','?')} "
         f"状态={src_inst.get('status','?')}")

    # 找 target 机器
    source_gpu = src_inst.get("snapshot_gpu_alias_name") or src_inst.get("snapshot_gpu_name") or ""
    source_region = src_inst.get("region_sign") or ""
    info(f"在市场上找匹配机器 (GPU≈{source_gpu}, "
         f"region={'仅 ' + source_region if same_region else 'any'})")

    try:
        matches = client.list_available(
            gpu_type_names=[source_gpu] if source_gpu else None,
            region_sign_list=[source_region] if same_region and source_region else None,
            min_idle_gpu=src_inst.get("req_gpu_amount", 1),
        )
    except NetworkError as e:
        raise UserInputError(f"无法查市场: {e}") from e

    if not matches:
        warn(f"市场上当前没有 {source_gpu} 空闲机器 — 用 kuake grab 后台轮询")
        return

    target = matches[0]
    ok(f"target 选第一个匹配: {target}")

    plan = plan_clone_from_instance(
        src_inst, target,
        gpu_count=gpu_count,
        expand_data_disk_gb=expand_data_disk_gb,
        system_disk_change_size_gb=system_disk_change_size_gb,
    )
    console.print(format_plan(plan))

    plans_dir = config_paths().home / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    plan_path = plans_dir / f"clone_{stamp}.json"
    save_plan(plan, str(plan_path))
    ok(f"克隆 PLAN 已落盘: {plan_path}")
    info("→ 真下单需要: kuake confirm-create --plan-file " + str(plan_path))
