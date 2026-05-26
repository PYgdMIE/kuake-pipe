"""Direct upload to Quark Cloud Drive via cookie-authenticated HTTP API.

替代夸克 PC 客户端「备份」功能,使工具无需依赖任何 GUI 客户端,
让 Linux / 无图形环境 / CI 都能跑。

协议(逆向自 pan.quark.cn 网页版,2026-05):
1. POST drive-pc.quark.cn/1/clouddrive/file/upload/pre        → task_id, upload_id, obj_key, bucket, auth_info
2. POST drive-pc.quark.cn/1/clouddrive/file/upload/hash       → 秒传检测 (有则直接跳到 finish)
3. for part in parts:
     POST drive-pc.quark.cn/1/clouddrive/file/upload/auth     → auth_key (OSS-style)
     PUT  {bucket}.pds.quark.cn/{obj_key}?partNumber=N&uploadId=...  → ETag
4. POST drive-pc.quark.cn/1/clouddrive/file/upload/auth       → complete auth_key
5. POST {bucket}.pds.quark.cn/{obj_key}?uploadId=...          → CompleteMultipartUpload XML
6. POST drive-pc.quark.cn/1/clouddrive/file/upload/finish     → Quark 落库
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests

from kuake.errors import KuakeError

CHUNK_SIZE = 4 * 1024 * 1024     # 4 MB
SINGLE_PART_THRESHOLD = 5 * 1024 * 1024  # < 5 MB → single part
MAX_CONCURRENT_PARTS = 4
USER_AGENT_OSS = "aliyun-sdk-js/1.0.0 Chrome 148.0.0.0 on OS X 10.15.7 64-bit"
USER_AGENT_API = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)
API_BASE = "https://drive-pc.quark.cn/1/clouddrive"
API_PARAMS = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}


class QuarkUploadError(KuakeError):
    exit_code = 1
    code = "QUARK_UPLOAD_FAILED"
    title = "Quark 直接上传失败"


@dataclass(frozen=True)
class UploadResult:
    fid: str
    file_name: str
    size: int
    md5: str
    sha1: str


def _oss_date() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _file_hashes(path: Path) -> tuple[str, str, int]:
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    size = 0
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            md5.update(chunk)
            sha1.update(chunk)
            size += len(chunk)
    return md5.hexdigest(), sha1.hexdigest(), size


class QuarkUploader:
    """Cookie-based direct uploader. Stateless across uploads (safe to reuse)."""

    def __init__(self, cookie: str, *, timeout: int = 60, proxies: dict | None = None):
        if not cookie:
            raise QuarkUploadError("Empty Quark cookie")
        self.cookie = cookie
        self.timeout = timeout
        self._s = requests.Session()
        self._s.headers.update({
            "Cookie": cookie,
            "User-Agent": USER_AGENT_API,
            "Origin": "https://pan.quark.cn",
            "Referer": "https://pan.quark.cn/",
        })
        if proxies:
            self._s.proxies.update(proxies)

    # ── API surface ─────────────────────────────────────────────────────

    def upload(
        self,
        local_path: Path,
        parent_folder_id: str,
        *,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> UploadResult:
        """Upload a single file. Returns UploadResult on success.

        on_progress(uploaded_bytes, total_bytes, stage_label) called periodically.
        """
        path = Path(local_path).resolve()
        if not path.is_file():
            raise QuarkUploadError(f"Not a file: {path}")

        md5_hex, sha1_hex, size = _file_hashes(path)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        if on_progress:
            on_progress(0, size, "pre_upload")
        pre = self._pre_upload(path.name, size, parent_folder_id, mime)
        task_id = pre["task_id"]
        bucket = pre["bucket"]
        obj_key = pre["obj_key"]
        upload_id = pre["upload_id"]
        auth_info = pre["auth_info"]
        callback = pre["callback"]

        # 秒传检测:服务端比对 sha1,如果云上已有相同文件则立刻完成
        finish = self._hash_update(task_id, md5_hex, sha1_hex)
        if finish.get("finish"):
            if on_progress:
                on_progress(size, size, "rapid_upload")
            return self._build_result(finish, path.name, size, md5_hex, sha1_hex)

        # 真正上传:单分片 or 多分片
        etags: list[tuple[int, str]] = []
        if size < SINGLE_PART_THRESHOLD:
            etag = self._upload_part(
                path, bucket, obj_key, upload_id, auth_info, task_id, mime,
                part_number=1, part_offset=0, part_size=size,
                on_progress=on_progress, uploaded_so_far=0, total_size=size,
            )
            etags.append((1, etag))
        else:
            etags = self._upload_parts_parallel(
                path, bucket, obj_key, upload_id, auth_info, task_id, mime,
                total_size=size, on_progress=on_progress,
            )

        # 提交合并
        if on_progress:
            on_progress(size, size, "complete_multipart")
        self._complete_multipart(
            bucket, obj_key, upload_id, auth_info, task_id, etags, callback,
        )

        # 通知 Quark 落库
        finish = self._finish(task_id, obj_key)
        return self._build_result(finish, path.name, size, md5_hex, sha1_hex)

    # ── Quark API calls ──────────────────────────────────────────────────

    def _api_post(self, path: str, body: dict) -> dict:
        url = f"{API_BASE}/{path}"
        r = self._s.post(url, params=API_PARAMS, json=body, timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != 0:
            raise QuarkUploadError(
                f"Quark API {path} failed: code={j.get('code')} msg={j.get('message')}"
            )
        return j.get("data") or {}

    def _pre_upload(self, file_name: str, size: int, pdir_fid: str, mime: str) -> dict:
        now_ms = int(time.time() * 1000)
        # parallel_upload=True 要求每个分片 PUT 带 x-oss-hash-ctx 增量 SHA1 状态.
        # 目前用 False (顺序多分片) 简化,速度仍可观 (单连接 + 4MB 分片);
        # 后续加 hash_ctx 支持后可开 True 真并发.
        return self._api_post("file/upload/pre", {
            "ccp_hash_update": True,
            "parallel_upload": False,
            "pdir_fid": pdir_fid,
            "dir_name": "",
            "size": size,
            "file_name": file_name,
            "format_type": mime,
            "l_updated_at": now_ms,
            "l_created_at": now_ms,
        })

    def _hash_update(self, task_id: str, md5_hex: str, sha1_hex: str) -> dict:
        return self._api_post("file/update/hash", {
            "task_id": task_id, "md5": md5_hex, "sha1": sha1_hex,
        })

    def _get_oss_auth(self, task_id: str, auth_info: str, auth_meta: str) -> str:
        data = self._api_post("file/upload/auth", {
            "task_id": task_id, "auth_info": auth_info, "auth_meta": auth_meta,
        })
        key = data.get("auth_key")
        if not key:
            raise QuarkUploadError(f"upload/auth missing auth_key: {data}")
        return key

    def _finish(self, task_id: str, obj_key: str) -> dict:
        return self._api_post("file/upload/finish", {
            "obj_key": obj_key, "task_id": task_id,
        })

    # ── OSS-layer calls (host = {bucket}.pds.quark.cn) ──────────────────

    def _upload_part(
        self,
        path: Path, bucket: str, obj_key: str, upload_id: str, auth_info: str,
        task_id: str, mime: str, part_number: int, part_offset: int, part_size: int,
        on_progress: Callable[[int, int, str], None] | None,
        uploaded_so_far: int, total_size: int,
    ) -> str:
        date = _oss_date()
        canonical = (
            f"PUT\n\n{mime}\n{date}\n"
            f"x-oss-date:{date}\n"
            f"x-oss-user-agent:{USER_AGENT_OSS}\n"
            f"/{bucket}/{obj_key}?partNumber={part_number}&uploadId={upload_id}"
        )
        auth_key = self._get_oss_auth(task_id, auth_info, canonical)

        url = f"https://{bucket}.pds.quark.cn/{obj_key}"
        params: dict[str, str] = {
            "partNumber": str(part_number), "uploadId": upload_id,
        }
        headers = {
            "Authorization": auth_key,
            "x-oss-date": date,
            "x-oss-user-agent": USER_AGENT_OSS,
            "Content-Type": mime,
        }
        with open(path, "rb") as f:
            f.seek(part_offset)
            data = f.read(part_size)

        r = requests.put(url, params=params, data=data, headers=headers,
                         timeout=self.timeout)
        if r.status_code != 200:
            raise QuarkUploadError(
                f"OSS PUT part {part_number} failed: {r.status_code} {r.text[:300]}"
            )
        etag = r.headers.get("ETag", "").strip('"')
        if not etag:
            raise QuarkUploadError(f"OSS PUT part {part_number} returned no ETag")

        if on_progress:
            on_progress(uploaded_so_far + part_size, total_size,
                        f"part_{part_number}")
        return etag

    def _upload_parts_parallel(
        self,
        path: Path, bucket: str, obj_key: str, upload_id: str, auth_info: str,
        task_id: str, mime: str, total_size: int,
        on_progress: Callable[[int, int, str], None] | None,
    ) -> list[tuple[int, str]]:
        # 切分
        parts = []
        offset = 0
        part_number = 1
        while offset < total_size:
            sz = min(CHUNK_SIZE, total_size - offset)
            parts.append((part_number, offset, sz))
            offset += sz
            part_number += 1

        # 顺序 PUT (parallel_upload=False, 服务端不允许真并发不带 hash_ctx)
        results: list[tuple[int, str]] = []
        bytes_done = 0
        for pn, off, sz in parts:
            etag = self._upload_part(
                path, bucket, obj_key, upload_id, auth_info, task_id, mime,
                pn, off, sz, None, 0, total_size,
            )
            results.append((pn, etag))
            bytes_done += sz
            if on_progress:
                on_progress(bytes_done, total_size, f"parts({len(results)}/{len(parts)})")
        return results

    def _complete_multipart(
        self,
        bucket: str, obj_key: str, upload_id: str, auth_info: str,
        task_id: str, etags: list[tuple[int, str]], callback: dict,
    ) -> None:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n<CompleteMultipartUpload>\n'
            + "".join(
                f"<Part>\n<PartNumber>{pn}</PartNumber>\n<ETag>\"{etag}\"</ETag>\n</Part>\n"
                for pn, etag in etags
            )
            + "</CompleteMultipartUpload>"
        )
        xml_bytes = xml.encode("utf-8")
        xml_md5 = base64.b64encode(hashlib.md5(xml_bytes).digest()).decode()
        callback_b64 = base64.b64encode(
            json.dumps(callback, separators=(",", ":")).encode("utf-8")
        ).decode()
        date = _oss_date()
        canonical = (
            f"POST\n{xml_md5}\napplication/xml\n{date}\n"
            f"x-oss-callback:{callback_b64}\n"
            f"x-oss-date:{date}\n"
            f"x-oss-user-agent:{USER_AGENT_OSS}\n"
            f"/{bucket}/{obj_key}?uploadId={upload_id}"
        )
        auth_key = self._get_oss_auth(task_id, auth_info, canonical)

        url = f"https://{bucket}.pds.quark.cn/{obj_key}"
        headers = {
            "Authorization": auth_key,
            "Content-MD5": xml_md5,
            "x-oss-callback": callback_b64,
            "x-oss-date": date,
            "x-oss-user-agent": USER_AGENT_OSS,
            "Content-Type": "application/xml",
        }
        r = requests.post(url, params={"uploadId": upload_id},
                          data=xml_bytes, headers=headers, timeout=self.timeout)
        # 200=OK,203=OK 但 callback 失败(数据已传完,仍算成功)
        if r.status_code not in (200, 203):
            raise QuarkUploadError(
                f"OSS complete_multipart failed: {r.status_code} {r.text[:300]}"
            )

    @staticmethod
    def _build_result(finish: dict, file_name: str, size: int,
                      md5_hex: str, sha1_hex: str) -> UploadResult:
        return UploadResult(
            fid=finish.get("fid", ""),
            file_name=finish.get("file_name", file_name),
            size=size,
            md5=finish.get("md5") or md5_hex,
            sha1=finish.get("sha1") or sha1_hex,
        )

    # ── Helpers for find/create folder by path (no PC client needed) ────

    def resolve_or_create_folder(self, cloud_path: str) -> str:
        """Return file_id of cloud_path (e.g. '/kuake-uploads/'). Creates missing dirs."""
        parts = [p for p in cloud_path.strip("/").split("/") if p]
        parent = "0"  # 根目录
        for name in parts:
            child = self._find_child(parent, name)
            if child is None:
                child = self._create_folder(parent, name)
            parent = child
        return parent

    def _find_child(self, parent_fid: str, name: str) -> str | None:
        # 简化版列表查找。大目录场景应分页,此处足够。
        url = f"{API_BASE}/file/sort"
        params: dict[str, str] = {
            **API_PARAMS,
            "pdir_fid": parent_fid,
            "_size": "200",
            "_page": "1",
            "_sort": "file_type:asc,updated_at:desc",
        }
        r = self._s.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != 0:
            raise QuarkUploadError(f"file/sort failed: {j}")
        items = j.get("data", {}).get("list") or []
        for it in items:
            if it.get("file_name") == name and it.get("file_type") == 0:
                return it.get("fid")
        return None

    def _create_folder(self, parent_fid: str, name: str) -> str:
        data = self._api_post("file", {
            "pdir_fid": parent_fid, "file_name": name, "dir_path": "",
            "dir_init_lock": False,
        })
        fid = data.get("fid")
        if not fid:
            raise QuarkUploadError(f"create folder failed: {data}")
        return fid
