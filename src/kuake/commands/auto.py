"""End-to-end automation: grab → confirm-create → wait → init → push.

Designed for CC / Codex CLI orchestration. All inputs as flags;
no interactive prompts past the 3s --yes grace window.

Stop points (--stop-after):
  create  仅下单,返回 uuid 就停
  ready   等实例 running 后停
  init    跑完 init 配好凭据后停
  push    完整跑完上传 (默认)

Usage:
  kuake auto --gpu "RTX 3080 Ti" \\
    --autopanel-password 220405 \\
    --src C:/data --task my-exp \\
    --expand-data-disk 100
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime

from kuake.autodl_api import AutoDLClient, load_jwt_from_storage_state
from kuake.autodl_planner import plan_from_match, save_plan
from kuake.commands import confirm_create
from kuake.config import config_paths
from kuake.errors import ConfigMissing, NetworkError, UserInputError
from kuake.progress import console, info, ok, warn

_STOP_POINTS = ("create", "ready", "init", "push")


def run(
    *,
    gpu_types: list[str] | None = None,
    regions: list[str] | None = None,
    cpu_ok: bool = False,
    min_idle_gpu: int = 1,
    gpu_count: int = 1,
    expand_data_disk_gb: int = 0,
    system_disk_change_size_gb: int = 0,
    image: str | None = None,
    poll_seconds: int = 5,
    max_market_iters: int = 0,
    ready_timeout: int = 600,
    autopanel_password: str | None = None,
    cloud_dir: str | None = None,
    task: str | None = None,
    src: str | None = None,
    no_unzip: bool = False,
    keep_zip: bool = False,
    stop_after: str = "push",
) -> None:
    """Chain: grab → create → wait → init → push, stop at `stop_after`."""
    if stop_after not in _STOP_POINTS:
        raise UserInputError(
            f"stop_after 必须是 {_STOP_POINTS} 之一, 收到 {stop_after!r}"
        )
    if stop_after in ("init", "push") and not autopanel_password:
        raise UserInputError(
            "init/push 阶段需要 AutoPanel 密码 (--autopanel-password 或 "
            "KUAKE_AUTOPANEL_PASSWORD 环境变量)"
        )
    if stop_after == "push" and (not task or not src):
        raise UserInputError("push 阶段需要 --task 和 --src")

    info("=" * 60)
    info("kuake auto: grab → create → wait → init → push")
    info(f"  stop_after = {stop_after}")
    info("=" * 60)

    try:
        jwt = load_jwt_from_storage_state()
    except NetworkError as e:
        raise ConfigMissing(str(e)) from e
    client = AutoDLClient(jwt=jwt)

    # ── [1/5] grab 直到匹配 ───────────────────────────────────
    target_desc = f"GPU={gpu_types or 'any'}, region={regions or 'any'}, min_idle={min_idle_gpu}"
    info(f"[1/5] 轮询市场: {target_desc} (每 {poll_seconds}s)")

    matched = None
    it = 0
    while matched is None:
        it += 1
        try:
            matches = client.list_available(
                gpu_type_names=gpu_types,
                region_sign_list=regions,
                min_idle_gpu=min_idle_gpu,
            )
        except NetworkError as e:
            warn(f"  poll #{it}: {e}")
            if max_market_iters and it >= max_market_iters:
                raise NetworkError(
                    f"市场轮询 {max_market_iters} 次仍失败"
                ) from e
            time.sleep(poll_seconds)
            continue

        if not cpu_ok:
            matches = [m for m in matches if (m.chip_corp or "").lower() != "cpu"]
        if matches:
            matched = matches[0]
            break

        console.print(f"[dim]  poll #{it}: 暂无匹配[/dim]", end="\r")
        if max_market_iters and it >= max_market_iters:
            console.print()
            warn(f"  轮询达 {max_market_iters} 次,无匹配,退出 (无操作)")
            return
        time.sleep(poll_seconds)

    console.print()
    ok(f"  匹配: {matched}")

    # ── [2/5] PLAN + confirm-create ───────────────────────────
    info("[2/5] 生成 PLAN + 自动下单 (--yes, 3s grace)")
    plan = plan_from_match(
        matched,
        gpu_count=gpu_count,
        image=image,
        expand_data_disk_gb=expand_data_disk_gb,
        system_disk_change_size_gb=system_disk_change_size_gb,
    )
    plans_dir = config_paths().home / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    plan_path = plans_dir / f"auto_{stamp}.json"
    save_plan(plan, str(plan_path))
    ok(f"  PLAN → {plan_path}")

    new_uuid = confirm_create.run(plan_file=str(plan_path), yes=True)
    if not new_uuid:
        raise UserInputError("confirm-create 被取消或失败,终止")
    ok(f"  uuid: {new_uuid}")

    if stop_after == "create":
        ok("stop_after=create → 完成,新实例已下单")
        return

    # ── [3/5] 等 running ───────────────────────────────────────
    info(f"[3/5] 等待实例 {new_uuid[:12]}.. → running (最多 {ready_timeout}s)")

    def _on_status(s: str) -> None:
        console.print(f"  · status = [cyan]{s}[/cyan]")

    inst = client.wait_until_running(
        new_uuid, timeout=ready_timeout, poll=5, progress_cb=_on_status
    )
    ok(f"  ready: {inst.get('machine_alias','?')} {inst.get('region_name','?')}")

    if stop_after == "ready":
        ok("stop_after=ready → 完成,实例已就绪可登录")
        return

    # ── [4/5] kuake init ──────────────────────────────────────
    cur_instances = client.list_instances()
    new_idx = next(
        (i + 1 for i, ins in enumerate(cur_instances)
         if ins.get("uuid") == new_uuid),
        None,
    )
    if new_idx is None:
        raise UserInputError(
            f"新实例 {new_uuid[:12]} 在 list_instances 里找不到 (状态异常?)"
        )

    info(f"[4/5] kuake init --instance {new_idx} (浏览器会临时弹出抓 SSH/AutoPanel URL)")
    init_args = [
        sys.executable, "-m", "kuake", "init",
        "--instance", str(new_idx),
        "--no-smoke",
    ]
    if cloud_dir:
        init_args.extend(["--cloud-dir", cloud_dir])
    if autopanel_password:
        init_args.extend(["--autopanel-password", autopanel_password])

    env = os.environ.copy()
    if autopanel_password:
        env["KUAKE_AUTOPANEL_PASSWORD"] = autopanel_password
    rc = subprocess.run(init_args, env=env, check=False).returncode
    if rc != 0:
        raise UserInputError(f"kuake init 失败 (exit {rc})")
    ok("  init 完成: ~/.kuake/config.toml + credentials.toml")

    if stop_after == "init":
        ok("stop_after=init → 完成,凭据已落地")
        return

    # ── [5/5] kuake push ──────────────────────────────────────
    info(f"[5/5] kuake push {task} {src}")
    push_args = [sys.executable, "-m", "kuake", "push", task, src]
    if no_unzip:
        push_args.append("--no-unzip")
    if keep_zip:
        push_args.append("--keep-zip")
    rc = subprocess.run(push_args, check=False).returncode
    if rc != 0:
        raise UserInputError(f"kuake push 失败 (exit {rc})")

    ok("=" * 60)
    ok("kuake auto: 全链完成")
    ok("=" * 60)
