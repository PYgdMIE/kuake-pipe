"""Block until an AutoDL instance reaches status='running'.

CC/Codex 自动化用 — 创建后等机器就绪再 init/push。
Exit 0 = running 了。非 0 = 超时或找不到。

Usage:
  kuake wait-running <uuid_or_idx_or_prefix> [--timeout 600] [--poll 5]
"""
from __future__ import annotations

import json as _json

from kuake.autodl_api import AutoDLClient, load_jwt_from_storage_state
from kuake.errors import ConfigMissing, NetworkError, UserInputError
from kuake.progress import console, info, ok, set_json_mode


def run(
    target: str,
    *,
    timeout: int = 600,
    poll: int = 5,
    json_output: bool = False,
) -> dict:
    """Wait for the given instance to be running.

    target: 实例的 uuid (完整或前缀), 或 1-based 索引 (kuake instances 列出的)。
    Returns the running instance dict (用于 chain).
    """
    if json_output:
        set_json_mode(True)
    if not target:
        raise UserInputError("缺 target (uuid 前缀或 1-based 索引)")

    try:
        jwt = load_jwt_from_storage_state()
    except NetworkError as e:
        raise ConfigMissing(str(e)) from e
    client = AutoDLClient(jwt=jwt)

    instances = client.list_instances()
    if not instances:
        raise UserInputError("AutoDL 账号下没有任何实例")

    # 解析 target → uuid
    uuid: str | None = None
    if target.isdigit():
        idx = int(target)
        if 1 <= idx <= len(instances):
            uuid = instances[idx - 1].get("uuid")
    if not uuid:
        for inst in instances:
            if inst.get("uuid", "").startswith(target):
                uuid = inst.get("uuid")
                break
    if not uuid:
        raise UserInputError(
            f"找不到 target={target!r} (不是 1-{len(instances)} 索引, 也不匹配任何 uuid 前缀)"
        )

    info(f"等待实例 {uuid[:12]}.. 状态变为 running (最多 {timeout}s, 每 {poll}s 查一次)")

    def _on_status(s: str) -> None:
        console.print(f"  · status = [cyan]{s}[/cyan]")

    inst = client.wait_until_running(uuid, timeout=timeout, poll=poll, progress_cb=_on_status)
    ok(f"实例 {uuid[:12]}.. 已 running")
    console.print(f"  机器: {inst.get('machine_alias','?')} ({inst.get('region_name','?')})")
    console.print(f"  GPU : {inst.get('snapshot_gpu_alias_name','?')} × "
                  f"{inst.get('req_gpu_amount', 1)}")
    if json_output:
        print(_json.dumps({
            "uuid": inst.get("uuid", ""),
            "machine_alias": inst.get("machine_alias", ""),
            "region_name": inst.get("region_name", ""),
            "gpu_name": inst.get("snapshot_gpu_alias_name", ""),
            "gpu_count": inst.get("req_gpu_amount", 1),
            "status": inst.get("status", ""),
        }, ensure_ascii=False))
    return inst
