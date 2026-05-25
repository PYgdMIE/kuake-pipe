import pytest
from kuake.concurrency import FileLock, LockBusy


def test_acquire_release(tmp_path):
    lock_path = tmp_path / ".lock"
    with FileLock(lock_path):
        assert lock_path.exists()


def test_second_acquire_raises(tmp_path):
    lock_path = tmp_path / ".lock"
    with FileLock(lock_path):
        with pytest.raises(LockBusy):
            with FileLock(lock_path):
                pass


def test_lock_released_after_with(tmp_path):
    lock_path = tmp_path / ".lock"
    with FileLock(lock_path):
        pass
    # After exit, can acquire again
    with FileLock(lock_path):
        pass


def test_lock_creates_parent_dir(tmp_path):
    lock_path = tmp_path / "subdir" / ".lock"
    with FileLock(lock_path):
        assert lock_path.exists()
