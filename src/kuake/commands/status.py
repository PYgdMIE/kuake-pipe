"""Show recent kuake jobs (push / auto) from ~/.kuake/jobs/.

CC / Codex 用 --json 查后台任务状态。

Usage:
  kuake status                         # 最近 10 个 jobs 人类视图
  kuake status --limit 50              # 多列点
  kuake status --json                  # JSON 数组
  kuake status <job_id>                # 单 job 详情 + 日志
  kuake status <job_id> --json
  kuake status --only-running          # 仅运行中
"""
from __future__ import annotations

import json as _json

from kuake.config import config_paths
from kuake.progress import console, set_json_mode


def run(
    job_id: str | None = None,
    *,
    limit: int = 10,
    only_running: bool = False,
    json_output: bool = False,
) -> None:
    """List jobs or show single job detail."""
    if json_output:
        set_json_mode(True)

    # 复用 server.JobStore 读取(不启 server)
    from kuake.server import JobStore
    store = JobStore(config_paths().home)
    store.sweep_stale()  # PID 死的标 interrupted

    if job_id:
        meta = store.get(job_id)
        if not meta:
            if json_output:
                print(_json.dumps({"error": f"unknown job_id: {job_id}"},
                                  ensure_ascii=False))
            else:
                console.print(f"[red]✗[/red] 找不到 job: {job_id}")
            return
        log = store.read_log(job_id)
        if json_output:
            print(_json.dumps({"meta": meta, "log": log}, ensure_ascii=False))
        else:
            _render_single(meta, log)
        return

    jobs = store.list_recent(limit=limit)
    if only_running:
        jobs = [j for j in jobs if j.get("status") == "running"]

    if json_output:
        print(_json.dumps(jobs, ensure_ascii=False))
        return

    if not jobs:
        console.print(f"[dim]无 job ({'running 中' if only_running else '历史'})[/dim]")
        return

    console.print()
    console.print("[bold]最近 kuake jobs:[/bold]")
    for j in jobs:
        status = j.get("status", "?")
        color = {
            "running": "blue", "completed": "green",
            "failed": "red", "cancelled": "yellow",
            "interrupted": "yellow",
        }.get(status, "white")
        jid = j.get("job_id", "")
        kind = j.get("kind", "?")
        task = j.get("task", "—")
        started = j.get("started_at", "")
        console.print(
            f"  [{color}]{status:11s}[/{color}] "
            f"[dim]{jid}[/dim]  {kind:5s}  {task[:30]:30s}  "
            f"[dim]{started}[/dim]"
        )


def _render_single(meta: dict, log: str) -> None:
    console.print()
    console.print(f"[bold]Job {meta.get('job_id', '?')}[/bold]")
    for k in ("kind", "status", "started_at", "finished_at", "exit_code",
              "task", "src", "stop_after"):
        if k in meta and meta[k] is not None:
            console.print(f"  {k:14s}: {meta[k]}")
    console.print()
    console.print("[bold]Log:[/bold]")
    console.print(log or "[dim](空)[/dim]")
