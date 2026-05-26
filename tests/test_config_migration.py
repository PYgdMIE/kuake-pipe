"""测试 v0.3 → v0.4 config 迁移兼容:
- 老 config.toml 带 quark.local_backup_dir 字段
- v0.4 read_config 必须能读出来,且 local_backup_dir 字段无效但不报错
- v0.4 write_config 写新结构,不输出 local_backup_dir
"""
from __future__ import annotations
import pytest

from kuake.config import (
    Config, read_config, write_config, config_paths,
    Credentials, write_credentials, read_credentials,
)


def test_read_legacy_v03_config(tmp_path, monkeypatch):
    """v0.3 风格的 config.toml 包含 quark.local_backup_dir,读取后 local_backup_dir 字段应填入"""
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    paths = config_paths()
    paths.home.mkdir(parents=True, exist_ok=True)
    paths.config_file.write_text("""
[instance]
host = "old.example"
port = 22
user = "root"
auth_mode = "password"

[panel]
base = "https://panel.example"
fs_id = "quark1"

[quark]
local_backup_dir = "/home/user/Downloads/UPLOAD"
cloud_backup_path = "/我的备份/电脑备份/UPLOAD"

[remote]
tmp_dir = "/root/autodl-tmp"

[meta]
created_at = "2026-05-25T22:00:00"
last_refresh = "2026-05-25T22:00:00"
""", encoding="utf-8")
    cfg = read_config()
    assert cfg.host == "old.example"
    assert cfg.cloud_backup_path == "/我的备份/电脑备份/UPLOAD"
    # 老字段保留(便于 rm 命令清理旧本地 zip)
    assert cfg.local_backup_dir == "/home/user/Downloads/UPLOAD"


def test_read_v04_config_without_local_backup_dir(tmp_path, monkeypatch):
    """v0.4 风格(没有 local_backup_dir 字段)读取,应 default 为空"""
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    paths = config_paths()
    paths.home.mkdir(parents=True, exist_ok=True)
    paths.config_file.write_text("""
[instance]
host = "new.example"
port = 22
user = "root"
auth_mode = "key"

[panel]
base = "https://panel.example"
fs_id = "quark1"

[quark]
cloud_backup_path = "/kuake-uploads"

[remote]
tmp_dir = "/root/autodl-tmp"

[meta]
created_at = "2026-05-26T01:00:00"
last_refresh = "2026-05-26T01:00:00"
""", encoding="utf-8")
    cfg = read_config()
    assert cfg.host == "new.example"
    assert cfg.local_backup_dir == ""  # default


def test_v04_write_omits_local_backup_dir(tmp_path, monkeypatch):
    """v0.4 write_config 不应该写 quark.local_backup_dir 字段"""
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    cfg = Config(
        host="x", port=22, user="root", auth_mode="key",
        panel_base="https://x", fs_id="quark1",
        cloud_backup_path="/c",
        remote_tmp_dir="/r",
    )
    write_config(cfg)
    paths = config_paths()
    content = paths.config_file.read_text(encoding="utf-8")
    assert "cloud_backup_path" in content
    assert "local_backup_dir" not in content


def test_round_trip_with_legacy_field(tmp_path, monkeypatch):
    """老 config 读出 → 新 write_config 写回 → 再读应保留 cloud_backup_path 但丢 local_backup_dir"""
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    paths = config_paths()
    paths.home.mkdir(parents=True, exist_ok=True)
    paths.config_file.write_text("""
[instance]
host = "h"
port = 22
user = "root"
auth_mode = "password"

[panel]
base = "https://x"
fs_id = "quark1"

[quark]
local_backup_dir = "/old/path"
cloud_backup_path = "/我的备份/x"

[remote]
tmp_dir = "/r"

[meta]
created_at = "2026-05-25T00:00:00"
last_refresh = "2026-05-25T00:00:00"
""", encoding="utf-8")

    cfg1 = read_config()
    assert cfg1.local_backup_dir == "/old/path"

    # write 回去
    write_config(cfg1)
    cfg2 = read_config()
    assert cfg2.cloud_backup_path == "/我的备份/x"
    # v0.4 write 不输出 local_backup_dir → 读出 default 空
    assert cfg2.local_backup_dir == ""


def test_credentials_unchanged_across_versions(tmp_path, monkeypatch):
    """credentials 文件结构 v0.3/v0.4 完全一致,无迁移问题"""
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    cred = Credentials(
        ssh_password=None, ssh_key_path="/k",
        panel_authorization="A" * 40, panel_autodl_token="J" * 40,
        expires_estimate="2026-12-31T00:00:00",
        standalone_password_sha1="a" * 40,
        quark_cookie="c=1",
    )
    write_credentials(cred)
    loaded = read_credentials()
    assert loaded == cred
