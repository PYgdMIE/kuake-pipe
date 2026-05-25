import pytest
from kuake.config import (
    Config, Credentials, write_config, read_config,
    write_credentials, read_credentials, config_paths,
)
from kuake.errors import ConfigMissing, ConfigCorrupt


def test_write_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    cfg = Config(
        host="host.example", port=22, user="root", auth_mode="password",
        panel_base="https://x.host", fs_id="quark1",
        local_backup_dir=str(tmp_path / "UPLOAD"),
        cloud_backup_path="/我的备份/test/UPLOAD",
        remote_tmp_dir="/root/autodl-tmp",
    )
    write_config(cfg)
    loaded = read_config()
    assert loaded.host == cfg.host
    assert loaded.port == cfg.port
    assert loaded.user == cfg.user
    assert loaded.auth_mode == cfg.auth_mode
    assert loaded.panel_base == cfg.panel_base
    assert loaded.cloud_backup_path == cfg.cloud_backup_path


def test_credentials_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    cred = Credentials(
        ssh_password="secret", ssh_key_path=None,
        panel_authorization="Bearer abc",
        panel_autodl_token="tok123",
        expires_estimate="2026-06-25T01:30:00",
    )
    write_credentials(cred)
    loaded = read_credentials()
    assert loaded == cred


def test_credentials_key_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    cred = Credentials(
        ssh_password=None, ssh_key_path="/path/to/key",
        panel_authorization="Bearer abc",
        panel_autodl_token="tok",
        expires_estimate="",
    )
    write_credentials(cred)
    loaded = read_credentials()
    assert loaded.ssh_password is None
    assert loaded.ssh_key_path == "/path/to/key"


def test_missing_config_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    with pytest.raises(ConfigMissing):
        read_config()


def test_missing_credentials_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    with pytest.raises(ConfigMissing):
        read_credentials()


def test_corrupt_config_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    paths = config_paths()
    paths.config_file.parent.mkdir(parents=True, exist_ok=True)
    paths.config_file.write_text("this is not valid toml = = =", encoding="utf-8")
    with pytest.raises(ConfigCorrupt):
        read_config()


def test_atomic_write_no_partial(tmp_path, monkeypatch):
    """write_config writes via tmp+rename so partial files never observed."""
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    cfg = Config(
        host="h", port=22, user="root", auth_mode="password",
        panel_base="https://x", fs_id="quark1",
        local_backup_dir="/u", cloud_backup_path="/c",
        remote_tmp_dir="/r",
    )
    write_config(cfg)
    paths = config_paths()
    # No .tmp leftover
    assert not list(paths.config_file.parent.glob("*.tmp"))


def test_config_paths_respects_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    paths = config_paths()
    assert paths.home == tmp_path
    assert paths.config_file == tmp_path / "config.toml"
    assert paths.credentials_file == tmp_path / "credentials.toml"
    assert paths.storage_state == tmp_path / "state" / "storage_state.json"
    assert paths.lock_file == tmp_path / ".lock"
