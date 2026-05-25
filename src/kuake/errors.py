"""Typed exceptions. Raise message is English (stack trace friendly).
Display layer translates via i18n.t(code) / i18n.t(hint_key)."""
from __future__ import annotations


class KuakeError(Exception):
    code: str = "GENERIC"
    hint_key: str = "GENERIC.hint"
    exit_code: int = 1


class UserInputError(KuakeError):
    code = "USER_INPUT"
    hint_key = "USER_INPUT.hint"
    exit_code = 2


class AuthExpired(KuakeError):
    code = "AUTH_EXPIRED"
    hint_key = "AUTH_EXPIRED.hint"
    exit_code = 3


class SessionDead(KuakeError):
    code = "SESSION_DEAD"
    hint_key = "SESSION_DEAD.hint"
    exit_code = 3


class NetworkError(KuakeError):
    code = "NETWORK"
    hint_key = "NETWORK.hint"
    exit_code = 4


class ChromiumMirrorUnreachable(KuakeError):
    code = "CHROMIUM_MIRROR_UNREACHABLE"
    hint_key = "CHROMIUM_MIRROR_UNREACHABLE.hint"
    exit_code = 4


class SshConnectFailed(KuakeError):
    code = "SSH_CONNECT_FAILED"
    hint_key = "SSH_CONNECT_FAILED.hint"
    exit_code = 5


class SshCommandFailed(KuakeError):
    code = "SSH_CMD_FAILED"
    hint_key = "SSH_CMD_FAILED.hint"
    exit_code = 5


class CloudTimeout(KuakeError):
    code = "CLOUD_TIMEOUT"
    hint_key = "CLOUD_TIMEOUT.hint"
    exit_code = 6


class ConcurrencyLock(KuakeError):
    code = "CONCURRENCY_LOCK"
    hint_key = "CONCURRENCY_LOCK.hint"
    exit_code = 7


class PlatformUnsupported(KuakeError):
    code = "PLATFORM_UNSUPPORTED"
    hint_key = "PLATFORM_UNSUPPORTED.hint"
    exit_code = 1


class ScraperFailed(KuakeError):
    code = "SCRAPER_FAILED"
    hint_key = "SCRAPER_FAILED.hint"
    exit_code = 1


class ConfigMissing(KuakeError):
    code = "CONFIG_MISSING"
    hint_key = "CONFIG_MISSING.hint"
    exit_code = 1


class ConfigCorrupt(KuakeError):
    code = "CONFIG_CORRUPT"
    hint_key = "CONFIG_CORRUPT.hint"
    exit_code = 1
