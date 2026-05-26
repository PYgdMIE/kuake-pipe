"""Tests for refresh / rm / ls / reset / instances / start / stop commands.

External dependencies (Playwright, SshExec, PanelClient) all mocked.
"""
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kuake.commands import refresh, rm, ls, reset
from kuake.config import Config, Credentials, write_config, write_credentials, config_paths
from kuake.errors import SessionDead, UserInputError


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
        standalone_password_sha1="0" * 40,
        quark_cookie="cookie=v",
    )
    write_config(cfg)
    write_credentials(cred)
    return cfg, cred


# ── refresh ──────────────────────────────────────────────────────────

def test_refresh_no_sha1_raises_session_dead(cfg_and_cred, kuake_home):
    """没保存密码 sha1 时,refresh 立刻报 SessionDead 提示重 init"""
    cfg, cred = cfg_and_cred
    # 覆盖 credentials,清掉 sha1
    write_credentials(Credentials(
        ssh_password=cred.ssh_password, ssh_key_path=None,
        panel_authorization="A" * 40, panel_autodl_token="J" * 40,
        expires_estimate=cred.expires_estimate,
        standalone_password_sha1="",  # 关键:空
        quark_cookie=cred.quark_cookie,
    ))
    with pytest.raises(SessionDead, match="missing"):
        refresh.run()


def test_refresh_uses_saved_sha1_to_sign_in(cfg_and_cred, kuake_home):
    """有 sha1 时,refresh 调 PanelClient.sign_in 拿新 token 并写回 credentials"""
    fake_panel = MagicMock()
    fake_panel.sign_in.return_value = "B" * 40  # 新 token
    fake_panel.s = MagicMock()
    fake_panel.s.headers = {"Authorization": "B" * 40, "AutodlAutoPanelToken": "J" * 40}

    # refresh.py 在函数内部 import PanelClient,patch 原始位置
    with patch("kuake.panel_api.PanelClient", return_value=fake_panel):
        refresh.run()

    fake_panel.sign_in.assert_called_once_with("0" * 40)
    # 验证写回 credentials
    from kuake.config import read_credentials
    cred = read_credentials()
    assert cred.panel_authorization == "B" * 40


# ── rm ───────────────────────────────────────────────────────────────

def test_rm_invalid_task_raises(cfg_and_cred, kuake_home):
    with pytest.raises(UserInputError):
        rm.run("bad name!", assume_yes=True)


def test_rm_with_assume_yes_skips_prompt_and_calls_ssh(cfg_and_cred, kuake_home):
    fake_ssh_ctx = MagicMock()
    fake_ssh = MagicMock()
    fake_ssh_ctx.__enter__.return_value = fake_ssh
    fake_ssh_ctx.__exit__.return_value = False
    fake_ssh.run.return_value = (0, "", "")

    with patch("kuake.commands.rm.SshExec", return_value=fake_ssh_ctx):
        rm.run("good-task", assume_yes=True)

    fake_ssh.run.assert_called_once()
    args, kwargs = fake_ssh.run.call_args
    assert "rm -rf" in args[0]
    assert "/root/autodl-tmp/good-task" in args[0]


def test_rm_cleans_staging_zip_if_exists(cfg_and_cred, kuake_home):
    """staging/<task>.zip 存在时,rm 应该删除"""
    staging = kuake_home / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    zip_file = staging / "to-clean.zip"
    zip_file.write_bytes(b"PK\x03\x04")

    with patch("kuake.commands.rm.SshExec") as mock_ssh:
        mock_ssh.return_value.__enter__.return_value.run.return_value = (0, "", "")
        rm.run("to-clean", assume_yes=True)

    assert not zip_file.exists()


# ── ls ───────────────────────────────────────────────────────────────

def test_ls_runs_ssh_and_prints(cfg_and_cred, kuake_home, capsys):
    fake_ssh_ctx = MagicMock()
    fake_ssh = MagicMock()
    fake_ssh_ctx.__enter__.return_value = fake_ssh
    fake_ssh_ctx.__exit__.return_value = False
    fake_ssh.run.return_value = (0, "total 4\ndrwxr-xr-x 2 root root  4096 May 25\n", "")

    with patch("kuake.commands.ls.SshExec", return_value=fake_ssh_ctx):
        ls.run()

    fake_ssh.run.assert_called_once()
    captured = capsys.readouterr()
    assert "total 4" in captured.out


# ── reset ────────────────────────────────────────────────────────────

def test_reset_removes_home_dir(cfg_and_cred, kuake_home):
    paths = config_paths()
    assert paths.config_file.exists()
    with patch("builtins.input", return_value="y"):
        reset.run(keep_credentials=False)
    assert not paths.config_file.exists()
    assert not paths.credentials_file.exists()


def test_reset_keep_credentials(cfg_and_cred, kuake_home):
    paths = config_paths()
    assert paths.config_file.exists()
    assert paths.credentials_file.exists()
    with patch("builtins.input", return_value="y"):
        reset.run(keep_credentials=True)
    assert not paths.config_file.exists()
    # credentials 保留
    assert paths.credentials_file.exists()


def test_reset_aborts_if_denied(cfg_and_cred, kuake_home):
    paths = config_paths()
    with patch("builtins.input", return_value="n"):
        reset.run(keep_credentials=False)
    assert paths.config_file.exists()  # 没动


# ── doctor (smoke) ─────────────────────────────────────────────────────

def test_doctor_missing_config_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    from kuake.commands import doctor
    with pytest.raises(SystemExit) as exc_info:
        doctor.run()
    assert exc_info.value.code == 2
