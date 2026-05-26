"""Post-init smoke test (v0.4+): 直接上传一个 1KB 文件到 Quark cloud,
验证 cookie + uploader 链路。不再依赖 PC 客户端「备份」功能。

旧逻辑(等夸克客户端同步本地目录) 已废弃。
"""
from __future__ import annotations

import os
from datetime import datetime

from kuake.progress import info, ok, warn
from kuake.quark_uploader import QuarkUploader, QuarkUploadError


def run_smoke_test(
    cookie: str,
    cloud_backup_path: str,
) -> bool:
    """Upload 1 KB random file to cloud_backup_path,验证整条上传链路。

    成功返回 True;失败 warn 并返回 False (不抛异常,init 不因此失败)。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"kuake_smoke_{stamp}.bin"

    info(f"Smoke test: 直接上传 {name} (1 KB) → {cloud_backup_path}/")
    uploader = QuarkUploader(cookie=cookie)
    try:
        fid = uploader.resolve_or_create_folder(cloud_backup_path)
    except QuarkUploadError as e:
        warn(f"无法解析云端目录: {e}")
        return False

    # 写一个真随机 1KB,避免被秒传跳过验证
    import tempfile
    with tempfile.NamedTemporaryFile(prefix="kuake_smoke_", suffix=".bin",
                                     delete=False) as f:
        f.write(os.urandom(1024))
        tmp_path = f.name

    try:
        result = uploader.upload(tmp_path, parent_folder_id=fid)
        ok(f"Smoke test 通过 (云端可见 fid={result.fid[:12]}... size={result.size})")
        return True
    except QuarkUploadError as e:
        warn(f"Smoke test 失败: {e}")
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
