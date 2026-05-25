"""Zip packaging + md5."""
from __future__ import annotations
import hashlib
import zipfile
from pathlib import Path


def make_zip(src: Path, out: Path) -> Path:
    src = Path(src)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        if src.is_file():
            zf.write(src, src.name)
        else:
            for p in src.rglob("*"):
                if p.is_file():
                    zf.write(p, p.relative_to(src).as_posix())
    return out


def md5sum(path: Path, bufsize: int = 1 << 20) -> str:
    h = hashlib.md5()
    with Path(path).open("rb") as f:
        while chunk := f.read(bufsize):
            h.update(chunk)
    return h.hexdigest()
