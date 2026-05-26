"""SSH execution wrapper with password/key dual-mode and unzip fallback."""
from __future__ import annotations

import shlex
import sys
from pathlib import Path

import paramiko

from kuake.errors import SshCommandFailed, SshConnectFailed


class SshExec:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str | None = None,
        key_path: str | None = None,
        timeout: int = 30,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.key_path = key_path
        self.timeout = timeout
        self._client: paramiko.SSHClient | None = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def connect(self) -> None:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if self.key_path:
                key = paramiko.Ed25519Key.from_private_key_file(str(self.key_path))
                c.connect(
                    self.host, self.port, self.user, pkey=key,
                    look_for_keys=False, allow_agent=False, timeout=self.timeout,
                )
            elif self.password:
                c.connect(
                    self.host, self.port, self.user, password=self.password,
                    look_for_keys=False, allow_agent=False, timeout=self.timeout,
                )
            else:
                raise SshConnectFailed("No password or key_path provided")
        except (paramiko.SSHException, OSError, EOFError) as e:
            raise SshConnectFailed(
                f"SSH connect to {self.host}:{self.port} failed: {e}"
            ) from e
        self._client = c

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def run(self, cmd: str, check: bool = True) -> tuple[int, str, str]:
        """Run command, return (exit_code, stdout, stderr)."""
        if self._client is None:
            raise SshConnectFailed("Not connected")
        _, o, e = self._client.exec_command(cmd, timeout=self.timeout)
        out = o.read().decode("utf-8", "replace")
        err_text = e.read().decode("utf-8", "replace")
        code = o.channel.recv_exit_status()
        if check and code != 0:
            raise SshCommandFailed(
                f"Command failed (exit={code}): {cmd}\n{err_text}"
            )
        return code, out, err_text

    def upload(self, local: Path, remote: str) -> None:
        if self._client is None:
            raise SshConnectFailed("Not connected")
        sftp = self._client.open_sftp()
        try:
            sftp.put(str(local), remote)
        finally:
            sftp.close()

    def unzip_remote(self, zip_path: str, dest: str) -> None:
        """Unzip with three-tier fallback: unzip → apt install unzip → python3 zipfile."""
        zip_q = shlex.quote(zip_path)
        dest_q = shlex.quote(dest)

        # Tier 1: native unzip
        code, _, _ = self.run("which unzip", check=False)
        if code == 0:
            self.run(
                f"mkdir -p {dest_q} && cd {dest_q} && "
                f"unzip -q -o {zip_q} && rm -f {zip_q}"
            )
            return

        # Tier 2: try apt install (non-interactive)
        code, _, _ = self.run("which apt-get", check=False)
        if code == 0:
            install_code, _, _ = self.run(
                "DEBIAN_FRONTEND=noninteractive apt-get install -y unzip",
                check=False,
            )
            if install_code == 0:
                self.run(
                    f"mkdir -p {dest_q} && cd {dest_q} && "
                    f"unzip -q -o {zip_q} && rm -f {zip_q}"
                )
                return

        # Tier 3: python3 zipfile
        py_code = (
            f"import zipfile,os;"
            f"os.makedirs({dest!r}, exist_ok=True);"
            f"zipfile.ZipFile({zip_path!r}).extractall({dest!r});"
            f"os.unlink({zip_path!r})"
        )
        self.run(f"python3 -c {shlex.quote(py_code)}")

    def test_connection(self) -> dict[str, str]:
        """Run smoke commands. Returns {whoami, df}."""
        _, who, _ = self.run("whoami")
        _, df, _ = self.run(
            "df -h /root/autodl-tmp 2>/dev/null || df -h /root", check=False
        )
        return {"whoami": who.strip(), "df": df.strip()}


def generate_ed25519_keypair(out_path: Path) -> tuple[Path, str]:
    """Generate ed25519 keypair via cryptography. Returns (private_key_path, public_key_str)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    priv = Ed25519PrivateKey.generate()
    # Write OpenSSH format private key (paramiko reads this)
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )
    out_path.write_bytes(pem)
    if sys.platform != "win32":
        out_path.chmod(0o600)

    # Build authorized_keys-style public string
    pub_ssh = priv.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("ascii")
    # pub_ssh looks like 'ssh-ed25519 AAAAC3...'  → append comment
    return out_path, f"{pub_ssh} kuake-pipe"
