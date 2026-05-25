import sys
import pytest
from unittest.mock import patch
from kuake.platform_guard import ensure_supported, harden_file_acl
from kuake.errors import PlatformUnsupported


def test_linux_raises():
    with patch.object(sys, "platform", "linux"):
        with pytest.raises(PlatformUnsupported):
            ensure_supported()


def test_win32_passes():
    with patch.object(sys, "platform", "win32"):
        ensure_supported()


def test_darwin_passes():
    with patch.object(sys, "platform", "darwin"):
        ensure_supported()


def test_harden_acl_no_crash_on_missing_file(tmp_path):
    # Should not raise even if file is missing
    harden_file_acl(tmp_path / "nonexistent")


def test_harden_acl_on_real_file(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("secret")
    harden_file_acl(p)
    # Should not raise; permission verification is platform-dependent
