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


def test_parser_instances():
    parser = build_parser()
    args = parser.parse_args(["instances"])
    assert args.cmd == "instances"


def test_parser_start_default():
    parser = build_parser()
    args = parser.parse_args(["start"])
    assert args.cmd == "start"
    assert args.target == "default"


def test_parser_start_with_number():
    parser = build_parser()
    args = parser.parse_args(["start", "2"])
    assert args.target == "2"


def test_parser_stop_with_yes():
    parser = build_parser()
    args = parser.parse_args(["stop", "1", "-y"])
    assert args.cmd == "stop"
    assert args.target == "1"
    assert args.yes is True


def test_resolve_target_default(monkeypatch):
    from kuake.commands.start import _resolve_target
    rows = [{"label": "a"}, {"label": "b"}]
    assert _resolve_target("default", rows) == 0


def test_resolve_target_valid_index():
    from kuake.commands.start import _resolve_target
    rows = [{"label": "a"}, {"label": "b"}, {"label": "c"}]
    assert _resolve_target("2", rows) == 1
    assert _resolve_target("3", rows) == 2


def test_resolve_target_invalid_raises():
    from kuake.commands.start import _resolve_target
    from kuake.errors import UserInputError
    rows = [{"label": "a"}]
    with pytest.raises(UserInputError):
        _resolve_target("abc", rows)
    with pytest.raises(UserInputError):
        _resolve_target("5", rows)
    with pytest.raises(UserInputError):
        _resolve_target("0", rows)
