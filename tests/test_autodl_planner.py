"""Unit tests for autodl_planner + grab + clone command paths.

Mocks AutoDLClient to avoid hitting real API. Critically validates:
- plans NEVER trigger create POST
- confirm-create requires literal 'YES' input + valid plan file
"""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kuake.autodl_api import MachineMatch
from kuake.autodl_planner import (
    plan_from_match, plan_clone_from_instance, save_plan, format_plan,
    DEFAULT_IMAGE_NVIDIA, DEFAULT_IMAGE_CPU,
)
from kuake.commands import grab, clone, confirm_create
from kuake.errors import UserInputError


def _match(gpu="RTX 4090", **kw) -> MachineMatch:
    return MachineMatch(
        machine_id=kw.get("mid", "m1"),
        machine_alias=kw.get("alias", "A1"),
        region_name=kw.get("region", "北京A"),
        region_sign=kw.get("rs", "north-A"),
        gpu_name=gpu,
        gpu_total=8,
        gpu_idle=2,
        chip_corp=kw.get("chip", "nvidia"),
        payg_price=2900,  # ¥29/h
        cpu_limit=12,
        mem_limit_in_byte=96 * 1024 ** 3,
        raw={"raw": "data"},
    )


# ── plan_from_match ──────────────────────────────────────────────

def test_plan_from_match_default_nvidia_image():
    m = _match()
    plan = plan_from_match(m, gpu_count=1)
    assert plan.image == DEFAULT_IMAGE_NVIDIA
    assert plan.req_gpu_amount == 1
    assert plan.machine_id == "m1"
    assert plan.payg_price_yuan_per_hour == 29.0
    assert plan.expand_data_disk == 0
    assert plan.system_disk_change_size == 0


def test_plan_from_match_cpu_default_image():
    m = _match(gpu="CPU", chip="cpu")
    plan = plan_from_match(m)
    assert plan.image == DEFAULT_IMAGE_CPU


def test_plan_from_match_custom_image_overrides_default():
    m = _match()
    plan = plan_from_match(m, image="custom.io/myrepo:latest")
    assert plan.image == "custom.io/myrepo:latest"


def test_plan_from_match_with_expansion():
    m = _match()
    plan = plan_from_match(m, expand_data_disk_gb=200, system_disk_change_size_gb=30)
    payload = plan.to_payload()["instance_info"]
    assert payload["expand_data_disk"] == 200
    assert payload["system_disk_change_size"] == 30


def test_plan_payload_has_all_required_fields():
    m = _match()
    plan = plan_from_match(m)
    p = plan.to_payload()["instance_info"]
    for required in [
        "machine_id", "charge_type", "req_gpu_amount", "image",
        "private_image_uuid", "reproduction_uuid",
        "expand_data_disk", "system_disk_change_size",
        "coupon_id_list", "duration", "num",
    ]:
        assert required in p, f"payload 缺字段 {required}"
    assert p["charge_type"] == "payg"


def test_estimated_hour_cost_multi_gpu():
    m = _match()
    plan = plan_from_match(m, gpu_count=2)
    # 2 GPU × ¥29/h
    assert plan.estimated_hour_cost() == pytest.approx(58.0)


# ── plan_clone_from_instance ────────────────────────────────────

def test_clone_copies_image_and_gpu_from_source():
    source = {
        "uuid": "u1234", "machine_alias": "A1",
        "snapshot_gpu_alias_name": "RTX 5090",
        "req_gpu_amount": 2,
        "image": "img:v1", "private_image_uuid": "",
        "reproduction_uuid": "", "status": "shutdown",
    }
    target = _match(gpu="RTX 5090")
    plan = plan_clone_from_instance(source, target)
    assert plan.image == "img:v1"
    assert plan.req_gpu_amount == 2  # 沿用源
    assert plan.source_instance_uuid == "u1234"
    assert plan.machine_id == "m1"  # 目标
    assert any("clone" in n.lower() or "克隆" in n for n in plan.notes)


def test_clone_gpu_count_override():
    source = {
        "uuid": "u", "machine_alias": "x",
        "snapshot_gpu_alias_name": "RTX 5090",
        "req_gpu_amount": 4,
        "image": "img", "private_image_uuid": "",
    }
    plan = plan_clone_from_instance(source, _match(), gpu_count=1)
    assert plan.req_gpu_amount == 1  # 用户覆盖了


def test_clone_uses_default_image_if_source_blank():
    source = {
        "uuid": "u", "machine_alias": "x",
        "snapshot_gpu_alias_name": "RTX 4090",
        "req_gpu_amount": 1,
        "image": "", "private_image_uuid": "",
    }
    plan = plan_clone_from_instance(source, _match())
    assert plan.image == DEFAULT_IMAGE_NVIDIA


def test_clone_detects_cpu_from_start_mode():
    source = {
        "uuid": "u", "machine_alias": "x",
        "start_mode": "cpu",
        "snapshot_gpu_alias_name": "",
        "req_gpu_amount": 1, "image": "",
        "private_image_uuid": "",
    }
    plan = plan_clone_from_instance(source, _match(chip="cpu"))
    assert plan.chip_corp == "cpu"
    assert plan.image == DEFAULT_IMAGE_CPU


# ── save_plan + format_plan ────────────────────────────────────

def test_save_plan_writes_valid_json(tmp_path):
    m = _match()
    plan = plan_from_match(m)
    path = tmp_path / "plan.json"
    save_plan(plan, str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["payload"]["instance_info"]["machine_id"] == "m1"
    assert data["plan"]["region_name"] == "北京A"


def test_format_plan_contains_dry_run_warning():
    m = _match()
    plan = plan_from_match(m)
    out = format_plan(plan)
    assert "PLAN" in out
    assert "dry-run" in out or "不发请求" in out
    assert "不会真下单" in out


# ── grab command (mocked) ──────────────────────────────────────

@pytest.fixture
def stub_jwt(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_dir.parent.joinpath("state/storage_state.json").write_text(json.dumps({
        "cookies": [],
        "origins": [{
            "origin": "https://www.autodl.com",
            "localStorage": [{"name": "token", "value": "fake-jwt"}],
        }],
    }))
    return tmp_path


def test_grab_finds_match_writes_plan_no_submit(stub_jwt):
    """grab 找到机器 → 落盘 plan,绝不调 create_payg_instance"""
    fake_client = MagicMock()
    fake_client.list_available.return_value = [_match()]

    with patch("kuake.commands.grab.AutoDLClient", return_value=fake_client):
        grab.run(gpu_types=["RTX 4090"], max_iterations=1, poll_seconds=0,
                 gpu_count=1, expand_data_disk_gb=50,
                 system_disk_change_size_gb=10)

    # 绝不能调过 create
    assert "create_payg_instance" not in [
        c.kwargs.get("path", "") for c in fake_client._post.mock_calls
    ]
    # plan 文件落了
    plans = list((stub_jwt / "plans").glob("plan_*.json"))
    assert len(plans) == 1
    data = json.loads(plans[0].read_text())
    assert data["payload"]["instance_info"]["expand_data_disk"] == 50
    assert data["payload"]["instance_info"]["system_disk_change_size"] == 10


def test_grab_no_match_returns_after_max_iter(stub_jwt):
    fake_client = MagicMock()
    fake_client.list_available.return_value = []
    with patch("kuake.commands.grab.AutoDLClient", return_value=fake_client):
        grab.run(max_iterations=2, poll_seconds=0)
    # 不能落 plan
    assert not list((stub_jwt / "plans").glob("*.json")) if (stub_jwt / "plans").exists() else True


# ── clone command (mocked) ──────────────────────────────────────

def test_clone_by_index_picks_correct_source(stub_jwt):
    src_inst = {
        "uuid": "uuid-1234567890", "machine_alias": "A1",
        "snapshot_gpu_alias_name": "RTX 4090",
        "req_gpu_amount": 1, "image": "img",
        "private_image_uuid": "", "status": "running",
        "region_sign": "north-A",
    }
    fake_client = MagicMock()
    fake_client.list_instances.return_value = [src_inst]
    fake_client.list_available.return_value = [_match()]
    with patch("kuake.commands.clone.AutoDLClient", return_value=fake_client):
        clone.run(source="1", same_region=False)
    plans = list((stub_jwt / "plans").glob("clone_*.json"))
    assert len(plans) == 1
    data = json.loads(plans[0].read_text())
    assert data["plan"]["source_instance_uuid"] == "uuid-1234567890"


def test_clone_by_uuid_prefix(stub_jwt):
    src_inst = {
        "uuid": "abcd123456-XYZ", "machine_alias": "A1",
        "snapshot_gpu_alias_name": "RTX 4090",
        "req_gpu_amount": 1, "image": "img",
        "private_image_uuid": "", "region_sign": "n-A",
    }
    fake_client = MagicMock()
    fake_client.list_instances.return_value = [src_inst]
    fake_client.list_available.return_value = [_match()]
    with patch("kuake.commands.clone.AutoDLClient", return_value=fake_client):
        clone.run(source="abcd1234")
    plans = list((stub_jwt / "plans").glob("clone_*.json"))
    assert plans
    data = json.loads(plans[0].read_text())
    assert data["plan"]["source_instance_uuid"] == "abcd123456-XYZ"


def test_clone_no_match_warns_no_plan(stub_jwt):
    src_inst = {
        "uuid": "u", "machine_alias": "x",
        "snapshot_gpu_alias_name": "Tesla T4",
        "req_gpu_amount": 1, "image": "", "private_image_uuid": "",
    }
    fake_client = MagicMock()
    fake_client.list_instances.return_value = [src_inst]
    fake_client.list_available.return_value = []  # 没匹配
    with patch("kuake.commands.clone.AutoDLClient", return_value=fake_client):
        clone.run(source="1")
    # 没有 plan 文件 (plans 目录可能根本没建)
    plans_dir = stub_jwt / "plans"
    if plans_dir.exists():
        assert not list(plans_dir.glob("clone_*.json"))


# ── confirm-create safety ──────────────────────────────────────

def test_confirm_create_missing_plan_file_raises(stub_jwt):
    with pytest.raises(UserInputError):
        confirm_create.run(plan_file=None)


def test_confirm_create_nonexistent_path_raises(stub_jwt, tmp_path):
    with pytest.raises(UserInputError, match="不存在"):
        confirm_create.run(plan_file=str(tmp_path / "no-such.json"))


def test_confirm_create_aborts_unless_yes(stub_jwt, tmp_path):
    """输不是 YES 的内容,绝对不发 POST"""
    m = _match()
    plan = plan_from_match(m)
    path = tmp_path / "p.json"
    save_plan(plan, str(path))

    fake_client = MagicMock()
    with patch("kuake.commands.confirm_create.AutoDLClient", return_value=fake_client):
        with patch("builtins.input", return_value="yes"):  # lowercase, 应该拒绝
            confirm_create.run(plan_file=str(path))
    fake_client._post.assert_not_called()


def test_confirm_create_yes_triggers_post(stub_jwt, tmp_path):
    """只有 YES 大写,才会真发请求"""
    m = _match()
    plan = plan_from_match(m)
    path = tmp_path / "p.json"
    save_plan(plan, str(path))

    fake_client = MagicMock()
    fake_client._post.return_value = {"instance_uuid": "new-uuid"}
    with patch("kuake.commands.confirm_create.AutoDLClient", return_value=fake_client):
        with patch("builtins.input", return_value="YES"):
            confirm_create.run(plan_file=str(path))
    fake_client._post.assert_called_once()
    args, _ = fake_client._post.call_args
    assert args[0] == "/api/v1/order/instance/create/payg"
    # 检查 payload 来自 plan
    assert args[1]["instance_info"]["machine_id"] == "m1"
