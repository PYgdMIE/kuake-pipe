"""rich.progress wrappers for stage progress + status spinners."""
from __future__ import annotations
import sys
from contextlib import contextmanager
from typing import Iterator, Optional, Callable

from rich.console import Console
from rich.progress import (
    Progress, BarColumn, TextColumn, TimeRemainingColumn,
    TransferSpeedColumn, DownloadColumn, SpinnerColumn,
)

console = Console()


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
def transfer(title: str, total: Optional[int] = None) -> Iterator[Callable]:
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

        def update(advance: int = 0, total: Optional[int] = None):
            if total is not None:
                prog.update(task, total=total)
            if advance:
                prog.update(task, advance=advance)

        yield update


def info(msg: str):
    console.print(f"[cyan]·[/cyan] {msg}")


def ok(msg: str):
    console.print(f"[green]✓[/green] {msg}")


def warn(msg: str):
    console.print(f"[yellow]![/yellow] {msg}")


def err(msg: str):
    console.print(f"[red]✗[/red] {msg}")
