"""Cross-platform exclusive file lock for ~/.kuake/.lock"""
from __future__ import annotations
import sys
from pathlib import Path


class LockBusy(Exception):
    pass


class FileLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+b")
        try:
            self._acquire()
        except (BlockingIOError, OSError) as e:
            self._fh.close()
            self._fh = None
            raise LockBusy(f"Lock busy: {self.path}") from e
        return self

    def __exit__(self, *args):
        if self._fh is not None:
            try:
                self._release()
            finally:
                self._fh.close()
                self._fh = None

    def _acquire(self):
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release(self):
        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
