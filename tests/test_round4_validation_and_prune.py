"""Round 4 tests: config schema validation + JobStore.prune_old."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict

import pytest

from kuake.config import (
    Config,
    Credentials,
    config_paths,
    read_config,
    read_credentials,
    validate_config,
    validate_credentials,
    write_config,
    write_credentials,
)
from kuake.errors import ConfigCorrupt


def _make_valid_config(**overrides) -> Config:
    base = {
        "host": "ssh.example.com", "port": 22, "user": "root",
        "auth_mode": "password",
        "panel_base": "https://panel.example.com:8443",
        "fs_id": "quark1",
        "cloud_backup_path": "/kuake-uploads",
        "remote_tmp_dir": "/root/autodl-tmp",
    }
    base.update(overrides)
    return Config(**base)


# ── validate_config ────────────────────────────────────────────

def test_validate_config_passes_for_valid():
    validate_config(_make_valid_config())


def test_validate_config_rejects_empty_host():
    with pytest.raises(ConfigCorrupt, match="instance.host"):
        validate_config(_make_valid_config(host=""))


def test_validate_config_rejects_bad_port():
    with pytest.raises(ConfigCorrupt, match="instance.port"):
        validate_config(_make_valid_config(port=99999))
    with pytest.raises(ConfigCorrupt, match="instance.port"):
        validate_config(_make_valid_config(port=0))


def test_validate_config_rejects_unknown_auth_mode():
    with pytest.raises(ConfigCorrupt, match="auth_mode"):
        validate_config(_make_valid_config(auth_mode="kerberos"))


def test_validate_config_rejects_non_http_panel():
    with pytest.raises(ConfigCorrupt, match="panel.base"):
        validate_config(_make_valid_config(panel_base="ftp://x"))


def test_validate_config_rejects_relative_cloud_path():
    with pytest.raises(ConfigCorrupt, match="cloud_backup_path"):
        validate_config(_make_valid_config(cloud_backup_path="kuake-uploads"))


def test_validate_config_rejects_relative_remote_tmp():
    with pytest.raises(ConfigCorrupt, match="remote.tmp_dir"):
        validate_config(_make_valid_config(remote_tmp_dir="autodl-tmp"))


def test_validate_config_multiple_errors_all_reported():
    bad = _make_valid_config(
        host="", port=99999, auth_mode="x",
        panel_base="ftp://", cloud_backup_path="rel", remote_tmp_dir="rel",
    )
    with pytest.raises(ConfigCorrupt) as exc:
        validate_config(bad)
    msg = str(exc.value)
    assert "instance.host" in msg
    assert "instance.port" in msg
    assert "auth_mode" in msg


# ── validate_credentials ───────────────────────────────────────

def test_validate_credentials_passes_for_password():
    validate_credentials(Credentials(
        ssh_password="pw", ssh_key_path=None,
        panel_authorization="abc", panel_autodl_token="tok",
        expires_estimate="",
    ))


def test_validate_credentials_passes_for_key():
    validate_credentials(Credentials(
        ssh_password=None, ssh_key_path="/somewhere/key",
        panel_authorization="abc", panel_autodl_token="tok",
        expires_estimate="",
    ))


def test_validate_credentials_rejects_no_ssh_at_all():
    with pytest.raises(ConfigCorrupt, match="ssh.password 和 ssh.key_path"):
        validate_credentials(Credentials(
            ssh_password=None, ssh_key_path=None,
            panel_authorization="abc", panel_autodl_token="tok",
            expires_estimate="",
        ))


def test_validate_credentials_rejects_empty_panel_authorization():
    with pytest.raises(ConfigCorrupt, match="panel.authorization"):
        validate_credentials(Credentials(
            ssh_password="pw", ssh_key_path=None,
            panel_authorization="", panel_autodl_token="tok",
            expires_estimate="",
        ))


# ── read_config / read_credentials 走完整链路 ────────────────────

def test_read_config_triggers_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    # 故意写一个 port 错的 config
    bad = _make_valid_config(port=99999)
    write_config(bad)
    with pytest.raises(ConfigCorrupt, match="instance.port"):
        read_config()


def test_read_credentials_triggers_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    bad = Credentials(
        ssh_password=None, ssh_key_path=None,
        panel_authorization="abc", panel_autodl_token="tok",
        expires_estimate="",
    )
    write_credentials(bad)
    with pytest.raises(ConfigCorrupt, match="ssh"):
        read_credentials()


# ── JobStore.prune_old ─────────────────────────────────────────

def test_prune_old_keeps_recent(tmp_path):
    from kuake.server import JobStore
    store = JobStore(tmp_path)
    # 创建 5 个 job, 全 fresh
    jids = [store.create("push", {"task": f"t{i}"}) for i in range(5)]
    deleted = store.prune_old(keep_count=3, max_age_days=14)
    assert deleted == 0  # 都还嫩 (mtime ~now), 不删
    # 全在
    for jid in jids:
        assert (tmp_path / "jobs" / f"{jid}.json").exists()


def test_prune_old_deletes_old_beyond_keep_count(tmp_path):
    from kuake.server import JobStore
    store = JobStore(tmp_path)
    # 5 个 job, 全标 completed (running 不会被删)
    jids = [store.create("push", {"task": f"t{i}"}) for i in range(5)]
    for jid in jids:
        store.update(jid, status="completed")
    # 把 jids[0..2] 的 mtime 设到 30 天前
    old_ts = time.time() - 30 * 86400
    for jid in jids[:3]:
        for ext in (".json", ".log"):
            p = tmp_path / "jobs" / f"{jid}{ext}"
            os.utime(p, (old_ts, old_ts))
    deleted = store.prune_old(keep_count=2, max_age_days=14)
    # 最新的 2 个 (jids[3], jids[4]) 留;jids[0..2] 老 + completed + 在外 → 删
    assert deleted == 3
    for jid in jids[:3]:
        assert not (tmp_path / "jobs" / f"{jid}.json").exists()
        assert not (tmp_path / "jobs" / f"{jid}.log").exists()
    for jid in jids[3:]:
        assert (tmp_path / "jobs" / f"{jid}.json").exists()


def test_prune_old_never_deletes_running_job(tmp_path):
    from kuake.server import JobStore
    store = JobStore(tmp_path)
    jids = [store.create("push", {"task": f"t{i}"}) for i in range(5)]
    # 全设老 ts
    old_ts = time.time() - 30 * 86400
    for jid in jids:
        for ext in (".json", ".log"):
            os.utime(tmp_path / "jobs" / f"{jid}{ext}", (old_ts, old_ts))
    # 标记 第一个 为 running
    store.update(jids[0], status="running")
    # 其他 mark completed
    for jid in jids[1:]:
        store.update(jid, status="completed")
    # 在 update 时 mtime 又被 bump 了, 把它再设回老的
    for jid in jids:
        for ext in (".json", ".log"):
            os.utime(tmp_path / "jobs" / f"{jid}{ext}", (old_ts, old_ts))

    deleted = store.prune_old(keep_count=2, max_age_days=14)
    assert (tmp_path / "jobs" / f"{jids[0]}.json").exists(), "running job 被误删"
    # 完成的 + 老的 → 删
    completed_old = sum(
        1 for jid in jids[1:]
        if not (tmp_path / "jobs" / f"{jid}.json").exists()
    )
    assert completed_old >= 1
    assert deleted >= 1
