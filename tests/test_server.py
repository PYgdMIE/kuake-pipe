"""Server route tests (Flask) — mocked AutoDLClient + storage_state."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from kuake.autodl_api import MachineMatch


@pytest.fixture
def kuake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KUAKE_HOME", str(tmp_path))
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "storage_state.json"
    state_file.write_text(json.dumps({
        "origins": [{
            "origin": "https://www.autodl.com",
            "localStorage": [{"name": "token", "value": "fake.jwt.token"}],
        }],
    }), encoding="utf-8")
    return tmp_path


@pytest.fixture
def app(kuake_home):
    from kuake.server import create_app
    a = create_app()
    a.config["TESTING"] = True
    return a


@pytest.fixture
def client(app):
    return app.test_client()


def _match(machine_id="m1", price=10000, gpu="RTX 4090"):
    return MachineMatch(
        machine_id=machine_id, machine_alias="A1",
        region_name="北京A", region_sign="north-A",
        gpu_name=gpu, gpu_total=8, gpu_idle=2,
        chip_corp="nvidia", payg_price=price,
        cpu_limit=12, mem_limit_in_byte=96 * 1024 ** 3,
        raw={},
    )


# ── /api/market ────────────────────────────────────────────────

def test_market_returns_matches(client):
    fake = MagicMock()
    fake.list_available.return_value = [_match(), _match(machine_id="m2", price=20000)]
    with patch("kuake.server.AutoDLClient", return_value=fake):
        r = client.get("/api/market")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["matches"]) == 2
    assert data["matches"][0]["price_yuan_per_hour"] == 10.0  # 10000 / 1000
    assert data["matches"][1]["price_yuan_per_hour"] == 20.0


def test_market_filters_cpu_unless_cpu_ok(client):
    fake = MagicMock()
    fake.list_available.return_value = [
        _match(machine_id="cpu1", gpu="CPU"),
        _match(machine_id="gpu1"),
    ]
    # CPU one should be filtered out by default
    with patch("kuake.server.AutoDLClient", return_value=fake):
        # Need to override chip_corp on the CPU match
        fake.list_available.return_value[0].chip_corp = "cpu"
        r = client.get("/api/market")
    data = r.get_json()
    assert all(m["machine_id"] != "cpu1" for m in data["matches"])

    with patch("kuake.server.AutoDLClient", return_value=fake):
        fake.list_available.return_value[0].chip_corp = "cpu"
        r = client.get("/api/market?cpu_ok=true")
    data = r.get_json()
    assert any(m["machine_id"] == "cpu1" for m in data["matches"])


# ── /api/grab-plan ─────────────────────────────────────────────

def test_grab_plan_creates_file_and_returns_summary(client, kuake_home):
    fake = MagicMock()
    fake.list_available.return_value = [_match(machine_id="abc123", price=5000)]
    with patch("kuake.server.AutoDLClient", return_value=fake):
        r = client.post("/api/grab-plan", json={
            "machine_id": "abc123",
            "gpu_count": 2,
            "expand_data_disk_gb": 100,
            "system_disk_change_size_gb": 0,
        })
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["gpu_count"] == 2
    assert data["summary"]["expand_data_disk_gb"] == 100
    assert data["summary"]["price_yuan_per_hour"] == 5.0
    # 文件落盘 + payload schema 正确
    assert (kuake_home / "plans").exists()
    plan_path = data["plan_file"]
    plan = json.loads(open(plan_path, encoding="utf-8").read())
    assert plan["payload"]["instance_info"]["expand_data_disk"] == 100 * 1024 ** 3


def test_grab_plan_unknown_machine_returns_410(client):
    fake = MagicMock()
    fake.list_available.return_value = [_match(machine_id="abc123")]
    with patch("kuake.server.AutoDLClient", return_value=fake):
        r = client.post("/api/grab-plan", json={"machine_id": "ghost"})
    assert r.status_code == 410  # gone — 没匹配


def test_grab_plan_missing_machine_id_returns_400(client):
    r = client.post("/api/grab-plan", json={})
    assert r.status_code == 400


# ── /api/confirm-create ────────────────────────────────────────

def test_confirm_create_without_yes_rejects(client, tmp_path):
    plan_file = tmp_path / "p.json"
    plan_file.write_text(json.dumps({"payload": {"x": 1}}), encoding="utf-8")
    r = client.post("/api/confirm-create",
                    json={"plan_file": str(plan_file), "yes": "yes"})
    assert r.status_code == 403


def test_confirm_create_with_missing_file_returns_404(client):
    r = client.post("/api/confirm-create",
                    json={"plan_file": "/nonexistent.json", "yes": "YES"})
    assert r.status_code == 404


def test_confirm_create_with_yes_calls_autodl(client, tmp_path):
    plan_file = tmp_path / "p.json"
    plan_file.write_text(json.dumps({"payload": {"instance_info": {"x": 1}}}),
                         encoding="utf-8")
    fake = MagicMock()
    fake._post.return_value = "new-uuid-xyz"
    with patch("kuake.server.AutoDLClient", return_value=fake):
        r = client.post("/api/confirm-create",
                        json={"plan_file": str(plan_file), "yes": "YES"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["uuid"] == "new-uuid-xyz"
    fake._post.assert_called_once()


# ── /api/instances ─────────────────────────────────────────────

def test_instances_endpoint(client):
    fake = MagicMock()
    fake.list_instances.return_value = [
        {"uuid": "u1", "machine_alias": "A", "region_name": "R",
         "snapshot_gpu_alias_name": "GPU1", "req_gpu_amount": 1,
         "status": "running", "image": "img"},
    ]
    with patch("kuake.server.AutoDLClient", return_value=fake):
        r = client.get("/api/instances")
    assert r.status_code == 200
    assert r.get_json()["instances"][0]["uuid"] == "u1"


# ── push-start input validation ────────────────────────────────

def test_push_start_requires_task_and_src(client):
    r = client.post("/api/push-start", json={"task": "", "src": ""})
    assert r.status_code == 400


def test_push_start_rejects_missing_src(client, tmp_path):
    r = client.post("/api/push-start",
                    json={"task": "test", "src": str(tmp_path / "ghost")})
    assert r.status_code == 404


# ── / (index) ──────────────────────────────────────────────────

def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"kuake" in r.data
    assert b"\xe6\x8a\xa2\xe5\x8d\xa1" in r.data  # 抢卡 in UTF-8
