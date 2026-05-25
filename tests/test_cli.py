"""CLI smoke tests — argparse + dispatch wiring."""
import pytest
from kuake.cli import build_parser, main


def test_parser_version_exits_zero(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--version"])
    assert exc.value.code == 0


def test_parser_no_args_errors():
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([])
    assert exc.value.code != 0


def test_parser_push_requires_args():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["push"])


def test_parser_push_accepts_task_and_src():
    parser = build_parser()
    args = parser.parse_args(["push", "mytask", "./src"])
    assert args.cmd == "push"
    assert args.task == "mytask"
    assert args.src == "./src"
    assert args.no_unzip is False
    assert args.keep_zip is False


def test_parser_push_flags():
    parser = build_parser()
    args = parser.parse_args(["push", "t", "s", "--no-unzip", "--keep-zip"])
    assert args.no_unzip is True
    assert args.keep_zip is True


def test_parser_init_flags():
    parser = build_parser()
    args = parser.parse_args(["init", "--no-smoke", "--ssh-key"])
    assert args.cmd == "init"
    assert args.no_smoke is True
    assert args.ssh_key is True


def test_parser_reset_keep_credentials():
    parser = build_parser()
    args = parser.parse_args(["reset", "--keep-credentials"])
    assert args.keep_credentials is True


def test_parser_rm_requires_task():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["rm"])


def test_parser_no_config_doctor_exits_2(tmp_path, monkeypatch):
    """Without config, doctor should sys.exit(2)."""
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    monkeypatch.setattr("sys.platform", "win32")
    with pytest.raises(SystemExit) as exc:
        main(["doctor"])
    assert exc.value.code == 2


def test_task_name_validator():
    from kuake.commands.push import TASK_NAME_RE
    assert TASK_NAME_RE.match("myproject")
    assert TASK_NAME_RE.match("test-123")
    assert TASK_NAME_RE.match("a_b")
    assert not TASK_NAME_RE.match("with space")
    assert not TASK_NAME_RE.match("with/slash")
    assert not TASK_NAME_RE.match("with.dot")
    assert not TASK_NAME_RE.match("")
