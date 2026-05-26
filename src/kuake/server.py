"""Local Flask server powering the kuake web UI.

启动方式: `kuake serve [--port N] [--no-browser]`
默认监听 127.0.0.1:8765, 启动后自动打开浏览器。

路由 (全在 localhost, 不做 auth — 反正本机操作):
  GET  /                              单页 HTML
  GET  /api/market?...                查市场可租机器 (含 CPU/RAM/磁盘/CUDA 详情)
  GET  /api/instances                 查我的实例
  GET  /api/image-presets             公共镜像目录 (Framework → Version → Py → CUDA)
  POST /api/grab-plan {filters}       根据 filter 生成 PLAN 文件
  POST /api/clone-plan {source, ...}  生成 clone PLAN
  POST /api/confirm-create {plan, yes}必须 yes=='YES', 真下单
  POST /api/push-start {task, src, no_unzip?, keep_zip?}  spawn `kuake push`
  POST /api/auto-start {full auto chain params}           spawn `kuake auto`
  POST /api/push-cancel/<job_id>      终止运行中的子进程 (push / auto 都用)
  GET  /api/push-stream/<job_id>      SSE: line/stage/done (stage 含 total)
  GET  /api/jobs                      列最近 N 个 job (从 ~/.kuake/jobs/ 读)
  GET  /api/jobs/<job_id>             单 job 详情 + 完整 log
  POST /api/pick-path {kind}          后端 tkinter 弹文件/目录选择 → 返回绝对路径
  GET  /api/remote/ls                 spawn `kuake ls` 列远端 tasks
  POST /api/remote/rm {task, confirm} spawn `kuake rm <task> -y` (confirm 必须 YES)
"""
from __future__ import annotations

import json
import os
import queue
import re
import secrets
import signal as _signal
import subprocess
import sys
import threading
import time
import uuid as uuidlib
import webbrowser
from datetime import datetime
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
# 进程内 live queue, 用于 SSE 实时推送 (job 跑完后从文件回放)
# queue 内容: ("line", str) | ("stage", int) | None (终止)
_LIVE_QUEUES: dict[str, queue.Queue] = {}
# 进程内 Popen 引用, 给 push-cancel 用
_LIVE_PROCS: dict[str, subprocess.Popen] = {}
# 标记 job 是否被用户主动 cancel, runner 在 wait() 后据此判断是否覆盖状态
_CANCELLED: set[str] = set()

# ── Auth + CSRF (本机 only, 但 --host 0.0.0.0 暴露时这两个就是必需) ────
# 由 serve() 启动时填; None = --no-auth 模式 (不做检查)。
_AUTH_TOKEN: str | None = None
# 期望的 same-origin, 比如 "http://127.0.0.1:8765";由 serve() 设。
_HOST_ORIGIN: str = ""
AUTH_COOKIE_NAME = "kuake_auth"
AUTH_QUERY_NAME = "token"
AUTH_HEADER_NAME = "X-Kuake-Token"

_STAGE_RE = re.compile(r"\[(\d)/(\d)\]")


def _detect_stage(line: str) -> tuple[int, int] | None:
    """从日志行抽取 [N/T] 阶段号 + 总数 (push 是 N/4, auto 是 N/5)。"""
    m = _STAGE_RE.search(line)
    return (int(m.group(1)), int(m.group(2))) if m else None


# ── 镜像目录 (来自 AutoDL Web UI 选择器观察) ─────────────────────
# 真实可用组合,与控制台「立即购买」配置页对齐。
IMAGE_PRESETS = {
    "PyTorch": {
        "versions": {
            "2.8.0": {"py": ["3.12"], "cuda": ["12.8"]},
            "2.7.0": {"py": ["3.12", "3.11"], "cuda": ["12.6", "12.4"]},
            "2.5.1": {"py": ["3.12", "3.11"], "cuda": ["12.4", "12.1"]},
            "2.3.0": {"py": ["3.10"], "cuda": ["12.1"]},
            "2.1.2": {"py": ["3.10"], "cuda": ["12.1", "11.8"]},
        },
        "tpl": "hub.kce.ksyun.com/autodl-image/torch:"
               "cuda{cuda}-cudnn-devel-ubuntu22.04-py{pyshort}-torch{ver}",
    },
    "TensorFlow": {
        "versions": {
            "2.15.0": {"py": ["3.11"], "cuda": ["12.2"]},
            "2.13.0": {"py": ["3.10"], "cuda": ["11.8"]},
        },
        "tpl": "hub.kce.ksyun.com/autodl-image/tensorflow:"
               "cuda{cuda}-cudnn-devel-ubuntu22.04-py{pyshort}-tf{ver}",
    },
    "Miniconda": {
        "versions": {
            "—": {"py": ["3.12", "3.11", "3.10"], "cuda": ["12.4", "12.1", "11.8"]},
        },
        "tpl": "hub.kce.ksyun.com/autodl-image/miniconda3:"
               "py{pyshort}-cuda{cuda}-ubuntu22.04",
    },
    "JAX": {
        "versions": {
            "0.4.30": {"py": ["3.12"], "cuda": ["12.4"]},
        },
        "tpl": "hub.kce.ksyun.com/autodl-image/jax:"
               "cuda{cuda}-cudnn-devel-ubuntu22.04-py{pyshort}-jax{ver}",
    },
    "PaddlePaddle": {
        "versions": {
            "2.6.0": {"py": ["3.10"], "cuda": ["12.0"]},
        },
        "tpl": "hub.kce.ksyun.com/autodl-image/paddle:"
               "cuda{cuda}-cudnn-devel-ubuntu22.04-py{pyshort}-paddle{ver}",
    },
}


def _pyshort(v: str) -> str:
    """3.12 -> 312"""
    return v.replace(".", "")


def render_image_url(framework: str, ver: str, py: str, cuda: str) -> str:
    cfg = IMAGE_PRESETS.get(framework)
    if not cfg:
        return ""
    return cfg["tpl"].format(ver=ver, py=py, pyshort=_pyshort(py), cuda=cuda)


# ── Machine 详细字段抽取 (面向 UI 展示) ──────────────────────────
def _machine_detail(m) -> dict:
    """从 MachineMatch.raw 提取人类可读的硬件 / 系统详情。"""
    raw = m.raw or {}
    base = raw.get("machine_base_info", {}) or {}
    return {
        "cpu_name": base.get("cpu_name", "?"),
        "cpu_num": base.get("cpu_num", 0),
        "cpu_per_gpu": raw.get("cpu_per_gpu", 0),
        "memory_gb": round(base.get("memory", 0) / 1024 ** 3, 1) if base.get("memory") else 0,
        "mem_per_gpu_gb": round(raw.get("mem_per_gpu", 0) / 1024 ** 3, 1) if raw.get("mem_per_gpu") else 0,
        "gpu_memory_gb": round(raw.get("gpu_memory", 0) / 1024 ** 3, 1) if raw.get("gpu_memory") else 0,
        "disk_size_gb": round(base.get("disk_size", 0) / 1024 ** 3, 0) if base.get("disk_size") else 0,
        "data_disk_default_gb": round(raw.get("max_instance_disk_size", 0) / 1024 ** 3, 0)
            if raw.get("max_instance_disk_size") else 50,
        "disk_type": raw.get("disk_type", "?"),
        "cuda_version_max": raw.get("highest_cuda_version", "?"),
        "driver_version": raw.get("driver_version", "?"),
        "os_name": base.get("os_name", "?"),
        "tflops": raw.get("floating_point_hash_rate", ""),
    }


# ── JobStore: 持久化 push job 状态到 ~/.kuake/jobs/ ──────────────
class JobStore:
    """File-based job state for unattended push:
    - <job_id>.json:  metadata {status, started_at, exit_code, ...}
    - <job_id>.log:   原始 stdout, append-only

    Flask 进程死了, 已完成的 job 状态保留;在跑的 job (subprocess) 也会死,
    但 log 文件保留, status 标记为 "interrupted" 由下次启动时扫到。
    """

    def __init__(self, home: Path):
        self.dir = home / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, kind: str, meta: dict) -> str:
        job_id = uuidlib.uuid4().hex[:12]
        now = datetime.now().isoformat(timespec="seconds")
        full = {
            "job_id": job_id, "kind": kind,
            "status": "running", "started_at": now,
            "finished_at": None, "exit_code": None,
            **meta,
        }
        (self.dir / f"{job_id}.json").write_text(json.dumps(full, ensure_ascii=False),
                                                  encoding="utf-8")
        (self.dir / f"{job_id}.log").touch()
        return job_id

    def update(self, job_id: str, **fields) -> None:
        p = self.dir / f"{job_id}.json"
        if not p.exists():
            return
        meta = json.loads(p.read_text(encoding="utf-8"))
        meta.update(fields)
        p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def get(self, job_id: str) -> dict | None:
        p = self.dir / f"{job_id}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def log_path(self, job_id: str) -> Path:
        return self.dir / f"{job_id}.log"

    def read_log(self, job_id: str) -> str:
        p = self.log_path(job_id)
        return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

    def list_recent(self, limit: int = 30) -> list[dict]:
        files = sorted(self.dir.glob("*.json"),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        out = []
        for p in files[:limit]:
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return out

    def sweep_stale(self) -> None:
        """启动时扫一遍, 把 status=running 但 PID 已死的 job 标为 interrupted。"""
        for meta in self.list_recent(limit=100):
            if meta.get("status") != "running":
                continue
            pid = meta.get("pid")
            if pid and not _pid_alive(pid):
                self.update(meta["job_id"], status="interrupted",
                            finished_at=datetime.now().isoformat(timespec="seconds"))

    def prune_old(self, keep_count: int = 100, max_age_days: int = 14) -> int:
        """老 job 文件清理: 同时满足
          - 在最新 keep_count 之外 (按 mtime)
          - 且 mtime > max_age_days 天前
        的 <job_id>.json + <job_id>.log 一起删。

        进行中的 job (status=running) 永远不删 (即使老)。
        返回删除的 job 数。
        """
        files = sorted(self.dir.glob("*.json"),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        if len(files) <= keep_count:
            return 0
        now = time.time()
        threshold = max_age_days * 86400
        deleted = 0
        for p in files[keep_count:]:
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if meta.get("status") == "running":
                continue  # 不动正在跑的
            if now - p.stat().st_mtime < threshold:
                continue  # 还嫩, 不删
            log_path = self.dir / f"{meta.get('job_id', '')}.log"
            try:
                p.unlink()
                if log_path.exists():
                    log_path.unlink()
                deleted += 1
            except OSError:
                pass
        return deleted


def _pid_alive(pid: int) -> bool:
    """跨平台粗略判断 PID 是否还在 (避免引入 psutil 依赖)。"""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFO = 0x1000
            STILL_ACTIVE = 259
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFO, 0, pid)
            if not h:
                return False
            exit_code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(h)
            return bool(ok) and exit_code.value == STILL_ACTIVE
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def _client() -> AutoDLClient:
    jwt = load_jwt_from_storage_state()
    return AutoDLClient(jwt=jwt)


def _extract_token() -> str | None:
    """从 cookie / 自定义 header / 查询字符串里抽 token (优先级 cookie > header > query)。"""
    return (
        request.cookies.get(AUTH_COOKIE_NAME)
        or request.headers.get(AUTH_HEADER_NAME)
        or request.args.get(AUTH_QUERY_NAME)
    )


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(_TEMPLATE_DIR))
    store = JobStore(config_paths().home)
    store.sweep_stale()
    pruned = store.prune_old()
    if pruned:
        print(f"  · 清理了 {pruned} 个 > 14 天的 job 文件")

    @app.before_request
    def _check_auth_and_csrf():
        # 1) auth
        if _AUTH_TOKEN is not None:
            tok = _extract_token()
            if tok != _AUTH_TOKEN:
                if request.path == "/" and request.method == "GET":
                    return (
                        "<h1>401 Unauthorized</h1>"
                        "<p>这个 kuake serve 启用了 token 认证。"
                        "请回到启动 server 的终端,复制带 ?token=XXX 的 URL 打开,"
                        "或 <code>kuake serve --no-auth</code> 关闭 (仅本机使用!)。</p>"
                    ), 401
                return jsonify({
                    "error": "Unauthorized — 缺 token (cookie / X-Kuake-Token / ?token=)",
                }), 401

        # 2) CSRF: 仅对 state-changing 方法检查 Origin (有 → 必须 same-origin;无 → 允许 curl)
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("Origin")
            if origin and _HOST_ORIGIN and origin != _HOST_ORIGIN:
                return jsonify({
                    "error": f"CSRF 拒绝: Origin {origin!r} != 期望 {_HOST_ORIGIN!r}",
                }), 403

    @app.route("/")
    def index():
        resp = send_from_directory(_TEMPLATE_DIR, "index.html")
        # 首次带 ?token=X 访问 → set cookie, 之后浏览器自动带
        if _AUTH_TOKEN and request.args.get(AUTH_QUERY_NAME) == _AUTH_TOKEN:
            if request.cookies.get(AUTH_COOKIE_NAME) != _AUTH_TOKEN:
                resp.set_cookie(
                    AUTH_COOKIE_NAME, _AUTH_TOKEN,
                    httponly=True, samesite="Strict", path="/",
                )
        return resp

    # ── 镜像目录 (静态) ────────────────────────────────────────
    @app.route("/api/image-presets")
    def api_image_presets():
        out = {}
        for fw, cfg in IMAGE_PRESETS.items():
            out[fw] = {ver: {"py": v["py"], "cuda": v["cuda"]}
                       for ver, v in cfg["versions"].items()}
        return jsonify({"frameworks": out})

    # ── 市场 ──────────────────────────────────────────────────
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
            "detail": _machine_detail(m),
        } for m in matches]
        return jsonify({"matches": result})

    # ── 实例列表 ──────────────────────────────────────────────
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

    # ── grab plan ─────────────────────────────────────────────
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

        # 镜像可以直接传 URL,或者传 framework/version/py/cuda 让后端拼
        image = data.get("image") or None
        if not image and data.get("framework"):
            image = render_image_url(
                data["framework"], data.get("ver", ""),
                data.get("py", ""), data.get("cuda", ""),
            ) or None

        plan = plan_from_match(
            chosen,
            gpu_count=int(data.get("gpu_count", 1)),
            image=image,
            expand_data_disk_gb=int(data.get("expand_data_disk_gb", 0)),
            system_disk_change_size_gb=int(data.get("system_disk_change_size_gb", 0)),
        )
        return _save_and_serialize(plan, prefix="plan")

    # ── clone plan ────────────────────────────────────────────
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

    # ── confirm-create (会扣费 !) ─────────────────────────────
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
        return jsonify({"ok": True, "result": result,
                        "uuid": result if isinstance(result, str) else None})

    # ── push job: 启 + 流式日志 + 历史列表 ─────────────────────
    @app.route("/api/push-start", methods=["POST"])
    def api_push_start():
        data = request.get_json() or {}
        task = data.get("task", "").strip()
        src = data.get("src", "").strip()
        no_unzip = bool(data.get("no_unzip", False))
        keep_zip = bool(data.get("keep_zip", False))
        if not task or not src:
            return jsonify({"error": "task + src required"}), 400
        if not Path(src).exists():
            return jsonify({"error": f"src 不存在: {src}"}), 404

        args = [sys.executable, "-m", "kuake", "push", task, src]
        if no_unzip:
            args.append("--no-unzip")
        if keep_zip:
            args.append("--keep-zip")

        job_id = _spawn_job(store, kind="push", meta={
            "task": task, "src": src,
            "no_unzip": no_unzip, "keep_zip": keep_zip,
        }, args=args)
        return jsonify({"job_id": job_id})

    @app.route("/api/auto-start", methods=["POST"])
    def api_auto_start():
        data = request.get_json() or {}
        autopanel_password = (data.get("autopanel_password") or "").strip()
        if not autopanel_password:
            return jsonify({"error": "autopanel_password required"}), 400
        stop_after = data.get("stop_after", "push")
        if stop_after not in ("create", "ready", "init", "push"):
            return jsonify({"error": f"stop_after 必须 create/ready/init/push, got {stop_after!r}"}), 400
        if stop_after == "push":
            if not data.get("task") or not data.get("src"):
                return jsonify({"error": "stop_after=push 时 task + src 必填"}), 400
            if not Path(data["src"]).exists():
                return jsonify({"error": f"src 不存在: {data['src']}"}), 404

        args = [sys.executable, "-m", "kuake", "auto"]
        for g in (data.get("gpu") or []):
            args.extend(["--gpu", g])
        for r in (data.get("region") or []):
            args.extend(["--region", r])
        if data.get("cpu_ok"):
            args.append("--cpu-ok")
        args.extend(["--min-idle", str(data.get("min_idle", 1))])
        args.extend(["--gpu-count", str(data.get("gpu_count", 1))])
        args.extend(["--expand-data-disk", str(data.get("expand_data_disk_gb", 0))])
        args.extend(["--system-disk-expand", str(data.get("system_disk_change_size_gb", 0))])
        if data.get("image"):
            args.extend(["--image", data["image"]])
        args.extend(["--poll", str(data.get("poll", 5))])
        args.extend(["--max-market-iter", str(data.get("max_market_iter", 0))])
        args.extend(["--ready-timeout", str(data.get("ready_timeout", 600))])
        args.extend(["--autopanel-password", autopanel_password])
        if data.get("cloud_dir"):
            args.extend(["--cloud-dir", data["cloud_dir"]])
        if data.get("task"):
            args.extend(["--task", data["task"]])
        if data.get("src"):
            args.extend(["--src", data["src"]])
        if data.get("no_unzip"):
            args.append("--no-unzip")
        if data.get("keep_zip"):
            args.append("--keep-zip")
        args.extend(["--stop-after", stop_after])

        # 密码也用 env 兜底, 子进程的 kuake init 会 fallback 读 env
        extra_env = {"KUAKE_AUTOPANEL_PASSWORD": autopanel_password}

        job_id = _spawn_job(store, kind="auto", meta={
            "task": data.get("task") or "—",
            "src": data.get("src") or "—",
            "gpu": data.get("gpu") or [],
            "stop_after": stop_after,
            "no_unzip": bool(data.get("no_unzip")),
            "keep_zip": bool(data.get("keep_zip")),
            # 密码不进 meta 避免泄露到日志/磁盘
        }, args=args, extra_env=extra_env)
        return jsonify({"job_id": job_id})

    @app.route("/api/push-cancel/<job_id>", methods=["POST"])
    def api_push_cancel(job_id: str):
        proc = _LIVE_PROCS.get(job_id)
        if not proc:
            return jsonify({"error": "未找到运行中进程 (job 可能已结束或属于上次启动遗留)"}), 404
        _CANCELLED.add(job_id)
        store.update(
            job_id,
            status="cancelled",
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        try:
            # Win: CTRL_BREAK_EVENT 让子进程的 Python 收到 KeyboardInterrupt,
            # finally 清理 (SSH 断连, FileLock 释放, 临时 zip 删除) 都能跑。
            # POSIX: SIGTERM 同效果。
            if sys.platform == "win32":
                proc.send_signal(_signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()  # 子进程没在 3s 内退 → 硬杀
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": f"终止失败: {e}"}), 500
        return jsonify({"ok": True})

    @app.route("/api/push-stream/<job_id>")
    def api_push_stream(job_id: str):
        meta = store.get(job_id)
        if not meta:
            return jsonify({"error": "unknown job_id"}), 404

        def gen():
            # 1) 回放已写入的历史 — 顺便扫最大阶段号, 让 UI 直接回到当前进度
            existing = store.read_log(job_id)
            max_stage = 0
            for line in existing.splitlines():
                s = _detect_stage(line)
                if s and s[0] > max_stage:
                    max_stage = s[0]
                    yield (f"event: stage\ndata: "
                           f"{json.dumps({'stage': s[0], 'total': s[1]})}\n\n")
                yield f"data: {json.dumps({'line': line}, ensure_ascii=False)}\n\n"

            # 2) 如果 job 已结束, 直接 done
            cur = store.get(job_id) or {}
            if cur.get("status") != "running":
                yield (
                    f"event: done\ndata: "
                    f"{json.dumps({'exit_code': cur.get('exit_code'), 'status': cur.get('status')})}\n\n"
                )
                return

            # 3) 还在跑 → 订阅 live queue;若进程是上次启动遗留的, queue 不存在 → 轮询文件 tail
            live_q = _LIVE_QUEUES.get(job_id)
            if live_q is not None:
                while True:
                    item = live_q.get()
                    if item is None:
                        cur = store.get(job_id) or {}
                        yield (
                            f"event: done\ndata: "
                            f"{json.dumps({'exit_code': cur.get('exit_code'), 'status': cur.get('status')})}\n\n"
                        )
                        return
                    kind, payload = item
                    if kind == "stage":
                        n, total = payload
                        yield (f"event: stage\ndata: "
                               f"{json.dumps({'stage': n, 'total': total})}\n\n")
                    else:
                        yield f"data: {json.dumps({'line': payload}, ensure_ascii=False)}\n\n"
            else:
                # 文件 tail 模式 (遗留 job 或外部进程写入)
                log_path = store.log_path(job_id)
                pos = len(existing)
                while True:
                    if log_path.exists():
                        with open(log_path, encoding="utf-8", errors="replace") as f:
                            f.seek(pos)
                            chunk = f.read()
                            pos = f.tell()
                        for line in chunk.splitlines():
                            s = _detect_stage(line)
                            if s and s[0] > max_stage:
                                max_stage = s[0]
                                yield (f"event: stage\ndata: "
                                       f"{json.dumps({'stage': s[0], 'total': s[1]})}\n\n")
                            yield f"data: {json.dumps({'line': line}, ensure_ascii=False)}\n\n"
                    cur = store.get(job_id) or {}
                    if cur.get("status") != "running":
                        yield (
                            f"event: done\ndata: "
                            f"{json.dumps({'exit_code': cur.get('exit_code'), 'status': cur.get('status')})}\n\n"
                        )
                        return
                    time.sleep(1.5)

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    @app.route("/api/jobs")
    def api_jobs():
        limit = int(request.args.get("limit", "30"))
        return jsonify({"jobs": store.list_recent(limit=limit)})

    @app.route("/api/jobs/<job_id>")
    def api_job(job_id: str):
        meta = store.get(job_id)
        if not meta:
            return jsonify({"error": "unknown job_id"}), 404
        return jsonify({"meta": meta, "log": store.read_log(job_id)})

    # ── 本机文件 / 目录选择器 (tkinter 子进程) ─────────────────
    @app.route("/api/pick-path", methods=["POST"])
    def api_pick_path():
        data = request.get_json() or {}
        kind = data.get("kind", "folder")
        if kind not in ("folder", "file"):
            return jsonify({"error": "kind must be 'folder' or 'file'"}), 400
        try:
            path = _pick_path_subprocess(kind)
        except FileNotFoundError as e:
            return jsonify({"error": f"tkinter 不可用: {e}"}), 501
        except subprocess.TimeoutExpired:
            return jsonify({"error": "超时 (用户没选)", "path": ""}), 200
        return jsonify({"path": path, "cancelled": not path})

    # ── 远端文件 (kuake ls / rm) ──────────────────────────────
    @app.route("/api/remote/ls")
    def api_remote_ls():
        try:
            result = subprocess.run(
                [sys.executable, "-m", "kuake", "ls"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30,
            )
        except subprocess.TimeoutExpired:
            return jsonify({"error": "kuake ls 超时 (30s)"}), 504
        return jsonify({
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })

    @app.route("/api/remote/rm", methods=["POST"])
    def api_remote_rm():
        data = request.get_json() or {}
        task = (data.get("task") or "").strip()
        confirm = data.get("confirm", "")
        if not task:
            return jsonify({"error": "task required"}), 400
        if confirm != "YES":
            return jsonify({"error": "需要 confirm=='YES' 才能删"}), 403
        try:
            result = subprocess.run(
                [sys.executable, "-m", "kuake", "rm", task, "-y"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60,
            )
        except subprocess.TimeoutExpired:
            return jsonify({"error": "kuake rm 超时 (60s)"}), 504
        return jsonify({
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })

    return app


def _spawn_job(
    store: JobStore,
    *,
    kind: str,
    meta: dict,
    args: list[str],
    extra_env: dict[str, str] | None = None,
) -> str:
    """Common: create job, spawn subprocess, stream stdout → log + queue, update status on exit.

    push 和 auto 共享同一套流程, 仅 args / kind / meta 不同。
    Returns: job_id.
    """
    job_id = store.create(kind, meta)
    log_q: queue.Queue = queue.Queue()
    _LIVE_QUEUES[job_id] = log_q

    def runner() -> None:
        log_path = store.log_path(job_id)
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        # Win: CREATE_NEW_PROCESS_GROUP 让我们后面能 send CTRL_BREAK_EVENT
        # (没有这个 flag, 子进程收不到 ctrl-break, 只能被硬杀)
        popen_kwargs: dict = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env,
            **popen_kwargs,
        )
        _LIVE_PROCS[job_id] = proc
        store.update(job_id, pid=proc.pid)
        with open(log_path, "a", encoding="utf-8") as logf:
            for line in proc.stdout or []:
                logf.write(line)
                logf.flush()
                stripped = line.rstrip("\r\n")
                stage = _detect_stage(stripped)
                if stage is not None:
                    log_q.put(("stage", stage))
                log_q.put(("line", stripped))
        proc.wait()
        _LIVE_PROCS.pop(job_id, None)
        if job_id in _CANCELLED:
            _CANCELLED.discard(job_id)
            store.update(job_id, exit_code=proc.returncode)
        else:
            store.update(
                job_id,
                status="completed" if proc.returncode == 0 else "failed",
                exit_code=proc.returncode,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        log_q.put(None)
        _LIVE_QUEUES.pop(job_id, None)

    threading.Thread(target=runner, daemon=True).start()
    return job_id


def _pick_path_subprocess(kind: str) -> str:
    """Spawn separate Python process to open tkinter dialog.

    在 Flask 同进程开 tk dialog 在 Windows 上易卡死;子进程隔离 + topmost 比较稳。
    Returns picked absolute path, 或 "" (用户取消)。
    """
    code = (
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "import sys\n"
        "root = tk.Tk()\n"
        "root.withdraw()\n"
        "root.attributes('-topmost', True)\n"
        "if sys.argv[1] == 'folder':\n"
        "    p = filedialog.askdirectory(title='kuake: 选目录')\n"
        "else:\n"
        "    p = filedialog.askopenfilename(title='kuake: 选文件')\n"
        "sys.stdout.write(p or '')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, kind],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600,
    )
    return result.stdout.strip()


def _save_and_serialize(plan, *, prefix: str):
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


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    no_auth: bool = False,
) -> None:
    """Boot the dev server. Foreground / blocks until Ctrl+C.

    no_auth: True = 跳过 token 检查 (仅本机 localhost 时可接受)
    """
    global _AUTH_TOKEN, _HOST_ORIGIN
    _AUTH_TOKEN = None if no_auth else secrets.token_urlsafe(24)
    _HOST_ORIGIN = f"http://{host}:{port}"

    app = create_app()
    base_url = f"{_HOST_ORIGIN}/"

    if _AUTH_TOKEN is None:
        url = base_url
        print(f"kuake serve → {url}  (Ctrl+C 退出)")
        if host != "127.0.0.1":
            print(f"⚠ --no-auth + --host {host} = 无认证暴露非本机!"
                  f" 建议改回 127.0.0.1 或去掉 --no-auth")
    else:
        url = f"{base_url}?{AUTH_QUERY_NAME}={_AUTH_TOKEN}"
        print(f"kuake serve → {base_url}  (Ctrl+C 退出)")
        print("🔐 token 认证已启用, 用这个 URL 打开:")
        print(f"   {url}")
        print(f"   (curl 用 -H '{AUTH_HEADER_NAME}: {_AUTH_TOKEN}' 也行)")
        print("   关闭认证: kuake serve --no-auth")

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
