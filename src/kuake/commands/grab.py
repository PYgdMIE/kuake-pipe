"""Poll the AutoDL market for available GPU/CPU machines and (optionally) grab one.

Usage:
  kuake grab                           # poll every 5s for any GPU
  kuake grab --gpu "RTX 5090"          # specific GPU
  kuake grab --gpu "RTX 5090" --gpu "RTX 4090"   # any of these
  kuake grab --region west-B           # only this region
  kuake grab --cpu-ok                  # accept CPU instances too
  kuake grab --poll 3                  # poll every 3s
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import List, Optional

from kuake.config import config_paths
from kuake.errors import ConfigMissing
from kuake.progress import info, ok, warn, console


def _load_autodl_cookies() -> dict:
    """Read autodl.com cookies from the saved Playwright storage_state."""
    state_path = config_paths().storage_state
    if not state_path.exists():
        raise ConfigMissing(
            f"storage_state missing ({state_path}); run `kuake init` first"
        )
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ConfigMissing(f"storage_state unreadable: {e}") from e
    cookies = {}
    for c in state.get("cookies", []):
        domain = c.get("domain", "")
        if "autodl.com" in domain:
            cookies[c["name"]] = c.get("value", "")
    return cookies


def run(
    gpu_types: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
    cpu_ok: bool = False,
    min_idle_gpu: int = 1,
    poll_seconds: int = 5,
    max_iterations: int = 0,
    dry_run: bool = True,
) -> None:
    """Poll AutoDL market until a matching machine is found.
    dry_run=True (default) only reports; does not create an instance."""
    from kuake.autodl_api import AutoDLClient

    cookies = _load_autodl_cookies()
    if not cookies:
        raise ConfigMissing(
            "No AutoDL cookies in storage_state; run `kuake init` to log in first"
        )
    client = AutoDLClient(cookies=cookies)

    target = f"GPU={gpu_types or 'any'}, region={regions or 'any'}, min_idle={min_idle_gpu}"
    if cpu_ok:
        target += ", CPU also OK"
    info(f"Polling AutoDL market for: {target}  (every {poll_seconds}s)")
    info("Press Ctrl+C to stop")

    it = 0
    while True:
        it += 1
        try:
            matches = client.list_available(
                gpu_type_names=gpu_types,
                region_sign_list=regions,
                min_idle_gpu=min_idle_gpu,
            )
        except Exception as e:
            warn(f"poll #{it} failed: {e}")
            time.sleep(poll_seconds)
            if max_iterations and it >= max_iterations:
                break
            continue

        if not cpu_ok:
            matches = [m for m in matches if m.chip_corp.lower() != "cpu"]

        if matches:
            console.print()
            ok(f"找到 {len(matches)} 个可用机器:")
            for m in matches:
                console.print(f"  • {m}")
            console.print()
            if dry_run:
                ok("dry-run 模式 — 未创建实例。去 https://www.autodl.com/market/list 手动抢")
                ok("(或加 --auto-create 自动创建第一台)")
                return
            else:
                target = matches[0]
                ok(f"自动创建实例: {target.region_name}/{target.machine_alias} "
                   f"{target.gpu_name} ×{min_idle_gpu}")
                try:
                    result = client.create_payg_instance(
                        machine_id=target.machine_id,
                        req_gpu_amount=min_idle_gpu,
                        chip_corp=target.chip_corp,
                    )
                    ok(f"创建成功: {result}")
                    return
                except Exception as e:
                    warn(f"创建失败,继续轮询: {e}")
                    time.sleep(poll_seconds)
                    continue
        else:
            console.print(f"[dim]poll #{it}: 暂无匹配 (next in {poll_seconds}s)[/dim]",
                          end="\r")
        if max_iterations and it >= max_iterations:
            console.print()
            warn(f"reached max iterations ({max_iterations}), giving up")
            return
        time.sleep(poll_seconds)
