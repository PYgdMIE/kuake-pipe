"""Tests for kuake auto / wait-running / confirm-create --yes."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from kuake.autodl_api import AutoDLClient, MachineMatch
from kuake.errors import NetworkError, UserInputError


@pytest.fixture
def kuake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "storage_state.json").write_text(json.dumps({
        "origins": [{
            "origin": "https://www.autodl.com",
            "localStorage": [{"name": "token", "value": "fake.jwt"}],
        }],
    }), encoding="utf-8")
    return tmp_path


def _match():
    return MachineMatch(
        machine_id="m1", machine_alias="A1",
        region_name="北京A", region_sign="north-A",
        gpu_name="RTX 3080 Ti", gpu_total=8, gpu_idle=2,
        chip_corp="nvidia", payg_price=1140,
        cpu_limit=12, mem_limit_in_byte=96 * 1024 ** 3,
        raw={},
    )


# ── wait_until_running ─────────────────────────────────────────

def test_wait_until_running_returns_when_status_running():
    client = AutoDLClient(jwt="x")
    inst_running = {"uuid": "u1", "status": "running", "machine_alias": "A"}
    with patch.object(client, "list_instances",
                      side_effect=[[{"uuid": "u1", "status": "starting"}],
                                   [inst_running]]):
        result = client.wait_until_running("u1", timeout=5, poll=0)
    assert result == inst_running


def test_wait_until_running_calls_progress_cb_on_status_change():
    client = AutoDLClient(jwt="x")
    seen: list[str] = []
    inst_running = {"uuid": "u1", "status": "running"}
    with patch.object(client, "list_instances",
                      side_effect=[
                          [{"uuid": "u1", "status": "starting"}],
                          [{"uuid": "u1", "status": "starting"}],  # 同状态, 不重复 cb
                          [inst_running],
                      ]):
        client.wait_until_running("u1", timeout=5, poll=0,
                                   progress_cb=seen.append)
    assert seen == ["starting", "running"]


def test_wait_until_running_raises_on_timeout():
    client = AutoDLClient(jwt="x")
    with patch.object(client, "list_instances",
                      return_value=[{"uuid": "u1", "status": "starting"}]):
        with pytest.raises(NetworkError, match="等待"):
            client.wait_until_running("u1", timeout=0, poll=0)


def test_wait_until_running_handles_not_found():
    client = AutoDLClient(jwt="x")
    with patch.object(client, "list_instances", return_value=[]):
        with pytest.raises(NetworkError):
            client.wait_until_running("u1", timeout=0, poll=0)


# ── confirm_create --yes ───────────────────────────────────────

def test_confirm_create_yes_skips_stdin_and_returns_uuid(tmp_path, kuake_home):
    from kuake.commands import confirm_create
    plan = tmp_path / "p.json"
    plan.write_text(json.dumps({
        "plan": {"machine_alias": "A", "region_name": "R",
                 "gpu_name": "G", "req_gpu_amount": 1,
                 "payg_price_yuan_per_hour": 1.0,
                 "image": "img", "expand_data_disk": 0,
                 "system_disk_change_size": 0},
        "payload": {"instance_info": {}},
    }), encoding="utf-8")
    fake = MagicMock()
    fake._post.return_value = "new-uuid"
    with patch("kuake.commands.confirm_create.AutoDLClient", return_value=fake), \
         patch("kuake.commands.confirm_create.time.sleep"):  # skip 3s grace
        result = confirm_create.run(plan_file=str(plan), yes=True)
    assert result == "new-uuid"
    fake._post.assert_called_once()


def test_confirm_create_yes_can_be_aborted_by_ctrlc(tmp_path, kuake_home):
    from kuake.commands import confirm_create
    plan = tmp_path / "p.json"
    plan.write_text(json.dumps({
        "plan": {}, "payload": {"instance_info": {}},
    }), encoding="utf-8")
    with patch("kuake.commands.confirm_create.time.sleep",
               side_effect=KeyboardInterrupt):
        result = confirm_create.run(plan_file=str(plan), yes=True)
    assert result is None


# ── wait-running command ───────────────────────────────────────

def test_wait_running_resolves_uuid_prefix(kuake_home):
    from kuake.commands import wait_running
    fake = MagicMock()
    fake.list_instances.return_value = [
        {"uuid": "abc12345", "status": "shutdown"},
        {"uuid": "def67890", "status": "running"},
    ]
    fake.wait_until_running.return_value = {
        "uuid": "def67890", "status": "running",
        "machine_alias": "A", "region_name": "R",
        "snapshot_gpu_alias_name": "G", "req_gpu_amount": 1,
    }
    with patch("kuake.commands.wait_running.AutoDLClient", return_value=fake):
        result = wait_running.run("def6", timeout=1, poll=0)
    assert result["uuid"] == "def67890"
    fake.wait_until_running.assert_called_once()
    assert fake.wait_until_running.call_args[0][0] == "def67890"


def test_wait_running_resolves_1based_index(kuake_home):
    from kuake.commands import wait_running
    fake = MagicMock()
    fake.list_instances.return_value = [
        {"uuid": "u1", "status": "running"},
        {"uuid": "u2", "status": "shutdown"},
    ]
    fake.wait_until_running.return_value = {
        "uuid": "u1", "machine_alias": "A", "region_name": "R",
        "snapshot_gpu_alias_name": "G", "req_gpu_amount": 1,
    }
    with patch("kuake.commands.wait_running.AutoDLClient", return_value=fake):
        wait_running.run("1", timeout=1, poll=0)
    assert fake.wait_until_running.call_args[0][0] == "u1"


def test_wait_running_unknown_target_raises(kuake_home):
    from kuake.commands import wait_running
    fake = MagicMock()
    fake.list_instances.return_value = [{"uuid": "u1", "status": "shutdown"}]
    with patch("kuake.commands.wait_running.AutoDLClient", return_value=fake):
        with pytest.raises(UserInputError, match="找不到"):
            wait_running.run("ghost", timeout=1, poll=0)


def test_wait_running_no_instances_raises(kuake_home):
    from kuake.commands import wait_running
    fake = MagicMock()
    fake.list_instances.return_value = []
    with patch("kuake.commands.wait_running.AutoDLClient", return_value=fake):
        with pytest.raises(UserInputError, match="没有任何实例"):
            wait_running.run("1", timeout=1, poll=0)


# ── auto command ───────────────────────────────────────────────

def test_auto_rejects_invalid_stop_after(kuake_home):
    from kuake.commands import auto
    with pytest.raises(UserInputError, match="stop_after"):
        auto.run(stop_after="invalid")


def test_auto_init_requires_autopanel_password(kuake_home):
    from kuake.commands import auto
    with pytest.raises(UserInputError, match="AutoPanel"):
        auto.run(stop_after="init", autopanel_password=None)


def test_auto_push_requires_task_and_src(kuake_home):
    from kuake.commands import auto
    with pytest.raises(UserInputError, match="--task"):
        auto.run(stop_after="push", autopanel_password="x", task=None, src="/x")


def test_auto_stop_after_create(kuake_home):
    """grab → confirm-create → 停。验证不调 wait_until_running / init / push。"""
    from kuake.commands import auto
    fake_client = MagicMock()
    fake_client.list_available.return_value = [_match()]
    with patch("kuake.commands.auto.AutoDLClient", return_value=fake_client), \
         patch("kuake.commands.auto.confirm_create.run",
               return_value="new-uuid-xyz") as cc_mock, \
         patch("kuake.commands.auto.time.sleep"):
        auto.run(stop_after="create", max_market_iters=5)
    cc_mock.assert_called_once()
    assert cc_mock.call_args.kwargs["yes"] is True
    fake_client.wait_until_running.assert_not_called()


def test_auto_market_no_match_after_max_iter(kuake_home):
    """没匹配 + max-iter 到上限 → 不报错, 静默返回。"""
    from kuake.commands import auto
    fake_client = MagicMock()
    fake_client.list_available.return_value = []  # 永远没匹配
    with patch("kuake.commands.auto.AutoDLClient", return_value=fake_client), \
         patch("kuake.commands.auto.time.sleep"), \
         patch("kuake.commands.auto.confirm_create.run") as cc_mock:
        auto.run(stop_after="create", max_market_iters=3, cpu_ok=True)
    cc_mock.assert_not_called()


def test_auto_stop_after_ready_calls_wait(kuake_home):
    from kuake.commands import auto
    fake_client = MagicMock()
    fake_client.list_available.return_value = [_match()]
    fake_client.wait_until_running.return_value = {
        "uuid": "new-uuid", "machine_alias": "A", "region_name": "R",
    }
    with patch("kuake.commands.auto.AutoDLClient", return_value=fake_client), \
         patch("kuake.commands.auto.confirm_create.run", return_value="new-uuid"), \
         patch("kuake.commands.auto.time.sleep"):
        auto.run(stop_after="ready", ready_timeout=10, max_market_iters=5)
    fake_client.wait_until_running.assert_called_once()


def test_auto_stop_after_push_runs_subprocesses(kuake_home, tmp_path):
    """跑完整链, 验证 init + push 各 spawn 一次子进程。"""
    from kuake.commands import auto
    src = tmp_path / "data"
    src.mkdir()
    fake_client = MagicMock()
    fake_client.list_available.return_value = [_match()]
    fake_client.wait_until_running.return_value = {
        "uuid": "new-uuid", "machine_alias": "A", "region_name": "R",
    }
    fake_client.list_instances.return_value = [
        {"uuid": "new-uuid", "status": "running"},
    ]
    fake_run = MagicMock()
    fake_run.return_value.returncode = 0
    with patch("kuake.commands.auto.AutoDLClient", return_value=fake_client), \
         patch("kuake.commands.auto.confirm_create.run", return_value="new-uuid"), \
         patch("kuake.commands.auto.subprocess.run", fake_run), \
         patch("kuake.commands.auto.time.sleep"):
        auto.run(
            stop_after="push",
            autopanel_password="pw",
            task="t1", src=str(src),
            max_market_iters=5,
        )
    # 2 个子进程: init + push
    assert fake_run.call_count == 2
    init_call = fake_run.call_args_list[0]
    push_call = fake_run.call_args_list[1]
    assert "init" in init_call.args[0]
    assert "--instance" in init_call.args[0]
    assert "1" in init_call.args[0]  # new instance 在 list_instances 里 idx=1
    assert "push" in push_call.args[0]
    assert "t1" in push_call.args[0]
    assert str(src) in push_call.args[0]


def test_auto_init_failure_propagates(kuake_home, tmp_path):
    from kuake.commands import auto
    src = tmp_path / "data"
    src.mkdir()
    fake_client = MagicMock()
    fake_client.list_available.return_value = [_match()]
    fake_client.wait_until_running.return_value = {"uuid": "new-uuid"}
    fake_client.list_instances.return_value = [{"uuid": "new-uuid"}]
    fake_run = MagicMock()
    fake_run.return_value.returncode = 1
    with patch("kuake.commands.auto.AutoDLClient", return_value=fake_client), \
         patch("kuake.commands.auto.confirm_create.run", return_value="new-uuid"), \
         patch("kuake.commands.auto.subprocess.run", fake_run), \
         patch("kuake.commands.auto.time.sleep"):
        with pytest.raises(UserInputError, match="init 失败"):
            auto.run(
                stop_after="push",
                autopanel_password="pw",
                task="t1", src=str(src),
                max_market_iters=5,
            )
