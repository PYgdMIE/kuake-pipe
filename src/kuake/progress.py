"""rich.progress wrappers for stage progress + status spinners."""
from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Callable

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

console = Console()


def set_json_mode(enabled: bool) -> None:
    """In JSON mode, route rich output (info/ok/warn/err) to stderr.

    Reserves stdout for the JSON-line payload that CC/Codex parse.
    """
    console.file = sys.stderr if enabled else sys.stdout


def setup_utf8():
    """Force UTF-8 stdout for Windows console (中文不乱码)."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore
        except Exception:
            pass


@contextmanager
def stage(title: str) -> Iterator[None]:
    """Show a spinner with title for an indeterminate stage."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console, transient=True,
    ) as prog:
        prog.add_task(title, total=None)
        yield


@contextmanager
def transfer(title: str, total: int | None = None) -> Iterator[Callable]:
    """Show a transfer progress bar. Returns an update(advance, total=None) callable."""
    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as prog:
        task = prog.add_task(title, total=total)

        def update(advance: int = 0, total: int | None = None):
            if total is not None:
                prog.update(task, total=total)
            if advance:
                prog.update(task, advance=advance)

        yield update


def info(msg: str):
    console.print(f"[cyan]·[/cyan] {msg}")
    try:
        from kuake.debug_log import log_event
        log_event("info", msg)
    except Exception:
        pass


def ok(msg: str):
    console.print(f"[green]✓[/green] {msg}")
    try:
        from kuake.debug_log import log_event
        log_event("ok", msg)
    except Exception:
        pass


def warn(msg: str):
    console.print(f"[yellow]![/yellow] {msg}")
    try:
        from kuake.debug_log import log_event
        log_event("warn", msg)
    except Exception:
        pass


def err(msg: str):
    console.print(f"[red]✗[/red] {msg}")
    try:
        from kuake.debug_log import log_event
        log_event("err", msg)
    except Exception:
        pass
