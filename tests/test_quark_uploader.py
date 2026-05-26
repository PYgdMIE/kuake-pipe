"""Unit tests for quark_uploader. Uses requests_mock to stub all HTTP calls."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import pytest
import requests_mock

from kuake.quark_uploader import (
    QuarkUploader, QuarkUploadError, UploadResult, SINGLE_PART_THRESHOLD, CHUNK_SIZE,
)


# ── 工具 ────────────────────────────────────────────────────────────────

def _ok(data):
    return {"code": 0, "status": 200, "message": "", "data": data}


def _pre_upload_resp(task_id="t1", upload_id="u1", obj_key="key1",
                     bucket="ul-sz-acc"):
    return _ok({
        "task_id": task_id, "upload_id": upload_id, "obj_key": obj_key,
        "bucket": bucket, "auth_info": "AUTHINFO",
        "callback": {"callbackUrl": "x", "callbackBody": "y"},
        "finish": False,
    })


def _hash_update_finish_false():
    return _ok({"finish": False})


def _hash_update_finish_true(fid="fid1", file_name="x.bin"):
    return _ok({"finish": True, "fid": fid, "file_name": file_name})


def _auth_resp(key="OSS K:ABC123"):
    return _ok({"auth_key": key})


def _finish_resp(fid="fid1", file_name="x.bin"):
    return _ok({
        "fid": fid, "file_name": file_name, "task_id": "t1",
        "md5": "0" * 32, "sha1": "0" * 40, "finish": True,
    })


# ── 测试 ────────────────────────────────────────────────────────────────

def test_empty_cookie_raises():
    with pytest.raises(QuarkUploadError):
        QuarkUploader(cookie="")


def test_single_part_upload(tmp_path):
    """< 5MB 文件走单分片路径,1 次 PUT + 1 次 complete。"""
    f = tmp_path / "small.bin"
    f.write_bytes(b"A" * 1024)  # 1 KB

    up = QuarkUploader(cookie="ck=v")
    base = "https://drive-pc.quark.cn/1/clouddrive"
    bucket_host = "https://ul-sz-acc.pds.quark.cn"

    with requests_mock.Mocker() as m:
        m.post(f"{base}/file/upload/pre", json=_pre_upload_resp())
        m.post(f"{base}/file/update/hash", json=_hash_update_finish_false())
        m.post(f"{base}/file/upload/auth", json=_auth_resp())
        m.put(f"{bucket_host}/key1", status_code=200,
              headers={"ETag": '"ABC123"'})
        m.post(f"{bucket_host}/key1", status_code=200, json={"Status": "OK"})
        m.post(f"{base}/file/upload/finish", json=_finish_resp())

        result = up.upload(f, parent_folder_id="parent1")

    assert isinstance(result, UploadResult)
    assert result.fid == "fid1"
    assert result.size == 1024


def test_rapid_upload_skips_oss(tmp_path):
    """秒传命中(hash_update 返回 finish=True)时,不走 PUT/complete,直接返回。"""
    f = tmp_path / "rapid.bin"
    f.write_bytes(b"B" * 256)
    up = QuarkUploader(cookie="ck=v")
    base = "https://drive-pc.quark.cn/1/clouddrive"

    with requests_mock.Mocker() as m:
        m.post(f"{base}/file/upload/pre", json=_pre_upload_resp())
        m.post(f"{base}/file/update/hash",
               json=_hash_update_finish_true(file_name="rapid.bin"))
        # 不挂 PUT / complete mock → 如果走了就会 NoMockAddress

        result = up.upload(f, parent_folder_id="parent1")

    assert result.size == 256
    assert result.file_name == "rapid.bin"


def test_multi_part_upload(tmp_path):
    """>= 5MB 文件走多分片,N 次 PUT + 1 次 complete。"""
    f = tmp_path / "big.bin"
    # 9 MB → CHUNK_SIZE=4MB → 3 个分片 (4+4+1)
    f.write_bytes(b"C" * (CHUNK_SIZE * 2 + 1024 * 1024))
    up = QuarkUploader(cookie="ck=v")
    base = "https://drive-pc.quark.cn/1/clouddrive"
    bucket_host = "https://ul-sz-acc.pds.quark.cn"

    put_count = {"n": 0}

    def _put_cb(req, ctx):
        put_count["n"] += 1
        ctx.status_code = 200
        ctx.headers["ETag"] = f'"PART{put_count["n"]}"'
        return ""

    with requests_mock.Mocker() as m:
        m.post(f"{base}/file/upload/pre", json=_pre_upload_resp())
        m.post(f"{base}/file/update/hash", json=_hash_update_finish_false())
        m.post(f"{base}/file/upload/auth", json=_auth_resp())
        m.put(f"{bucket_host}/key1", text=_put_cb)
        m.post(f"{bucket_host}/key1", status_code=200, json={"Status": "OK"})
        m.post(f"{base}/file/upload/finish", json=_finish_resp())

        result = up.upload(f, parent_folder_id="parent1")

    assert put_count["n"] == 3
    assert result.size == f.stat().st_size


def test_pre_upload_api_failure_raises(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"X")
    up = QuarkUploader(cookie="ck=v")
    base = "https://drive-pc.quark.cn/1/clouddrive"

    with requests_mock.Mocker() as m:
        m.post(f"{base}/file/upload/pre",
               json={"code": 50001, "message": "无权限"})
        with pytest.raises(QuarkUploadError, match="50001"):
            up.upload(f, parent_folder_id="parent1")


def test_oss_put_failure_raises(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"X" * 100)
    up = QuarkUploader(cookie="ck=v")
    base = "https://drive-pc.quark.cn/1/clouddrive"
    bucket_host = "https://ul-sz-acc.pds.quark.cn"

    with requests_mock.Mocker() as m:
        m.post(f"{base}/file/upload/pre", json=_pre_upload_resp())
        m.post(f"{base}/file/update/hash", json=_hash_update_finish_false())
        m.post(f"{base}/file/upload/auth", json=_auth_resp())
        m.put(f"{bucket_host}/key1", status_code=403,
              text="<Error><Code>AccessDenied</Code></Error>")
        with pytest.raises(QuarkUploadError, match="403"):
            up.upload(f, parent_folder_id="parent1")


def test_uses_pds_quark_cn_not_oss_aliyuncs(tmp_path):
    """回归测试:确认 PUT 走 {bucket}.pds.quark.cn,不要回退到 aliyuncs.com。"""
    f = tmp_path / "z.bin"
    f.write_bytes(b"Z" * 1024)
    up = QuarkUploader(cookie="ck=v")
    base = "https://drive-pc.quark.cn/1/clouddrive"

    seen_hosts = []

    def _put_cb(req, ctx):
        seen_hosts.append(req.url)
        ctx.status_code = 200
        ctx.headers["ETag"] = '"X"'
        return ""

    with requests_mock.Mocker() as m:
        m.post(f"{base}/file/upload/pre",
               json=_pre_upload_resp(bucket="ul-zb-acc"))
        m.post(f"{base}/file/update/hash", json=_hash_update_finish_false())
        m.post(f"{base}/file/upload/auth", json=_auth_resp())
        m.put("https://ul-zb-acc.pds.quark.cn/key1", text=_put_cb)
        m.post("https://ul-zb-acc.pds.quark.cn/key1",
               status_code=200, json={"Status": "OK"})
        m.post(f"{base}/file/upload/finish", json=_finish_resp())
        up.upload(f, parent_folder_id="parent1")

    assert seen_hosts, "PUT was not made"
    for url in seen_hosts:
        assert "pds.quark.cn" in url
        assert "aliyuncs.com" not in url


def test_resolve_or_create_folder_finds_existing(tmp_path):
    up = QuarkUploader(cookie="ck=v")
    with requests_mock.Mocker() as m:
        m.get("https://drive-pc.quark.cn/1/clouddrive/file/sort",
              json=_ok({"list": [
                  {"fid": "F1", "file_name": "kuake-uploads", "file_type": 0},
                  {"fid": "F2", "file_name": "other", "file_type": 0},
              ]}))
        fid = up.resolve_or_create_folder("/kuake-uploads")
    assert fid == "F1"


def test_resolve_or_create_folder_creates_missing(tmp_path):
    up = QuarkUploader(cookie="ck=v")
    with requests_mock.Mocker() as m:
        m.get("https://drive-pc.quark.cn/1/clouddrive/file/sort",
              json=_ok({"list": []}))
        m.post("https://drive-pc.quark.cn/1/clouddrive/file",
               json=_ok({"fid": "NEW", "file_name": "new-folder"}))
        fid = up.resolve_or_create_folder("/new-folder")
    assert fid == "NEW"
