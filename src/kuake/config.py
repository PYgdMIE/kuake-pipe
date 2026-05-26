"""Persistent config + credentials with atomic writes and ACL hardening."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore

import tomli_w

from kuake.errors import ConfigCorrupt, ConfigMissing
from kuake.platform_guard import harden_file_acl


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    user: str
    auth_mode: str          # "password" or "key"
    panel_base: str
    fs_id: str              # quark fs id, default "quark1"
    cloud_backup_path: str  # 上传目标云端路径,例如 "/kuake-uploads"
    remote_tmp_dir: str
    created_at: str = ""
    last_refresh: str = ""
    # 兼容旧 0.3 config 的字段, 不再使用 (留 None 避免读取报错)
    local_backup_dir: str = ""


@dataclass(frozen=True)
class Credentials:
    ssh_password: str | None
    ssh_key_path: str | None
    panel_authorization: str       # session_token from sign_in (Authorization header)
    panel_autodl_token: str        # JupyterLab token (AutodlAutoPanelToken header)
    expires_estimate: str          # ISO8601
    standalone_password_sha1: str = ""  # SHA1 of AutoPanel standalone password, for auto re-sign_in
    quark_cookie: str = ""              # full Quark Cookie header, for auto re-bind on new instance


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
            "cloud_backup_path": data["cloud_backup_path"],
        },
        "remote": {"tmp_dir": data["remote_tmp_dir"]},
        "meta": {
            "created_at": data["created_at"],
            "last_refresh": data["last_refresh"],
        },
    }
    _atomic_write_text(paths.config_file, tomli_w.dumps(nested))


def validate_config(cfg: Config) -> None:
    """Semantic checks beyond TOML shape — raise ConfigCorrupt with clear msg。

    catches:
      - empty / 假值字段
      - port 非法范围
      - auth_mode 取值
      - panel_base 不是 http(s) URL
      - 路径不是绝对路径 (云端 / 远端)
    """
    errors: list[str] = []
    if not cfg.host:
        errors.append("instance.host 不能为空")
    if not (0 < cfg.port < 65536):
        errors.append(f"instance.port 必须 1-65535, 现为 {cfg.port}")
    if not cfg.user:
        errors.append("instance.user 不能为空")
    if cfg.auth_mode not in ("password", "key"):
        errors.append(f"instance.auth_mode 必须 'password' 或 'key', 现为 {cfg.auth_mode!r}")
    if not cfg.panel_base.startswith(("http://", "https://")):
        errors.append(f"panel.base 必须 http(s):// 开头, 现为 {cfg.panel_base!r}")
    if not cfg.cloud_backup_path.startswith("/"):
        errors.append(f"quark.cloud_backup_path 必须以 / 开头, 现为 {cfg.cloud_backup_path!r}")
    if not cfg.remote_tmp_dir.startswith("/"):
        errors.append(f"remote.tmp_dir 必须以 / 开头, 现为 {cfg.remote_tmp_dir!r}")
    if errors:
        raise ConfigCorrupt("config.toml 字段无效:\n  - " + "\n  - ".join(errors))


def validate_credentials(cred: Credentials) -> None:
    """凭据语义校验 — 至少要有 SSH 凭据 + panel 鉴权头。

    注意: 故意不校验 ssh_key_path 是否真存在 (key 文件可能临时被移走但 config
    仍 "valid";真正用时 paramiko 会报清晰错。)
    """
    errors: list[str] = []
    if not (cred.ssh_password or cred.ssh_key_path):
        errors.append("ssh.password 和 ssh.key_path 不能同时空 (至少给一个)")
    if not cred.panel_authorization:
        errors.append("panel.authorization 不能为空 (跑 kuake refresh 重新签发)")
    if errors:
        raise ConfigCorrupt("credentials.toml 字段无效:\n  - " + "\n  - ".join(errors))


def read_config() -> Config:
    paths = config_paths()
    if not paths.config_file.exists():
        raise ConfigMissing(f"Config file not found: {paths.config_file}")
    try:
        data = tomllib.loads(paths.config_file.read_text("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, ValueError) as e:
        raise ConfigCorrupt(f"Cannot parse config: {e}") from e
    try:
        cfg = Config(
            host=data["instance"]["host"],
            port=int(data["instance"]["port"]),
            user=data["instance"]["user"],
            auth_mode=data["instance"]["auth_mode"],
            panel_base=data["panel"]["base"],
            fs_id=data["panel"].get("fs_id", "quark1"),
            cloud_backup_path=data["quark"]["cloud_backup_path"],
            local_backup_dir=data["quark"].get("local_backup_dir", ""),
            remote_tmp_dir=data["remote"]["tmp_dir"],
            created_at=data.get("meta", {}).get("created_at", ""),
            last_refresh=data.get("meta", {}).get("last_refresh", ""),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ConfigCorrupt(f"Config schema invalid: {e}") from e
    validate_config(cfg)
    return cfg


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
            "standalone_password_sha1": cred.standalone_password_sha1 or "",
        },
        "quark": {
            "cookie": cred.quark_cookie or "",
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
        quark = data.get("quark", {})
        cred = Credentials(
            ssh_password=(ssh.get("password") or None),
            ssh_key_path=(ssh.get("key_path") or None),
            panel_authorization=panel["authorization"],
            panel_autodl_token=panel["autodl_token"],
            expires_estimate=panel.get("expires_estimate", ""),
            standalone_password_sha1=panel.get("standalone_password_sha1", ""),
            quark_cookie=quark.get("cookie", ""),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ConfigCorrupt(f"Credentials schema invalid: {e}") from e
    validate_credentials(cred)
    return cred


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
