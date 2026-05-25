from kuake.errors import (
    KuakeError, AuthExpired, SshConnectFailed, CloudTimeout,
    SessionDead, ConcurrencyLock, UserInputError, ChromiumMirrorUnreachable,
)
from kuake import i18n


def test_kuake_error_has_required_attrs():
    e = AuthExpired()
    assert e.code == "AUTH_EXPIRED"
    assert e.hint_key == "AUTH_EXPIRED.hint"
    assert e.exit_code == 3


def test_user_input_error():
    e = UserInputError()
    assert e.exit_code == 2


def test_concurrency_lock_exit_7():
    e = ConcurrencyLock()
    assert e.exit_code == 7


def test_cloud_timeout_exit_6():
    e = CloudTimeout()
    assert e.exit_code == 6


def test_ssh_connect_failed_exit_5():
    e = SshConnectFailed()
    assert e.exit_code == 5


def test_chromium_mirror_unreachable_exit_4():
    e = ChromiumMirrorUnreachable()
    assert e.exit_code == 4


def test_session_dead_exit_3():
    e = SessionDead()
    assert e.exit_code == 3


def test_i18n_lookup_returns_message():
    assert "过期" in i18n.t("AUTH_EXPIRED")
    assert "refresh" in i18n.t("AUTH_EXPIRED.hint")


def test_i18n_unknown_key_returns_key():
    assert i18n.t("NONEXISTENT_KEY") == "NONEXISTENT_KEY"


def test_all_error_codes_have_i18n():
    codes = [
        "GENERIC", "USER_INPUT", "AUTH_EXPIRED", "SESSION_DEAD",
        "NETWORK", "CHROMIUM_MIRROR_UNREACHABLE", "SSH_CONNECT_FAILED",
        "SSH_CMD_FAILED", "CLOUD_TIMEOUT", "CONCURRENCY_LOCK",
        "PLATFORM_UNSUPPORTED", "SCRAPER_FAILED",
        "CONFIG_MISSING", "CONFIG_CORRUPT",
    ]
    for code in codes:
        assert i18n.t(code) != code, f"{code} missing i18n"
        assert i18n.t(f"{code}.hint") != f"{code}.hint", f"{code}.hint missing i18n"
