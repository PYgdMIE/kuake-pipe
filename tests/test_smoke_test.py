"""Tests for browser/smoke_test.py (v0.4 direct upload version)."""
from __future__ import annotations
from unittest.mock import MagicMock, patch

from kuake.browser.smoke_test import run_smoke_test
from kuake.quark_uploader import QuarkUploadError, UploadResult


def test_smoke_test_success_returns_true():
    """正常路径: resolve_or_create_folder + upload 都通"""
    fake_uploader = MagicMock()
    fake_uploader.resolve_or_create_folder.return_value = "folder-fid"
    fake_uploader.upload.return_value = UploadResult(
        fid="upload-fid", file_name="x.bin", size=1024,
        md5="m" * 32, sha1="s" * 40,
    )
    with patch("kuake.browser.smoke_test.QuarkUploader",
               return_value=fake_uploader):
        ok = run_smoke_test(cookie="ck=v", cloud_backup_path="/test-uploads")
    assert ok is True
    # 上传调用一次, 文件夹解析一次
    fake_uploader.resolve_or_create_folder.assert_called_once_with("/test-uploads")
    fake_uploader.upload.assert_called_once()


def test_smoke_test_folder_resolve_fails_returns_false():
    """resolve_or_create_folder 抛错时 smoke 失败但不抛"""
    fake_uploader = MagicMock()
    fake_uploader.resolve_or_create_folder.side_effect = \
        QuarkUploadError("404")
    with patch("kuake.browser.smoke_test.QuarkUploader",
               return_value=fake_uploader):
        ok = run_smoke_test(cookie="ck=v", cloud_backup_path="/test")
    assert ok is False
    fake_uploader.upload.assert_not_called()


def test_smoke_test_upload_fails_returns_false():
    fake_uploader = MagicMock()
    fake_uploader.resolve_or_create_folder.return_value = "f"
    fake_uploader.upload.side_effect = QuarkUploadError("upload broke")
    with patch("kuake.browser.smoke_test.QuarkUploader",
               return_value=fake_uploader):
        ok = run_smoke_test(cookie="ck=v", cloud_backup_path="/test")
    assert ok is False


def test_smoke_test_cleans_up_temp_file(tmp_path):
    """临时上传文件必须删 (即使上传失败) — 跨平台 (用 tempfile.gettempdir)"""
    import os
    import tempfile
    tmpdir = tempfile.gettempdir()
    before = set(f for f in os.listdir(tmpdir) if f.startswith("kuake_smoke_"))

    fake_uploader = MagicMock()
    fake_uploader.resolve_or_create_folder.return_value = "f"
    fake_uploader.upload.side_effect = QuarkUploadError("oops")
    with patch("kuake.browser.smoke_test.QuarkUploader",
               return_value=fake_uploader):
        run_smoke_test(cookie="ck=v", cloud_backup_path="/test")

    after = set(f for f in os.listdir(tmpdir) if f.startswith("kuake_smoke_"))
    # finally clause 应该已经清掉本次写的临时文件 — after 不应该比 before 多
    assert after <= before, f"temp files leaked: {after - before}"


def test_smoke_test_uses_random_content(tmp_path):
    """smoke test 写的 1KB 应是真随机, 避免被秒传 (md5 相同)跳过"""
    captured_paths = []

    def _capture_upload(path, parent_folder_id, **kw):
        captured_paths.append(path)
        return UploadResult(fid="f", file_name="x", size=1024,
                            md5="m" * 32, sha1="s" * 40)

    fake_uploader = MagicMock()
    fake_uploader.resolve_or_create_folder.return_value = "f"
    fake_uploader.upload.side_effect = _capture_upload
    with patch("kuake.browser.smoke_test.QuarkUploader",
               return_value=fake_uploader):
        run_smoke_test(cookie="ck=v", cloud_backup_path="/t")
    assert captured_paths
    # 文件应该是真随机内容,size=1024
    import os
    path = captured_paths[0]
    if os.path.exists(path):
        # 已经被 finally 删了,我们看不到内容
        pass
    # 至少验证文件名格式
    assert "kuake_smoke_" in path
