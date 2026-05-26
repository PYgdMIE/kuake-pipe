"""Round 3 tests: --json output + kuake status + fail-rollback + headless preflight."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from kuake.errors import NetworkError, UserInputError


@pytest.fixture(autouse=True)
def _reset_json_mode():
    """capsys 在每个 test 间会重定向 sys.stderr — 防止 console.file 缓存到
    上一个 test 的 (已关闭) stream 上, 每个 test 跑完就 reset。"""
    yield
    from kuake.progress import set_json_mode
    set_json_mode(False)


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


# ── set_json_mode ──────────────────────────────────────────────

def test_set_json_mode_routes_console_to_stderr():
    import sys
    from kuake.progress import console, set_json_mode
    try:
        set_json_mode(True)
        assert console.file is sys.stderr
        set_json_mode(False)
        assert console.file is sys.stdout
    finally:
        set_json_mode(False)


# ── whoami --json ──────────────────────────────────────────────

def test_whoami_json_output(kuake_home, capsys):
    from kuake.commands import whoami
    fake = MagicMock()
    fake.wallet_balance.return_value = {
        "assets": 5155, "blocked_asset": 0, "accumulate": 21984,
        "voucher_balance": 100, "available_coupon_num": 3,
    }
    fake.list_instances.return_value = [
        {"status": "running"}, {"status": "shutdown"}, {"status": "running"},
    ]
    with patch("kuake.commands.whoami.AutoDLClient", return_value=fake):
        whoami.run(json_output=True)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["wallet"]["assets_yuan"] == 51.55
    assert data["instances"]["running"] == 2
    assert data["instances"]["total"] == 3


# ── instances --json ──────────────────────────────────────────

def test_instances_json_uses_api_not_dom(kuake_home, capsys):
    from kuake.commands import instances
    fake = MagicMock()
    fake.list_instances.return_value = [
        {"uuid": "u1", "machine_alias": "A", "region_name": "R",
         "snapshot_gpu_alias_name": "GPU1", "req_gpu_amount": 1,
         "status": "running", "image": "img"},
    ]
    # AutoDLClient 在 instances.run 内部 lazy import, 要 patch 上游
    with patch("kuake.autodl_api.AutoDLClient", return_value=fake):
        instances.run(json_output=True)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["uuid"] == "u1"
    assert data[0]["index"] == 1


# ── wait-running --json ────────────────────────────────────────

def test_wait_running_json_output(kuake_home, capsys):
    from kuake.commands import wait_running
    fake = MagicMock()
    fake.list_instances.return_value = [{"uuid": "u1", "status": "shutdown"}]
    fake.wait_until_running.return_value = {
        "uuid": "u1", "machine_alias": "A1", "region_name": "R1",
        "snapshot_gpu_alias_name": "RTX 5090", "req_gpu_amount": 2,
        "status": "running",
    }
    with patch("kuake.commands.wait_running.AutoDLClient", return_value=fake):
        wait_running.run("1", timeout=1, poll=0, json_output=True)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["uuid"] == "u1"
    assert data["gpu_name"] == "RTX 5090"
    assert data["gpu_count"] == 2


# ── grab --json ───────────────────────────────────────────────

def test_grab_json_matched(kuake_home, capsys):
    from kuake.autodl_api import MachineMatch
    from kuake.commands import grab
    m = MachineMatch(
        machine_id="m1", machine_alias="A1", region_name="北京A",
        region_sign="north-A", gpu_name="RTX 3080 Ti", gpu_total=8,
        gpu_idle=2, chip_corp="nvidia", payg_price=1140,
        cpu_limit=12, mem_limit_in_byte=96 * 1024**3, raw={},
    )
    fake = MagicMock()
    fake.list_available.return_value = [m]
    with patch("kuake.commands.grab.AutoDLClient", return_value=fake), \
         patch("kuake.commands.grab.time.sleep"):
        grab.run(gpu_types=["RTX 3080 Ti"], max_iterations=1,
                 poll_seconds=0, json_output=True)
    out = capsys.readouterr().out.strip()
    # 末行是 JSON (PLAN 文本也在 stderr 之前)
    lines = [line for line in out.splitlines() if line.startswith("{")]
    data = json.loads(lines[-1])
    assert data["matched"] is True
    assert "plan_file" in data
    assert data["summary"]["gpu_name"] == "RTX 3080 Ti"


def test_grab_json_no_match_after_max_iter(kuake_home, capsys):
    from kuake.commands import grab
    fake = MagicMock()
    fake.list_available.return_value = []
    with patch("kuake.commands.grab.AutoDLClient", return_value=fake), \
         patch("kuake.commands.grab.time.sleep"):
        grab.run(max_iterations=2, poll_seconds=0, json_output=True, cpu_ok=True)
    out = capsys.readouterr().out.strip()
    lines = [line for line in out.splitlines() if line.startswith("{")]
    data = json.loads(lines[-1])
    assert data["matched"] is False
    assert data["reason"] == "max_iter"


# ── auto --json ───────────────────────────────────────────────

def test_auto_json_success_at_create_stop(kuake_home, capsys):
    from kuake.autodl_api import MachineMatch
    from kuake.commands import auto
    m = MachineMatch(
        machine_id="m1", machine_alias="A1", region_name="R",
        region_sign="rs", gpu_name="G", gpu_total=4, gpu_idle=1,
        chip_corp="nvidia", payg_price=1000,
        cpu_limit=8, mem_limit_in_byte=32 * 1024**3, raw={},
    )
    fake_client = MagicMock()
    fake_client.list_available.return_value = [m]
    with patch("kuake.commands.auto.AutoDLClient", return_value=fake_client), \
         patch("kuake.commands.auto.confirm_create.run", return_value="new-uuid-x"), \
         patch("kuake.commands.auto.time.sleep"):
        auto.run(stop_after="create", max_market_iters=1, json_output=True)
    out = capsys.readouterr().out.strip()
    lines = [line for line in out.splitlines() if line.startswith("{")]
    data = json.loads(lines[-1])
    assert data["success"] is True
    assert data["new_uuid"] == "new-uuid-x"
    assert data["stage_reached"] == "created"


def test_auto_json_failure_emits_error(kuake_home, capsys):
    from kuake.commands import auto
    fake_client = MagicMock()
    fake_client.list_available.side_effect = NetworkError("无网")
    with patch("kuake.commands.auto.AutoDLClient", return_value=fake_client), \
         patch("kuake.commands.auto.time.sleep"), \
         pytest.raises(NetworkError):
        auto.run(stop_after="create", max_market_iters=1, json_output=True)
    out = capsys.readouterr().out.strip()
    lines = [line for line in out.splitlines() if line.startswith("{")]
    data = json.loads(lines[-1])
    assert data["success"] is False
    # auto 把内层 NetworkError 包装成 "市场轮询 N 次仍失败"
    assert "市场轮询" in data["error"]


# ── auto --fail-rollback ──────────────────────────────────────

def test_auto_fail_rollback_calls_stop(kuake_home, tmp_path):
    """链中失败 + new_uuid 已知 → 自动 spawn `kuake stop <uuid> -y`。"""
    from kuake.autodl_api import MachineMatch
    from kuake.commands import auto
    src = tmp_path / "data"
    src.mkdir()
    m = MachineMatch(
        machine_id="m1", machine_alias="A", region_name="R",
        region_sign="rs", gpu_name="G", gpu_total=4, gpu_idle=1,
        chip_corp="nvidia", payg_price=1000,
        cpu_limit=8, mem_limit_in_byte=32 * 1024**3, raw={},
    )
    fake_client = MagicMock()
    fake_client.list_available.return_value = [m]
    fake_client.wait_until_running.side_effect = NetworkError("等待超时")
    fake_run = MagicMock()
    fake_run.return_value.returncode = 0
    with patch("kuake.commands.auto.AutoDLClient", return_value=fake_client), \
         patch("kuake.commands.auto.confirm_create.run", return_value="new-uuid"), \
         patch("kuake.commands.auto.subprocess.run", fake_run), \
         patch("kuake.commands.auto.time.sleep"), \
         pytest.raises(NetworkError):
        auto.run(
            stop_after="ready",  # 在 wait 失败
            max_market_iters=1,
            fail_rollback=True,
        )
    # subprocess.run 应该有调用 kuake stop new-uuid -y
    calls = fake_run.call_args_list
    assert any(
        "stop" in c.args[0] and "new-uuid" in c.args[0]
        for c in calls
    ), f"没找到 kuake stop new-uuid 调用, calls={calls}"


def test_auto_no_rollback_when_not_created(kuake_home):
    """grab 阶段失败 (new_uuid 还未拿到) → 不应该 spawn stop。"""
    from kuake.commands import auto
    fake_client = MagicMock()
    fake_client.list_available.side_effect = NetworkError("market 挂了")
    fake_run = MagicMock()
    with patch("kuake.commands.auto.AutoDLClient", return_value=fake_client), \
         patch("kuake.commands.auto.subprocess.run", fake_run), \
         patch("kuake.commands.auto.time.sleep"), \
         pytest.raises(NetworkError):
        auto.run(stop_after="create", max_market_iters=1, fail_rollback=True)
    fake_run.assert_not_called()


# ── kuake status ──────────────────────────────────────────────

def test_status_json_lists_recent_jobs(kuake_home, capsys):
    from kuake.commands import status as status_cmd
    from kuake.server import JobStore
    store = JobStore(kuake_home)
    jid = store.create("push", {"task": "t1", "src": "/x"})
    store.update(jid, status="completed", exit_code=0)

    status_cmd.run(json_output=True)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert any(j["job_id"] == jid for j in data)


def test_status_single_job_json(kuake_home, capsys):
    from kuake.commands import status as status_cmd
    from kuake.server import JobStore
    store = JobStore(kuake_home)
    jid = store.create("auto", {"task": "—", "src": "—", "stop_after": "push"})
    store.log_path(jid).write_text("line a\nline b\n", encoding="utf-8")
    status_cmd.run(jid, json_output=True)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["meta"]["job_id"] == jid
    assert "line a" in data["log"]


def test_status_unknown_job_json(kuake_home, capsys):
    from kuake.commands import status as status_cmd
    status_cmd.run("nonexistent", json_output=True)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert "error" in data


def test_status_only_running_filters(kuake_home, capsys):
    from kuake.commands import status as status_cmd
    from kuake.server import JobStore
    store = JobStore(kuake_home)
    j1 = store.create("push", {"task": "running-one"})
    j2 = store.create("push", {"task": "done-one"})
    store.update(j2, status="completed")
    status_cmd.run(only_running=True, json_output=True)
    data = json.loads(capsys.readouterr().out.strip())
    ids = {j["job_id"] for j in data}
    assert j1 in ids
    assert j2 not in ids


# ── init --headless preflight ─────────────────────────────────

def test_init_headless_fails_when_jwt_expired(kuake_home, tmp_path, monkeypatch):
    """JWT 失效时 headless 应该立即报错, 不进浏览器循环。"""
    from kuake.commands import init as init_cmd
    fake_client = MagicMock()
    fake_client.list_instances.side_effect = NetworkError(
        "AutoDL /api/v1/instance: 登录超时 (code=AuthorizeFailed)"
    )
    with patch("kuake.autodl_api.AutoDLClient", return_value=fake_client):
        with pytest.raises(UserInputError, match="headless 预检失败"):
            init_cmd.run(headless=True)


def test_init_headless_fails_when_no_storage_state(tmp_path, monkeypatch):
    """没 storage_state 直接报错, 不去 ping API。"""
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    from kuake.commands import init as init_cmd
    with pytest.raises(UserInputError, match="--headless 要求"):
        init_cmd.run(headless=True)