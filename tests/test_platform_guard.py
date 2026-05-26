import sys
from unittest.mock import patch
from kuake.platform_guard import ensure_supported, harden_file_acl


def test_ensure_supported_linux_noop():
    # v0.4+: 不再拦截 Linux,直接 return None
    with patch.object(sys, "platform", "linux"):
        assert ensure_supported() is None


def test_ensure_supported_win32_noop():
    with patch.object(sys, "platform", "win32"):
        assert ensure_supported() is None


def test_ensure_supported_darwin_noop():
    with patch.object(sys, "platform", "darwin"):
        assert ensure_supported() is None


def test_harden_acl_no_crash_on_missing_file(tmp_path):
    # Should not raise even if file is missing
    harden_file_acl(tmp_path / "nonexistent")


def test_harden_acl_on_real_file(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("secret")
    harden_file_acl(p)
    # Should not raise; permission verification is platform-dependent
