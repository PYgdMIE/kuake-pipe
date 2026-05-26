"""Tests for autodl_api.load_jwt_from_storage_state edge cases + AutoDLClient mock."""
from __future__ import annotations
import json

import pytest
import requests_mock

from kuake.autodl_api import (
    AutoDLClient, MachineMatch, load_jwt_from_storage_state,
)
from kuake.errors import NetworkError


# ── JWT loader ─────────────────────────────────────────────────

def test_load_jwt_missing_file_raises(tmp_path):
    with pytest.raises(NetworkError, match="storage_state missing"):
        load_jwt_from_storage_state(tmp_path / "no-such.json")


def test_load_jwt_no_autodl_origin_raises(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"cookies": [], "origins": []}))
    with pytest.raises(NetworkError, match="未在 storage_state"):
        load_jwt_from_storage_state(p)


def test_load_jwt_no_token_in_localstorage_raises(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({
        "cookies": [],
        "origins": [{
            "origin": "https://www.autodl.com",
            "localStorage": [{"name": "other-key", "value": "x"}],
        }],
    }))
    with pytest.raises(NetworkError, match="未在 storage_state"):
        load_jwt_from_storage_state(p)


def test_load_jwt_success(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({
        "cookies": [],
        "origins": [{
            "origin": "https://www.autodl.com",
            "localStorage": [{"name": "token", "value": "ey-jwt-xxx"}],
        }],
    }))
    assert load_jwt_from_storage_state(p) == "ey-jwt-xxx"


def test_load_jwt_ignores_other_origins(tmp_path):
    """token 在多个 origin 都可能存在,只看 autodl.com"""
    p = tmp_path / "state.json"
    p.write_text(json.dumps({
        "cookies": [],
        "origins": [
            {"origin": "https://other.com",
             "localStorage": [{"name": "token", "value": "WRONG"}]},
            {"origin": "https://www.autodl.com",
             "localStorage": [{"name": "token", "value": "CORRECT"}]},
        ],
    }))
    assert load_jwt_from_storage_state(p) == "CORRECT"


# ── AutoDLClient request paths ─────────────────────────────────

BASE = "https://www.autodl.com"


def _ok(data):
    return {"code": "Success", "msg": "", "data": data}


def test_client_attaches_jwt_header_when_provided():
    client = AutoDLClient(jwt="my-jwt")
    assert client.s.headers["Authorization"] == "my-jwt"


def test_client_no_jwt_no_header():
    client = AutoDLClient()
    assert "Authorization" not in client.s.headers


def test_client_post_raises_on_authorize_failed():
    client = AutoDLClient(jwt="bad")
    with requests_mock.Mocker() as m:
        m.post(f"{BASE}/api/v1/instance",
               json={"code": "AuthorizeFailed", "msg": "登录超时"})
        with pytest.raises(NetworkError, match="登录超时"):
            client.list_instances()


def test_client_list_instances_parses_response():
    client = AutoDLClient(jwt="ok")
    with requests_mock.Mocker() as m:
        m.post(f"{BASE}/api/v1/instance",
               json=_ok({"list": [
                   {"uuid": "u1", "status": "running"},
                   {"uuid": "u2", "status": "shutdown"},
               ]}))
        instances = client.list_instances()
    assert len(instances) == 2
    assert instances[0]["uuid"] == "u1"


def test_client_get_instance_returns_none_when_not_found():
    client = AutoDLClient(jwt="ok")
    with requests_mock.Mocker() as m:
        m.post(f"{BASE}/api/v1/instance", json=_ok({"list": []}))
        assert client.get_instance("nonexistent") is None


def test_client_list_available_filters_by_min_idle():
    client = AutoDLClient(jwt="ok")
    with requests_mock.Mocker() as m:
        m.post(f"{BASE}/api/v1/user/machine/list", json=_ok({"list": [
            {"machine_id": "a", "machine_alias": "A", "region_name": "R1",
             "region_sign": "rs1", "gpu_name": "GPU", "gpu_number": 8,
             "gpu_idle_num": 0,  # 0 张空闲 — 应该被过滤掉
             "chip_corp": "nvidia"},
            {"machine_id": "b", "machine_alias": "B", "region_name": "R2",
             "region_sign": "rs2", "gpu_name": "GPU", "gpu_number": 8,
             "gpu_idle_num": 3,
             "chip_corp": "nvidia"},
        ]}))
        matches = client.list_available(min_idle_gpu=2)
    assert len(matches) == 1
    assert matches[0].machine_id == "b"
    assert matches[0].gpu_idle == 3


def test_client_list_available_parses_price():
    client = AutoDLClient(jwt="ok")
    with requests_mock.Mocker() as m:
        m.post(f"{BASE}/api/v1/user/machine/list", json=_ok({"list": [
            {"machine_id": "a", "machine_alias": "A",
             "region_name": "R", "region_sign": "rs",
             "gpu_name": "RTX 5090", "gpu_number": 4, "gpu_idle_num": 2,
             "chip_corp": "nvidia",
             "payg_price": 7500,  # ¥75/h
             "cpu_limit": 16,
             "mem_limit_in_byte": 96 * 1024 ** 3},
        ]}))
        matches = client.list_available()
    assert matches[0].payg_price == 7500
    assert matches[0].cpu_limit == 16


def test_client_wallet_balance():
    client = AutoDLClient(jwt="ok")
    with requests_mock.Mocker() as m:
        m.get(f"{BASE}/api/v1/wallet/balance",
              json=_ok({"assets": 50000, "accumulate": 200000}))
        w = client.wallet_balance()
    assert w["assets"] == 50000


# ── MachineMatch __str__ ────────────────────────────────────────

def test_machine_match_str_with_price():
    m = MachineMatch(
        machine_id="x", machine_alias="A", region_name="R", region_sign="rs",
        gpu_name="GPU", gpu_total=4, gpu_idle=1, chip_corp="nvidia",
        payg_price=2880,
    )
    s = str(m)
    assert "R/A" in s
    assert "GPU (1/4 free)" in s
    assert "¥28.80/h" in s


def test_machine_match_str_zero_price():
    m = MachineMatch(
        machine_id="x", machine_alias="A", region_name="R", region_sign="rs",
        gpu_name="GPU", gpu_total=4, gpu_idle=1, chip_corp="nvidia",
        payg_price=0,
    )
    s = str(m)
    assert "¥0.00/h" in s
