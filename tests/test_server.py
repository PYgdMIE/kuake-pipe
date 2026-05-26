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


def _match(machine_id="m1", price=10000, gpu="RTX 4090", raw=None):
    return MachineMatch(
        machine_id=machine_id, machine_alias="A1",
        region_name="北京A", region_sign="north-A",
        gpu_name=gpu, gpu_total=8, gpu_idle=2,
        chip_corp="nvidia", payg_price=price,
        cpu_limit=12, mem_limit_in_byte=96 * 1024 ** 3,
        raw=raw or {
            "cpu_per_gpu": 12,
            "mem_per_gpu": 16 * 1024 ** 3,
            "gpu_memory": 24 * 1024 ** 3,
            "max_instance_disk_size": 50 * 1024 ** 3,
            "disk_type": "SSD",
            "highest_cuda_version": "12.8",
            "driver_version": "535.104",
            "machine_base_info": {
                "cpu_num": 96, "cpu_name": "Intel Xeon E5-2680",
                "memory": 128 * 1024 ** 3, "disk_size": 4000 * 1024 ** 3,
                "os_name": "ubuntu22.04",
            },
        },
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


# ── /api/market 详情字段 ─────────────────────────────────────

def test_market_includes_machine_detail(client):
    fake = MagicMock()
    fake.list_available.return_value = [_match()]
    with patch("kuake.server.AutoDLClient", return_value=fake):
        r = client.get("/api/market")
    data = r.get_json()
    d = data["matches"][0]["detail"]
    assert d["cpu_per_gpu"] == 12
    assert d["mem_per_gpu_gb"] == 16.0
    assert d["gpu_memory_gb"] == 24.0
    assert d["cuda_version_max"] == "12.8"
    assert d["driver_version"] == "535.104"
    assert d["os_name"] == "ubuntu22.04"


# ── /api/image-presets ────────────────────────────────────────

def test_image_presets_returns_frameworks(client):
    r = client.get("/api/image-presets")
    data = r.get_json()
    assert "PyTorch" in data["frameworks"]
    pt = data["frameworks"]["PyTorch"]
    assert "2.8.0" in pt
    assert "3.12" in pt["2.8.0"]["py"]
    assert "12.8" in pt["2.8.0"]["cuda"]


# ── grab-plan with framework/ver/py/cuda ──────────────────────

def test_grab_plan_renders_image_from_framework(client, kuake_home):
    fake = MagicMock()
    fake.list_available.return_value = [_match(machine_id="abc")]
    with patch("kuake.server.AutoDLClient", return_value=fake):
        r = client.post("/api/grab-plan", json={
            "machine_id": "abc",
            "framework": "PyTorch", "ver": "2.8.0",
            "py": "3.12", "cuda": "12.8",
        })
    data = r.get_json()
    img = data["summary"]["image"]
    assert "cuda12.8" in img
    assert "py312" in img
    assert "torch2.8.0" in img


# ── jobs ──────────────────────────────────────────────────────

def test_jobs_endpoint_empty(client, kuake_home):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.get_json()["jobs"] == []


def test_job_persistence(client, kuake_home):
    from kuake.server import JobStore
    store = JobStore(kuake_home)
    jid = store.create("push", {"task": "t1", "src": "/data"})
    assert (kuake_home / "jobs" / f"{jid}.json").exists()
    meta = store.get(jid)
    assert meta["task"] == "t1"
    assert meta["status"] == "running"

    store.update(jid, status="completed", exit_code=0)
    meta = store.get(jid)
    assert meta["status"] == "completed"
    assert meta["exit_code"] == 0

    r = client.get("/api/jobs")
    jobs = r.get_json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == jid


def test_job_single_endpoint(client, kuake_home):
    from kuake.server import JobStore
    store = JobStore(kuake_home)
    jid = store.create("push", {"task": "t1", "src": "/data"})
    store.log_path(jid).write_text("line 1\nline 2\n", encoding="utf-8")
    r = client.get(f"/api/jobs/{jid}")
    data = r.get_json()
    assert data["meta"]["job_id"] == jid
    assert "line 1" in data["log"]


def test_job_single_unknown_returns_404(client):
    r = client.get("/api/jobs/nonexistent")
    assert r.status_code == 404


# ── render_image_url ─────────────────────────────────────────

def test_render_image_url_pytorch():
    from kuake.server import render_image_url
    url = render_image_url("PyTorch", "2.8.0", "3.12", "12.8")
    assert "cuda12.8" in url
    assert "py312" in url
    assert "torch2.8.0" in url


def test_render_image_url_unknown_framework():
    from kuake.server import render_image_url
    assert render_image_url("Caffe", "1.0", "3.10", "11.0") == ""


# ── auth + CSRF ───────────────────────────────────────────────

@pytest.fixture
def app_with_auth(kuake_home):
    """像 serve() 一样设 _AUTH_TOKEN + _HOST_ORIGIN, 测完恢复。"""
    from kuake import server
    old_token = server._AUTH_TOKEN
    old_origin = server._HOST_ORIGIN
    server._AUTH_TOKEN = "secret-test-token-abc"
    server._HOST_ORIGIN = "http://127.0.0.1:8765"
    a = server.create_app()
    a.config["TESTING"] = True
    try:
        yield a
    finally:
        server._AUTH_TOKEN = old_token
        server._HOST_ORIGIN = old_origin


@pytest.fixture
def client_with_auth(app_with_auth):
    return app_with_auth.test_client()


def test_auth_missing_token_returns_401(client_with_auth):
    r = client_with_auth.get("/api/jobs")
    assert r.status_code == 401
    assert "Unauthorized" in r.get_json()["error"]


def test_auth_wrong_token_returns_401(client_with_auth):
    r = client_with_auth.get("/api/jobs?token=wrong")
    assert r.status_code == 401


def test_auth_query_token_accepted(client_with_auth):
    r = client_with_auth.get("/api/jobs?token=secret-test-token-abc")
    assert r.status_code == 200


def test_auth_header_token_accepted(client_with_auth):
    r = client_with_auth.get(
        "/api/jobs", headers={"X-Kuake-Token": "secret-test-token-abc"})
    assert r.status_code == 200


def test_auth_cookie_token_accepted(client_with_auth):
    client_with_auth.set_cookie("kuake_auth", "secret-test-token-abc")
    r = client_with_auth.get("/api/jobs")
    assert r.status_code == 200


def test_index_with_token_sets_cookie(client_with_auth):
    r = client_with_auth.get("/?token=secret-test-token-abc")
    assert r.status_code == 200
    # cookie 应该被 set
    set_cookie = r.headers.get("Set-Cookie", "")
    assert "kuake_auth=secret-test-token-abc" in set_cookie
    assert "HttpOnly" in set_cookie


def test_index_without_token_serves_401_html(client_with_auth):
    r = client_with_auth.get("/")
    assert r.status_code == 401
    assert b"Unauthorized" in r.data


def test_csrf_cross_origin_post_rejected(client_with_auth):
    r = client_with_auth.post(
        "/api/pick-path",
        headers={
            "X-Kuake-Token": "secret-test-token-abc",
            "Origin": "https://evil.example.com",
        },
        json={"kind": "folder"},
    )
    assert r.status_code == 403
    assert "CSRF" in r.get_json()["error"]


def test_csrf_same_origin_post_passes(client_with_auth):
    with patch("kuake.server._pick_path_subprocess", return_value="/tmp/x"):
        r = client_with_auth.post(
            "/api/pick-path",
            headers={
                "X-Kuake-Token": "secret-test-token-abc",
                "Origin": "http://127.0.0.1:8765",
            },
            json={"kind": "folder"},
        )
    assert r.status_code == 200


def test_csrf_no_origin_post_passes(client_with_auth):
    """curl 不发 Origin -> 允许 (是用户主动操作)。"""
    with patch("kuake.server._pick_path_subprocess", return_value="/tmp/x"):
        r = client_with_auth.post(
            "/api/pick-path",
            headers={"X-Kuake-Token": "secret-test-token-abc"},
            json={"kind": "folder"},
        )
    assert r.status_code == 200


def test_csrf_get_unaffected(client_with_auth):
    """GET 不查 Origin (无副作用方法)。"""
    r = client_with_auth.get(
        "/api/jobs",
        headers={
            "X-Kuake-Token": "secret-test-token-abc",
            "Origin": "https://evil.example.com",
        },
    )
    assert r.status_code == 200


# ── stage detection ───────────────────────────────────────────

def test_detect_stage_matches_push_bracket_n_of_4():
    from kuake.server import _detect_stage
    assert _detect_stage("· [1/4] 打包 /data -> data.zip") == (1, 4)
    assert _detect_stage("· [2/4] 上传到夸克网盘") == (2, 4)
    assert _detect_stage("· [3/4] 触发 AutoPanel 下载") == (3, 4)
    assert _detect_stage("· [4/4] 服务器解压") == (4, 4)


def test_detect_stage_matches_auto_bracket_n_of_5():
    from kuake.server import _detect_stage
    assert _detect_stage("· [1/5] 轮询市场") == (1, 5)
    assert _detect_stage("· [5/5] kuake push") == (5, 5)


def test_detect_stage_none_for_unrelated_lines():
    from kuake.server import _detect_stage
    assert _detect_stage("✓ 完成") is None
    assert _detect_stage("md5=abc123") is None
    assert _detect_stage("") is None


# ── /api/pick-path ────────────────────────────────────────────

def test_pick_path_validates_kind(client):
    r = client.post("/api/pick-path", json={"kind": "invalid"})
    assert r.status_code == 400


def test_pick_path_returns_picked(client):
    with patch("kuake.server._pick_path_subprocess", return_value="C:/data/foo"):
        r = client.post("/api/pick-path", json={"kind": "folder"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["path"] == "C:/data/foo"
    assert data["cancelled"] is False


def test_pick_path_cancelled_returns_empty(client):
    with patch("kuake.server._pick_path_subprocess", return_value=""):
        r = client.post("/api/pick-path", json={"kind": "folder"})
    data = r.get_json()
    assert data["path"] == ""
    assert data["cancelled"] is True


# ── /api/push-cancel ──────────────────────────────────────────

def test_push_cancel_unknown_job_returns_404(client):
    r = client.post("/api/push-cancel/nonexistent")
    assert r.status_code == 404


def test_push_cancel_terminates_process(client, kuake_home):
    import sys as _sys

    from kuake import server
    from kuake.server import JobStore
    store = JobStore(kuake_home)
    jid = store.create("push", {"task": "t", "src": "/x"})

    fake_proc = MagicMock()
    fake_proc.wait.return_value = None
    server._LIVE_PROCS[jid] = fake_proc
    try:
        r = client.post(f"/api/push-cancel/{jid}")
        assert r.status_code == 200
        if _sys.platform == "win32":
            # Win: 用 CTRL_BREAK_EVENT (让子进程有机会清理)
            fake_proc.send_signal.assert_called_once()
        else:
            fake_proc.terminate.assert_called_once()
        assert store.get(jid)["status"] == "cancelled"
        assert jid in server._CANCELLED
    finally:
        server._LIVE_PROCS.pop(jid, None)
        server._CANCELLED.discard(jid)


# ── /api/remote/ls + /api/remote/rm ───────────────────────────

def test_remote_ls_returns_subprocess_output(client):
    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = "task1/\ntask2.zip\n"
    fake_result.stderr = ""
    with patch("kuake.server.subprocess.run", return_value=fake_result):
        r = client.get("/api/remote/ls")
    data = r.get_json()
    assert data["ok"] is True
    assert "task1" in data["stdout"]


def test_remote_rm_requires_yes_confirm(client):
    r = client.post("/api/remote/rm", json={"task": "t1", "confirm": "no"})
    assert r.status_code == 403


def test_remote_rm_with_yes_spawns_subprocess(client):
    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = "deleted"
    fake_result.stderr = ""
    with patch("kuake.server.subprocess.run", return_value=fake_result) as mock_run:
        r = client.post("/api/remote/rm",
                        json={"task": "t1", "confirm": "YES"})
    assert r.status_code == 200
    args = mock_run.call_args[0][0]
    assert "rm" in args
    assert "t1" in args


def test_remote_rm_missing_task_returns_400(client):
    r = client.post("/api/remote/rm", json={"confirm": "YES"})
    assert r.status_code == 400


# ── /api/auto-start ───────────────────────────────────────────

def test_auto_start_requires_autopanel_password(client):
    r = client.post("/api/auto-start", json={"task": "t", "src": "/"})
    assert r.status_code == 400
    assert "autopanel_password" in r.get_json()["error"]


def test_auto_start_validates_stop_after(client):
    r = client.post("/api/auto-start",
                    json={"autopanel_password": "x", "stop_after": "bogus"})
    assert r.status_code == 400


def test_auto_start_push_needs_task_and_src(client):
    r = client.post("/api/auto-start",
                    json={"autopanel_password": "x", "stop_after": "push"})
    assert r.status_code == 400
    assert "task" in r.get_json()["error"]


def test_auto_start_with_create_stop_after_returns_job_id(client, tmp_path):
    """stop_after=create 不需要 task/src, 验证 spawn 成功。"""
    fake_popen = MagicMock()
    fake_popen.pid = 999
    fake_popen.stdout = iter([])
    fake_popen.returncode = 0
    with patch("kuake.server.subprocess.Popen", return_value=fake_popen) as mock_popen:
        r = client.post("/api/auto-start",
                        json={"autopanel_password": "secret",
                              "stop_after": "create",
                              "gpu": ["RTX 3080 Ti"],
                              "min_idle": 1, "gpu_count": 1,
                              "expand_data_disk_gb": 50})
    assert r.status_code == 200
    assert "job_id" in r.get_json()
    import time
    time.sleep(0.1)
    args = mock_popen.call_args[0][0]
    assert "auto" in args
    assert "--gpu" in args and "RTX 3080 Ti" in args
    assert "--stop-after" in args and "create" in args
    assert "--expand-data-disk" in args and "50" in args
    # 密码通过 args + env 都给
    assert "--autopanel-password" in args
    env = mock_popen.call_args.kwargs.get("env", {})
    assert env.get("KUAKE_AUTOPANEL_PASSWORD") == "secret"


# ── push-start with flags ─────────────────────────────────────

def test_push_start_passes_no_unzip_and_keep_zip(client, tmp_path):
    src = tmp_path / "data"
    src.mkdir()
    fake_popen = MagicMock()
    fake_popen.pid = 12345
    fake_popen.stdout = iter([])
    fake_popen.returncode = 0
    with patch("kuake.server.subprocess.Popen", return_value=fake_popen) as mock_popen:
        r = client.post("/api/push-start",
                        json={"task": "t1", "src": str(src),
                              "no_unzip": True, "keep_zip": True})
    assert r.status_code == 200
    # 让 runner 线程跑完 (Popen mock 立即返回)
    import time
    time.sleep(0.1)
    args = mock_popen.call_args[0][0]
    assert "--no-unzip" in args
    assert "--keep-zip" in args
