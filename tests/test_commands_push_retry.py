"""Unit tests for push / retry commands. Mock SshExec, PanelClient, QuarkUploader.

Goal: cover the pipeline 4-stage state machine + error paths without hitting real
infra. These tests give confidence that refactors don't regress the wire.
"""
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kuake.commands import push, retry
from kuake.config import Config, Credentials, write_config, write_credentials
from kuake.errors import UserInputError, CloudTimeout
from kuake.quark_uploader import UploadResult


@pytest.fixture
def kuake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def cfg_and_cred(kuake_home):
    cfg = Config(
        host="h.example", port=22, user="root", auth_mode="password",
        panel_base="https://panel.example", fs_id="quark1",
        cloud_backup_path="/kuake-uploads",
        remote_tmp_dir="/root/autodl-tmp",
    )
    cred = Credentials(
        ssh_password="pw", ssh_key_path=None,
        panel_authorization="A" * 40, panel_autodl_token="J" * 40,
        expires_estimate="2026-12-31T00:00:00",
        quark_cookie="cookie=v",
    )
    write_config(cfg)
    write_credentials(cred)
    return cfg, cred


def _make_src(tmp_path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "a.txt").write_text("hello")
    return src


def test_push_invalid_task_name_raises(kuake_home):
    with pytest.raises(UserInputError, match="Invalid task name"):
        push.run("bad name!", "/tmp/x")


def test_push_missing_src_raises(kuake_home, tmp_path):
    with pytest.raises(UserInputError, match="Source not found"):
        push.run("good-task", str(tmp_path / "nonexistent"))


def test_push_full_pipeline_mocked(cfg_and_cred, tmp_path, kuake_home):
    """Mock all external IO and validate the 4-stage pipeline order."""
    src = _make_src(tmp_path)

    fake_upload_result = UploadResult(
        fid="cloud-fid", file_name="task-x.zip", size=999,
        md5="m" * 32, sha1="s" * 40,
    )
    fake_uploader = MagicMock()
    fake_uploader.resolve_or_create_folder.return_value = "folder-fid"
    fake_uploader.upload.return_value = fake_upload_result

    fake_panel = MagicMock()
    fake_panel.find_by_path.return_value = {
        "file_id": "cloud-fid", "name": "task-x.zip",
        "is_dir": False, "size": 999,
    }
    fake_panel.trigger_download.return_value = {}
    fake_panel.wait_task.return_value = {"status": "done"}

    fake_ssh_ctx = MagicMock()
    fake_ssh = MagicMock()
    fake_ssh_ctx.__enter__.return_value = fake_ssh
    fake_ssh_ctx.__exit__.return_value = False
    fake_ssh.run.return_value = (0, "", "")
    fake_ssh.unzip_remote.return_value = None

    with patch("kuake.commands.push.QuarkUploader", return_value=fake_uploader), \
         patch("kuake.commands.push.PanelClient", return_value=fake_panel), \
         patch("kuake.commands.push.SshExec", return_value=fake_ssh_ctx):
        push.run("task-x", str(src), no_unzip=False, keep_zip=False)

    # 验证关键调用顺序
    fake_uploader.resolve_or_create_folder.assert_called_once_with("/kuake-uploads")
    fake_uploader.upload.assert_called_once()
    fake_panel.find_by_path.assert_called_with("/kuake-uploads/task-x.zip")
    fake_panel.trigger_download.assert_called_once()
    fake_panel.wait_task.assert_called_once_with("task-x.zip")
    # SSH: test-f + mkdir + mv + unzip + ls
    assert fake_ssh.run.call_count >= 4
    fake_ssh.unzip_remote.assert_called_once()


def test_push_cloud_not_visible_after_upload_raises(cfg_and_cred, tmp_path, kuake_home):
    """上传成功但 AutoPanel 视角不可见 → CloudTimeout"""
    src = _make_src(tmp_path)

    fake_uploader = MagicMock()
    fake_uploader.resolve_or_create_folder.return_value = "ff"
    fake_uploader.upload.return_value = UploadResult(
        fid="f", file_name="z.zip", size=10, md5="m"*32, sha1="s"*40,
    )
    fake_panel = MagicMock()
    fake_panel.find_by_path.return_value = None

    with patch("kuake.commands.push.QuarkUploader", return_value=fake_uploader), \
         patch("kuake.commands.push.PanelClient", return_value=fake_panel):
        with pytest.raises(CloudTimeout, match="AutoPanel 看不到"):
            push.run("task-y", str(src))


def test_push_no_unzip_skips_ssh_unzip(cfg_and_cred, tmp_path, kuake_home):
    src = _make_src(tmp_path)
    fake_uploader = MagicMock()
    fake_uploader.resolve_or_create_folder.return_value = "ff"
    fake_uploader.upload.return_value = UploadResult(
        fid="f", file_name="z.zip", size=10, md5="m"*32, sha1="s"*40,
    )
    fake_panel = MagicMock()
    fake_panel.find_by_path.return_value = {"file_id": "f", "is_dir": False, "size": 10}
    fake_panel.trigger_download.return_value = {}
    fake_panel.wait_task.return_value = {}

    with patch("kuake.commands.push.QuarkUploader", return_value=fake_uploader), \
         patch("kuake.commands.push.PanelClient", return_value=fake_panel), \
         patch("kuake.commands.push.SshExec") as mock_ssh:
        push.run("task-z", str(src), no_unzip=True)
    mock_ssh.assert_not_called()  # --no-unzip 跳过 SSH 阶段


def test_retry_uses_existing_staging_zip(cfg_and_cred, kuake_home):
    """retry 路径:不打包,直接复用 staging/<task>.zip"""
    # 先放一个假 zip 到 staging
    staging = kuake_home / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    fake_zip = staging / "existing-task.zip"
    fake_zip.write_bytes(b"PK\x03\x04fake zip content")

    fake_uploader = MagicMock()
    fake_uploader.resolve_or_create_folder.return_value = "ff"
    fake_uploader.upload.return_value = UploadResult(
        fid="f", file_name="existing-task.zip", size=fake_zip.stat().st_size,
        md5="m"*32, sha1="s"*40,
    )
    fake_panel = MagicMock()
    fake_panel.find_by_path.return_value = {"file_id": "f", "is_dir": False, "size": 999}
    fake_panel.trigger_download.return_value = {}
    fake_panel.wait_task.return_value = {}

    with patch("kuake.commands.push.QuarkUploader", return_value=fake_uploader), \
         patch("kuake.commands.push.PanelClient", return_value=fake_panel), \
         patch("kuake.commands.push.SshExec") as mock_ssh:
        # 用 SshExec 的上下文管理器 mock
        mock_ssh.return_value.__enter__.return_value.run.return_value = (0, "", "")
        retry.run("existing-task")

    fake_uploader.upload.assert_called_once()


def test_retry_missing_zip_raises(cfg_and_cred, kuake_home):
    with pytest.raises(UserInputError, match="No existing zip"):
        retry.run("nonexistent-task")


def test_push_lock_conflict_raises(cfg_and_cred, tmp_path, kuake_home):
    """文件锁占用时 push 报 ConcurrencyLock"""
    from kuake.concurrency import FileLock
    src = _make_src(tmp_path)
    paths_home = kuake_home
    lock_file = paths_home / ".lock"

    # 持锁,模拟另一个 kuake 进程
    with FileLock(lock_file):
        with pytest.raises(Exception) as exc_info:
            push.run("locked-task", str(src))
        # 类型检查:可能是 ConcurrencyLock 或派生
        from kuake.errors import ConcurrencyLock
        assert isinstance(exc_info.value, ConcurrencyLock)
