"""更多边界 / 错误路径单测,覆盖 whoami / grab 过滤 / clone 交互 / confirm-create 破损。"""
from __future__ import annotations
import json
from unittest.mock import MagicMock, patch

import pytest

from kuake.autodl_api import MachineMatch
from kuake.autodl_planner import (
    InstancePlan, plan_from_match, save_plan, format_plan,
)
from kuake.commands import clone, confirm_create, grab, whoami
from kuake.errors import ConfigMissing, UserInputError


@pytest.fixture
def kuake_home_with_jwt(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "storage_state.json").write_text(json.dumps({
        "cookies": [],
        "origins": [{
            "origin": "https://www.autodl.com",
            "localStorage": [{"name": "token", "value": "fake-jwt"}],
        }],
    }))
    return tmp_path


def _match(**kw):
    return MachineMatch(
        machine_id=kw.get("mid", "m1"),
        machine_alias=kw.get("alias", "A1"),
        region_name=kw.get("region", "北京A"),
        region_sign=kw.get("rs", "north-A"),
        gpu_name=kw.get("gpu", "RTX 4090"),
        gpu_total=8,
        gpu_idle=kw.get("idle", 2),
        chip_corp=kw.get("chip", "nvidia"),
        payg_price=kw.get("price", 2900),
        cpu_limit=12,
        mem_limit_in_byte=96 * 1024 ** 3,
        raw={},
    )


# ── whoami ─────────────────────────────────────────────────────

def test_whoami_displays_wallet_and_instances(kuake_home_with_jwt, capsys):
    fake_client = MagicMock()
    fake_client.wallet_balance.return_value = {
        "assets": 51550, "blocked_asset": 0, "accumulate": 2198450,
        "voucher_balance": 1000, "available_coupon_num": 3,
    }
    fake_client.list_instances.return_value = [
        {"status": "running"}, {"status": "shutdown"}, {"status": "running"},
    ]
    with patch("kuake.commands.whoami.AutoDLClient", return_value=fake_client):
        whoami.run()
    out = capsys.readouterr().out
    assert "515.50" in out  # 现金
    assert "21984.50" in out  # 累计
    assert "运行中 2 台" in out
    assert "10.00" in out  # 代金券
    assert "3 张" in out  # 优惠券


def test_whoami_handles_wallet_failure_gracefully(kuake_home_with_jwt, capsys):
    fake_client = MagicMock()
    fake_client.wallet_balance.side_effect = Exception("net")
    fake_client.list_instances.return_value = []
    with patch("kuake.commands.whoami.AutoDLClient", return_value=fake_client):
        whoami.run()
    out = capsys.readouterr().out
    # 不崩,显示 0 实例
    assert "0" in out


# ── grab 过滤组合 ────────────────────────────────────────────────

def test_grab_filters_cpu_when_cpu_not_ok(kuake_home_with_jwt):
    fake_client = MagicMock()
    fake_client.list_available.return_value = [
        _match(gpu="CPU", chip="cpu"),
        _match(gpu="RTX 4090"),
    ]
    with patch("kuake.commands.grab.AutoDLClient", return_value=fake_client):
        grab.run(cpu_ok=False, max_iterations=1, poll_seconds=0)
    plans = list((kuake_home_with_jwt / "plans").glob("plan_*.json"))
    # 应该选了 RTX 4090,不是 CPU
    data = json.loads(plans[0].read_text())
    assert data["plan"]["chip_corp"] == "nvidia"


def test_grab_accepts_cpu_when_cpu_ok(kuake_home_with_jwt):
    fake_client = MagicMock()
    fake_client.list_available.return_value = [
        _match(gpu="CPU", chip="cpu"),  # 第一个就是 CPU
    ]
    with patch("kuake.commands.grab.AutoDLClient", return_value=fake_client):
        grab.run(cpu_ok=True, max_iterations=1, poll_seconds=0)
    plans = list((kuake_home_with_jwt / "plans").glob("plan_*.json"))
    data = json.loads(plans[0].read_text())
    assert data["plan"]["chip_corp"] == "cpu"


def test_grab_with_expansion_writes_correct_payload(kuake_home_with_jwt):
    fake_client = MagicMock()
    fake_client.list_available.return_value = [_match()]
    with patch("kuake.commands.grab.AutoDLClient", return_value=fake_client):
        grab.run(
            gpu_count=4,
            expand_data_disk_gb=200,
            system_disk_change_size_gb=50,
            max_iterations=1, poll_seconds=0,
        )
    plans = list((kuake_home_with_jwt / "plans").glob("plan_*.json"))
    data = json.loads(plans[0].read_text())
    p = data["payload"]["instance_info"]
    assert p["req_gpu_amount"] == 4
    assert p["expand_data_disk"] == 200
    assert p["system_disk_change_size"] == 50
    # 时费 = ¥29 × 4 GPU = ¥116/h
    assert data["plan"]["payg_price_yuan_per_hour"] == 29.0


def test_grab_custom_image_in_payload(kuake_home_with_jwt):
    fake_client = MagicMock()
    fake_client.list_available.return_value = [_match()]
    with patch("kuake.commands.grab.AutoDLClient", return_value=fake_client):
        grab.run(
            image="my.io/custom:tag",
            max_iterations=1, poll_seconds=0,
        )
    plans = list((kuake_home_with_jwt / "plans").glob("plan_*.json"))
    data = json.loads(plans[0].read_text())
    assert data["payload"]["instance_info"]["image"] == "my.io/custom:tag"


def test_grab_missing_jwt_raises_config_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    # 没有 storage_state.json
    with pytest.raises(ConfigMissing):
        grab.run(max_iterations=1, poll_seconds=0)


# ── clone 错误路径 ───────────────────────────────────────────────

def test_clone_no_instances_raises(kuake_home_with_jwt):
    fake_client = MagicMock()
    fake_client.list_instances.return_value = []
    with patch("kuake.commands.clone.AutoDLClient", return_value=fake_client):
        with pytest.raises(UserInputError, match="没有任何实例"):
            clone.run(source="1")


def test_clone_invalid_source_raises(kuake_home_with_jwt):
    fake_client = MagicMock()
    fake_client.list_instances.return_value = [
        {"uuid": "abc-123", "machine_alias": "A1",
         "snapshot_gpu_alias_name": "RTX", "req_gpu_amount": 1,
         "image": "", "private_image_uuid": ""},
    ]
    with patch("kuake.commands.clone.AutoDLClient", return_value=fake_client):
        with pytest.raises(UserInputError, match="找不到"):
            clone.run(source="zzzz-nonexistent")


def test_clone_index_out_of_range_falls_to_uuid_match_failure(kuake_home_with_jwt):
    """source='99' 不是有效索引(只有 1 个实例), 也不匹配任何 uuid 前缀 → 抛错"""
    fake_client = MagicMock()
    fake_client.list_instances.return_value = [
        {"uuid": "abc-123", "machine_alias": "A1",
         "snapshot_gpu_alias_name": "RTX", "req_gpu_amount": 1,
         "image": "", "private_image_uuid": ""},
    ]
    with patch("kuake.commands.clone.AutoDLClient", return_value=fake_client):
        with pytest.raises(UserInputError, match="找不到"):
            clone.run(source="99")


def test_clone_interactive_mode(kuake_home_with_jwt):
    """source=None 时弹列表交互, 用 input 选编号"""
    src = {"uuid": "u1", "machine_alias": "X",
           "snapshot_gpu_alias_name": "RTX", "req_gpu_amount": 1,
           "image": "img", "private_image_uuid": "",
           "region_sign": "north-A"}
    fake_client = MagicMock()
    fake_client.list_instances.return_value = [src]
    fake_client.list_available.return_value = [_match()]
    with patch("kuake.commands.clone.AutoDLClient", return_value=fake_client), \
         patch("builtins.input", return_value="1"):
        clone.run()  # source=None
    plans = list((kuake_home_with_jwt / "plans").glob("clone_*.json"))
    assert plans
    data = json.loads(plans[0].read_text())
    assert data["plan"]["source_instance_uuid"] == "u1"


def test_clone_interactive_invalid_input_raises(kuake_home_with_jwt):
    fake_client = MagicMock()
    fake_client.list_instances.return_value = [
        {"uuid": "u1", "machine_alias": "X",
         "snapshot_gpu_alias_name": "RTX", "req_gpu_amount": 1,
         "image": "i", "private_image_uuid": ""},
    ]
    with patch("kuake.commands.clone.AutoDLClient", return_value=fake_client), \
         patch("builtins.input", return_value="abc"):
        with pytest.raises(UserInputError, match="无效编号"):
            clone.run()


# ── confirm-create 错误路径 ────────────────────────────────────

def test_confirm_create_corrupt_json_raises(kuake_home_with_jwt, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json {{{")
    with pytest.raises(UserInputError, match="解析失败"):
        confirm_create.run(plan_file=str(bad))


def test_confirm_create_missing_payload_field_raises(kuake_home_with_jwt, tmp_path):
    """plan 文件没 payload 字段"""
    bad = tmp_path / "noplay.json"
    bad.write_text(json.dumps({"plan": {"machine_id": "x"}}))
    with pytest.raises(UserInputError, match="无效"):
        confirm_create.run(plan_file=str(bad))


def test_confirm_create_eof_aborts(kuake_home_with_jwt, tmp_path):
    """stdin EOF 时(管道关闭等)安全取消"""
    plan = plan_from_match(_match())
    path = tmp_path / "p.json"
    save_plan(plan, str(path))

    fake_client = MagicMock()
    with patch("kuake.commands.confirm_create.AutoDLClient", return_value=fake_client), \
         patch("builtins.input", side_effect=EOFError):
        confirm_create.run(plan_file=str(path))
    fake_client._post.assert_not_called()


def test_confirm_create_ctrl_c_aborts(kuake_home_with_jwt, tmp_path):
    plan = plan_from_match(_match())
    path = tmp_path / "p.json"
    save_plan(plan, str(path))

    fake_client = MagicMock()
    with patch("kuake.commands.confirm_create.AutoDLClient", return_value=fake_client), \
         patch("builtins.input", side_effect=KeyboardInterrupt):
        confirm_create.run(plan_file=str(path))
    fake_client._post.assert_not_called()


# ── format_plan 内容稳定性 (规避未来 regression) ───────────────────

def test_format_plan_shows_all_critical_fields():
    """plan 打印里必须有: 机器名 / GPU / 镜像 / 数据盘 / 系统盘 / 单价 / 警告"""
    plan = plan_from_match(_match(), expand_data_disk_gb=100, gpu_count=2)
    out = format_plan(plan)
    for keyword in [
        "区域", "机器", "GPU", "RTX 4090",
        "镜像", "数据盘扩容", "系统盘扩容",
        "单价", "估算时费", "不会真下单",
        "100",  # 扩容 GB
    ]:
        assert keyword in out, f"plan 打印里缺关键字 {keyword!r}"


def test_format_plan_with_private_image():
    plan = InstancePlan(
        machine_id="m", machine_alias="A", region_name="N",
        gpu_name="GPU", chip_corp="nvidia",
        private_image_uuid="abc-private",
    )
    out = format_plan(plan)
    assert "[私有] uuid=abc-private" in out
    assert "[公共]" not in out


def test_format_plan_with_coupon():
    plan = InstancePlan(
        machine_id="m", machine_alias="A", region_name="N",
        gpu_name="GPU", chip_corp="nvidia",
        coupon_id_list=["c1", "c2"],
    )
    out = format_plan(plan)
    assert "c1" in out and "c2" in out


# ── 价格计算 ────────────────────────────────────────────────────

def test_estimated_cost_with_num_multiple():
    plan = plan_from_match(_match(price=10000), gpu_count=2)  # ¥100/h × 2 = ¥200/h
    plan.num = 3  # 创建 3 台
    assert plan.estimated_hour_cost() == pytest.approx(600.0)


def test_zero_price_no_crash():
    plan = plan_from_match(_match(price=0))
    assert plan.payg_price_yuan_per_hour == 0.0
    assert plan.estimated_hour_cost() == 0.0
