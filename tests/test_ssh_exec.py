import pytest
from pathlib import Path
from kuake.ssh_exec import SshExec, generate_ed25519_keypair
from kuake.errors import SshConnectFailed


def test_no_credentials_raises():
    s = SshExec(host="invalid.local", port=22, user="root")
    with pytest.raises(SshConnectFailed):
        s.connect()


def test_invalid_host_raises():
    s = SshExec(
        host="0.0.0.1", port=22, user="root", password="x", timeout=2
    )
    with pytest.raises(SshConnectFailed):
        s.connect()


def test_run_without_connect_raises():
    s = SshExec(host="x", port=22, user="root", password="x")
    with pytest.raises(SshConnectFailed):
        s.run("echo hi")


def test_generate_ed25519_keypair(tmp_path):
    key_path = tmp_path / "id_ed25519"
    priv, pub = generate_ed25519_keypair(key_path)
    assert priv == key_path
    assert priv.exists()
    assert pub.startswith("ssh-ed25519 ")
    assert pub.endswith(" kuake-pipe")
    # Verify private key file is non-empty
    assert priv.stat().st_size > 0
