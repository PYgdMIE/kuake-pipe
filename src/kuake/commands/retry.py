"""Skip stage1 packing; reuse existing UPLOAD/<task>.zip."""
from __future__ import annotations

from kuake.commands import push


def run(task: str) -> None:
    push.run_existing_zip(task)
