"""Persistent config + credentials with atomic writes and ACL hardening."""
from __future__ import annotations
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore

import tomli_w

from kuake.errors import ConfigMissing, ConfigCorrupt
from kuake.platform_guard import harden_file_acl


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    user: str
    auth_mode: str          # "password" or "key"
    panel_base: str
    fs_id: str              # quark fs id, default "quark1"
    local_backup_dir: str
    cloud_backup_path: str
    remote_tmp_dir: str
    created_at: str = ""
    last_refresh: str = ""


@dataclass(frozen=True)
class Credentials:
    ssh_password: Optional[str]
    ssh_key_path: Optional[str]
    panel_authorization: str
    panel_autodl_token: str
    expires_estimate: str  # ISO8601


@dataclass(frozen=True)
class ConfigPaths:
    home: Path
    config_file: Path
    credentials_file: Path
    state_dir: Path
    storage_state: Path
    lock_file: Path


def config_paths() -> ConfigPaths:
    home_env = os.environ.get("KUAKE_HOME")
    home = Path(home_env) if home_env else Path.home() / ".kuake"
    return ConfigPaths(
        home=home,
        config_file=home / "config.toml",
        credentials_file=home / "credentials.toml",
        state_dir=home / "state",
        storage_state=home / "state" / "storage_state.json",
        lock_file=home / ".lock",
    )


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def write_config(cfg: Config) -> None:
    paths = config_paths()
    data = asdict(cfg)
    if not data.get("created_at"):
        data["created_at"] = datetime.now().isoformat(timespec="seconds")
    nested = {
        "instance": {
            "host": data["host"], "port": data["port"],
            "user": data["user"], "auth_mode": data["auth_mode"],
        },
        "panel": {"base": data["panel_base"], "fs_id": data["fs_id"]},
        "quark": {
            "local_backup_dir": data["local_backup_dir"],
            "cloud_backup_path": data["cloud_backup_path"],
        },
        "remote": {"tmp_dir": data["remote_tmp_dir"]},
        "meta": {
            "created_at": data["created_at"],
            "last_refresh": data["last_refresh"],
        },
    }
    _atomic_write_text(paths.config_file, tomli_w.dumps(nested))


def read_config() -> Config:
    paths = config_paths()
    if not paths.config_file.exists():
        raise ConfigMissing(f"Config file not found: {paths.config_file}")
    try:
        data = tomllib.loads(paths.config_file.read_text("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, ValueError) as e:
        raise ConfigCorrupt(f"Cannot parse config: {e}") from e
    try:
        return Config(
            host=data["instance"]["host"],
            port=int(data["instance"]["port"]),
            user=data["instance"]["user"],
            auth_mode=data["instance"]["auth_mode"],
            panel_base=data["panel"]["base"],
            fs_id=data["panel"].get("fs_id", "quark1"),
            local_backup_dir=data["quark"]["local_backup_dir"],
            cloud_backup_path=data["quark"]["cloud_backup_path"],
            remote_tmp_dir=data["remote"]["tmp_dir"],
            created_at=data.get("meta", {}).get("created_at", ""),
            last_refresh=data.get("meta", {}).get("last_refresh", ""),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ConfigCorrupt(f"Config schema invalid: {e}") from e


def write_credentials(cred: Credentials) -> None:
    paths = config_paths()
    data = {
        "ssh": {
            "password": cred.ssh_password or "",
            "key_path": cred.ssh_key_path or "",
        },
        "panel": {
            "authorization": cred.panel_authorization,
            "autodl_token": cred.panel_autodl_token,
            "expires_estimate": cred.expires_estimate,
        },
    }
    _atomic_write_text(paths.credentials_file, tomli_w.dumps(data))
    harden_file_acl(paths.credentials_file)


def read_credentials() -> Credentials:
    paths = config_paths()
    if not paths.credentials_file.exists():
        raise ConfigMissing(f"Credentials file not found: {paths.credentials_file}")
    try:
        data = tomllib.loads(paths.credentials_file.read_text("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, ValueError) as e:
        raise ConfigCorrupt(f"Cannot parse credentials: {e}") from e
    try:
        ssh = data.get("ssh", {})
        panel = data["panel"]
        return Credentials(
            ssh_password=(ssh.get("password") or None),
            ssh_key_path=(ssh.get("key_path") or None),
            panel_authorization=panel["authorization"],
            panel_autodl_token=panel["autodl_token"],
            expires_estimate=panel.get("expires_estimate", ""),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ConfigCorrupt(f"Credentials schema invalid: {e}") from e


def update_last_refresh() -> None:
    """Bump meta.last_refresh in config.toml. Best-effort."""
    try:
        cfg = read_config()
        new_cfg = Config(
            **{**asdict(cfg), "last_refresh": datetime.now().isoformat(timespec="seconds")}
        )
        write_config(new_cfg)
    except (ConfigMissing, ConfigCorrupt):
        pass
