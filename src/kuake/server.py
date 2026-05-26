"""Local Flask server powering the kuake web UI.

启动方式: `kuake serve [--port N] [--no-browser]`
默认监听 127.0.0.1:8765, 启动后自动打开浏览器。

路由 (全在 localhost, 不做 auth — 反正本机操作):
  GET  /                              单页 HTML
  GET  /api/market?...                查市场可租机器 (实时轮询用)
  GET  /api/instances                 查我的实例
  POST /api/grab-plan {filters}       根据 filter 生成 PLAN 文件
  POST /api/clone-plan {source, ...}  生成 clone PLAN
  POST /api/confirm-create {plan, yes}必须 yes=='YES', 真下单
  POST /api/push-start {task, src}    spawn `kuake push` 子进程, 返回 task_id
  GET  /api/push-stream/<task_id>     SSE 推日志行
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import uuid as uuidlib
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from kuake.autodl_api import AutoDLClient, load_jwt_from_storage_state
from kuake.autodl_planner import (
    format_plan,
    plan_clone_from_instance,
    plan_from_match,
    save_plan,
)
from kuake.config import config_paths
from kuake.errors import NetworkError

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_PUSH_JOBS: dict[str, dict] = {}


def _client() -> AutoDLClient:
    jwt = load_jwt_from_storage_state()
    return AutoDLClient(jwt=jwt)


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(_TEMPLATE_DIR))

    @app.route("/")
    def index():
        return send_from_directory(_TEMPLATE_DIR, "index.html")

    @app.route("/api/market")
    def api_market():
        gpu_filter = request.args.getlist("gpu") or None
        region_filter = request.args.getlist("region") or None
        cpu_ok = request.args.get("cpu_ok", "false").lower() == "true"
        min_idle = int(request.args.get("min_idle", "1"))
        try:
            matches = _client().list_available(
                gpu_type_names=gpu_filter,
                region_sign_list=region_filter,
                min_idle_gpu=min_idle,
            )
        except NetworkError as e:
            return jsonify({"error": str(e)}), 502

        if not cpu_ok:
            matches = [m for m in matches if (m.chip_corp or "").lower() != "cpu"]

        result = [{
            "machine_id": m.machine_id,
            "machine_alias": m.machine_alias,
            "region_name": m.region_name,
            "region_sign": m.region_sign,
            "gpu_name": m.gpu_name,
            "gpu_total": m.gpu_total,
            "gpu_idle": m.gpu_idle,
            "chip_corp": m.chip_corp,
            "price_yuan_per_hour": m.payg_price / 1000 if m.payg_price else 0.0,
        } for m in matches]
        return jsonify({"matches": result})

    @app.route("/api/instances")
    def api_instances():
        try:
            instances = _client().list_instances()
        except NetworkError as e:
            return jsonify({"error": str(e)}), 502
        return jsonify({"instances": [{
            "uuid": i.get("uuid", ""),
            "machine_alias": i.get("machine_alias", ""),
            "region_name": i.get("region_name", ""),
            "gpu_name": i.get("snapshot_gpu_alias_name", ""),
            "gpu_count": i.get("req_gpu_amount", 1),
            "status": i.get("status", ""),
            "image": i.get("image", ""),
        } for i in instances]})

    @app.route("/api/grab-plan", methods=["POST"])
    def api_grab_plan():
        data = request.get_json() or {}
        machine_id = data.get("machine_id")
        if not machine_id:
            return jsonify({"error": "machine_id required"}), 400
        try:
            matches = _client().list_available(min_idle_gpu=1, page_size=50)
        except NetworkError as e:
            return jsonify({"error": str(e)}), 502
        chosen = next((m for m in matches if m.machine_id == machine_id), None)
        if chosen is None:
            return jsonify({"error": f"机器 {machine_id} 已不在市场 (可能刚被抢了)"}), 410
        plan = plan_from_match(
            chosen,
            gpu_count=int(data.get("gpu_count", 1)),
            image=data.get("image") or None,
            expand_data_disk_gb=int(data.get("expand_data_disk_gb", 0)),
            system_disk_change_size_gb=int(data.get("system_disk_change_size_gb", 0)),
        )
        return _save_and_serialize(plan, prefix="plan")

    @app.route("/api/clone-plan", methods=["POST"])
    def api_clone_plan():
        data = request.get_json() or {}
        source = data.get("source")
        if not source:
            return jsonify({"error": "source required (uuid or 1-based index)"}), 400
        try:
            instances = _client().list_instances()
        except NetworkError as e:
            return jsonify({"error": str(e)}), 502
        src_inst = None
        if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
            idx = int(source)
            if 1 <= idx <= len(instances):
                src_inst = instances[idx - 1]
        if src_inst is None:
            src_inst = next((i for i in instances if i.get("uuid", "").startswith(str(source))), None)
        if src_inst is None:
            return jsonify({"error": f"找不到 source={source}"}), 404

        source_gpu = src_inst.get("snapshot_gpu_alias_name") or src_inst.get("snapshot_gpu_name") or ""
        try:
            matches = _client().list_available(
                gpu_type_names=[source_gpu] if source_gpu else None,
                min_idle_gpu=src_inst.get("req_gpu_amount", 1),
            )
        except NetworkError as e:
            return jsonify({"error": str(e)}), 502
        if not matches:
            return jsonify({"error": f"市场上当前没有 {source_gpu} 空闲机器"}), 410

        plan = plan_clone_from_instance(
            src_inst, matches[0],
            gpu_count=data.get("gpu_count"),
            expand_data_disk_gb=data.get("expand_data_disk_gb"),
            system_disk_change_size_gb=data.get("system_disk_change_size_gb"),
        )
        return _save_and_serialize(plan, prefix="clone")

    @app.route("/api/confirm-create", methods=["POST"])
    def api_confirm_create():
        data = request.get_json() or {}
        plan_file = data.get("plan_file")
        yes_token = data.get("yes", "")
        if yes_token != "YES":
            return jsonify({"error": "需要 yes=='YES' (大写) 才会真下单"}), 403
        if not plan_file or not Path(plan_file).exists():
            return jsonify({"error": f"plan 文件不存在: {plan_file}"}), 404
        try:
            payload = json.loads(Path(plan_file).read_text(encoding="utf-8")).get("payload")
        except json.JSONDecodeError as e:
            return jsonify({"error": f"plan 解析失败: {e}"}), 400
        if not payload:
            return jsonify({"error": "plan 缺 payload 字段"}), 400
        try:
            result = _client()._post("/api/v1/order/instance/create/payg", payload)
        except NetworkError as e:
            return jsonify({"error": str(e)}), 502
        return jsonify({"ok": True, "result": result, "uuid": result if isinstance(result, str) else None})

    @app.route("/api/push-start", methods=["POST"])
    def api_push_start():
        data = request.get_json() or {}
        task = data.get("task", "").strip()
        src = data.get("src", "").strip()
        if not task or not src:
            return jsonify({"error": "task + src required"}), 400
        if not Path(src).exists():
            return jsonify({"error": f"src 不存在: {src}"}), 404
        job_id = uuidlib.uuid4().hex[:12]
        log_q: queue.Queue = queue.Queue()
        _PUSH_JOBS[job_id] = {"queue": log_q, "done": False, "exit_code": None}

        def runner():
            proc = subprocess.Popen(
                [sys.executable, "-m", "kuake", "push", task, src],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            for line in proc.stdout or []:
                log_q.put(line.rstrip("\r\n"))
            proc.wait()
            _PUSH_JOBS[job_id]["exit_code"] = proc.returncode
            _PUSH_JOBS[job_id]["done"] = True
            log_q.put(None)

        threading.Thread(target=runner, daemon=True).start()
        return jsonify({"job_id": job_id})

    @app.route("/api/push-stream/<job_id>")
    def api_push_stream(job_id):
        job = _PUSH_JOBS.get(job_id)
        if not job:
            return jsonify({"error": "unknown job_id"}), 404

        def gen():
            log_q: queue.Queue = job["queue"]
            while True:
                line = log_q.get()
                if line is None:
                    yield f"event: done\ndata: {{\"exit_code\": {job['exit_code']}}}\n\n"
                    return
                yield f"data: {json.dumps({'line': line}, ensure_ascii=False)}\n\n"

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


def _save_and_serialize(plan, *, prefix: str):
    from datetime import datetime
    plans_dir = config_paths().home / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    plan_path = plans_dir / f"{prefix}_{stamp}.json"
    save_plan(plan, str(plan_path))
    return jsonify({
        "plan_file": str(plan_path),
        "summary": {
            "machine_alias": plan.machine_alias,
            "region_name": plan.region_name,
            "gpu_name": plan.gpu_name,
            "gpu_count": plan.req_gpu_amount,
            "image": plan.image,
            "private_image_uuid": plan.private_image_uuid,
            "expand_data_disk_gb": plan.expand_data_disk,
            "system_disk_change_size_gb": plan.system_disk_change_size,
            "price_yuan_per_hour": plan.payg_price_yuan_per_hour,
            "hour_cost": plan.estimated_hour_cost(),
            "notes": plan.notes,
        },
        "format": format_plan(plan),
        "payload": plan.to_payload(),
    })


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Boot the dev server. Foreground / blocks until Ctrl+C."""
    app = create_app()
    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"kuake serve → {url}  (Ctrl+C 退出)")
    app.run(host=host, port=port, debug=False, use_reloader=False)
