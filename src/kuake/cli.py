"""CLI entry. UTF-8 stdout + i18n error layer + subcommand dispatch."""
from __future__ import annotations

import argparse
import os
import sys

from kuake import __version__, i18n
from kuake.errors import KuakeError
from kuake.platform_guard import ensure_supported
from kuake.progress import console, err, setup_utf8


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kuake",
        description="本地 → 夸克网盘 → AutoDL 服务器全自动数据中转",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"kuake-pipe {__version__}"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="首次配置向导")
    p_init.add_argument("--no-smoke", action="store_true", help="跳过末尾上传验证")
    p_init.add_argument("--ssh-key", action="store_true", help="强制密钥模式 (默认 password)")
    p_init.add_argument("--use-system-chrome", action="store_true",
                        help="复用本机 Chrome profile (Chrome 必须先关闭)")
    # v0.4 自动化 flags: 只剩 AutoDL/Quark 扫码两步真正手动
    p_init.add_argument("--instance", type=int, default=None,
                        help="自动选第 N 号实例 (1-based, 见 `kuake instances`),省去交互选择")
    p_init.add_argument("--autopanel-password", default=None,
                        help="AutoPanel 独立密码 (或设 KUAKE_AUTOPANEL_PASSWORD 环境变量),"
                             "脚本自动填表,无需在浏览器里手输")
    p_init.add_argument("--cloud-dir", default=None,
                        help="云端上传目录,默认 /kuake-uploads")

    p_push = sub.add_parser("push", help="上传 + 触发服务器解压")
    p_push.add_argument("task", help="任务名 (a-zA-Z0-9_-)")
    p_push.add_argument("src", help="本地文件或目录")
    p_push.add_argument("--no-unzip", action="store_true")
    p_push.add_argument("--keep-zip", action="store_true")

    p_retry = sub.add_parser("retry", help="跳过打包,用已有 UPLOAD/<task>.zip")
    p_retry.add_argument("task")

    sub.add_parser("refresh", help="强制刷 panel token/cookie")
    sub.add_parser("doctor", help="全链路自检")
    sub.add_parser("whoami", help="AutoDL 账号信息 + 钱包余额(只读)")
    sub.add_parser("ls", help="列远端 /root/autodl-tmp/")

    p_rm = sub.add_parser("rm", help="删除远端 task 目录")
    p_rm.add_argument("task")
    p_rm.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    p_reset = sub.add_parser("reset", help="清空 ~/.kuake/")
    p_reset.add_argument("--keep-credentials", action="store_true")

    # Instance lifecycle (v1.1)
    sub.add_parser("instances", help="列出 AutoDL 实例及状态")

    p_start = sub.add_parser("start", help="开机 AutoDL 实例")
    p_start.add_argument("target", nargs="?", default="default",
                         help="实例编号(见 `kuake instances`),默认 1")

    p_stop = sub.add_parser("stop", help="关机 AutoDL 实例")
    p_stop.add_argument("target", nargs="?", default="default")
    p_stop.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    p_grab = sub.add_parser(
        "grab",
        help="轮询 AutoDL 市场 → 生成 dry-run PLAN(不下单)",
    )
    p_grab.add_argument("--gpu", action="append", default=[],
                        help="目标 GPU 型号(可多次,如 --gpu 'RTX 5090')")
    p_grab.add_argument("--region", action="append", default=[],
                        help="目标区域 sign(可多次)。不传 = 不限制区")
    p_grab.add_argument("--any-region", action="store_true",
                        help="(显式)不限制区,等同于不传 --region")
    p_grab.add_argument("--cpu-ok", action="store_true", help="也接受 CPU 实例")
    p_grab.add_argument("--min-idle", type=int, default=1,
                        help="市场过滤:至少多少张空闲 GPU 才算匹配")
    p_grab.add_argument("--gpu-count", type=int, default=1,
                        help="创建时申请几张卡(plan 用)")
    p_grab.add_argument("--expand-data-disk", type=int, default=0,
                        help="数据盘扩容 GB (0=不扩,默认 50G 起步)")
    p_grab.add_argument("--system-disk-expand", type=int, default=0,
                        help="系统盘扩容 GB (0=不扩,默认 30G 起步)")
    p_grab.add_argument("--image", default=None,
                        help="自定义镜像 url(留空走 PyTorch/Conda 默认公共镜像)")
    p_grab.add_argument("--poll", type=int, default=5, help="轮询间隔秒")
    p_grab.add_argument("--max-iter", type=int, default=0,
                        help="最多轮询次数,0=无限")

    p_clone = sub.add_parser(
        "clone",
        help="克隆已有实例配置到一台新机器 → 生成 dry-run PLAN(不下单)",
    )
    p_clone.add_argument("source", nargs="?", default=None,
                         help="源实例的 1-based 索引(见 kuake instances)或 uuid 前缀;留空交互选择")
    p_clone.add_argument("--same-region", action="store_true",
                         help="只在源实例同区找空闲机器")
    p_clone.add_argument("--gpu-count", type=int, default=None,
                         help="覆盖 GPU 数量(默认沿用源实例)")
    p_clone.add_argument("--expand-data-disk", type=int, default=None,
                         help="数据盘扩容 GB(覆盖默认)")
    p_clone.add_argument("--system-disk-expand", type=int, default=None,
                         help="系统盘扩容 GB(覆盖默认)")

    p_cc = sub.add_parser(
        "confirm-create",
        help="⚠ 用保存的 PLAN 真下单 (需输 YES 确认, 会扣费)",
    )
    p_cc.add_argument("--plan-file", required=True,
                      help="grab/clone 生成的 plan JSON 路径")

    p_serve = sub.add_parser(
        "serve",
        help="启动本地 Web UI (抢卡 + 上传)",
    )
    p_serve.add_argument("--port", type=int, default=8765,
                         help="监听端口 (默认 8765)")
    p_serve.add_argument("--host", default="127.0.0.1",
                         help="监听地址 (默认 127.0.0.1)")
    p_serve.add_argument("--no-browser", action="store_true",
                         help="不自动开浏览器")

    return parser


def main(argv=None) -> int:
    setup_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        ensure_supported()
    except KuakeError as e:
        err(i18n.t(e.code))
        console.print(f"[yellow]提示:[/yellow] {i18n.t(e.hint_key)}")
        return e.exit_code

    try:
        dispatch(args)
        return 0
    except KuakeError as e:
        from rich.markup import escape
        err(i18n.t(e.code))
        console.print(f"[yellow]提示:[/yellow] {i18n.t(e.hint_key)}")
        if str(e):
            console.print(f"[dim]详情: {escape(str(e))}[/dim]")
        if os.environ.get("KUAKE_DEBUG"):
            import traceback
            traceback.print_exc()
        return e.exit_code
    except KeyboardInterrupt:
        err("已中断")
        return 130
    except Exception as e:
        err(f"未知错误: {e}")
        console.print("[yellow]提示:[/yellow] 运行 KUAKE_DEBUG=1 重试以获取完整 traceback")
        if os.environ.get("KUAKE_DEBUG"):
            import traceback
            traceback.print_exc()
        return 1


def dispatch(args):
    cmd = args.cmd
    if cmd == "init":
        from kuake.commands import init
        autopanel_pw = (args.autopanel_password
                        or os.environ.get("KUAKE_AUTOPANEL_PASSWORD"))
        init.run(no_smoke=args.no_smoke, ssh_key=args.ssh_key,
                 use_system_chrome=args.use_system_chrome,
                 instance_idx=args.instance,
                 autopanel_password=autopanel_pw,
                 cloud_dir=args.cloud_dir)
    elif cmd == "push":
        from kuake.commands import push
        push.run(args.task, args.src, no_unzip=args.no_unzip, keep_zip=args.keep_zip)
    elif cmd == "retry":
        from kuake.commands import retry
        retry.run(args.task)
    elif cmd == "refresh":
        from kuake.commands import refresh
        refresh.run()
    elif cmd == "doctor":
        from kuake.commands import doctor
        doctor.run()
    elif cmd == "whoami":
        from kuake.commands import whoami
        whoami.run()
    elif cmd == "ls":
        from kuake.commands import ls
        ls.run()
    elif cmd == "rm":
        from kuake.commands import rm
        rm.run(args.task, assume_yes=args.yes)
    elif cmd == "reset":
        from kuake.commands import reset
        reset.run(keep_credentials=args.keep_credentials)
    elif cmd == "instances":
        from kuake.commands import instances
        instances.run()
    elif cmd == "start":
        from kuake.commands import start
        start.run(args.target)
    elif cmd == "stop":
        from kuake.commands import stop
        stop.run(args.target, yes=args.yes)
    elif cmd == "grab":
        from kuake.commands import grab
        grab.run(
            gpu_types=args.gpu or None,
            regions=None if args.any_region else (args.region or None),
            cpu_ok=args.cpu_ok,
            min_idle_gpu=args.min_idle,
            gpu_count=args.gpu_count,
            expand_data_disk_gb=args.expand_data_disk,
            system_disk_change_size_gb=args.system_disk_expand,
            image=args.image,
            poll_seconds=args.poll,
            max_iterations=args.max_iter,
        )
    elif cmd == "clone":
        from kuake.commands import clone
        clone.run(
            source=args.source,
            same_region=args.same_region,
            gpu_count=args.gpu_count,
            expand_data_disk_gb=args.expand_data_disk,
            system_disk_change_size_gb=args.system_disk_expand,
        )
    elif cmd == "confirm-create":
        from kuake.commands import confirm_create
        confirm_create.run(plan_file=args.plan_file)
    elif cmd == "serve":
        from kuake import server
        server.serve(host=args.host, port=args.port,
                     open_browser=not args.no_browser)
    else:
        raise ValueError(f"Unknown command: {cmd}")


if __name__ == "__main__":
    sys.exit(main())
