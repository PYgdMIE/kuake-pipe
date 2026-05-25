"""CLI entry. UTF-8 stdout + i18n error layer + subcommand dispatch."""
from __future__ import annotations
import argparse
import os
import sys

from kuake import __version__, i18n
from kuake.errors import KuakeError
from kuake.platform_guard import ensure_supported
from kuake.progress import setup_utf8, err, console


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
    p_init.add_argument("--ssh-key", action="store_true", help="强制密钥模式")
    p_init.add_argument("--use-system-chrome", action="store_true",
                        help="复用本机 Chrome profile (Chrome 必须先关闭)")

    p_push = sub.add_parser("push", help="上传 + 触发服务器解压")
    p_push.add_argument("task", help="任务名 (a-zA-Z0-9_-)")
    p_push.add_argument("src", help="本地文件或目录")
    p_push.add_argument("--no-unzip", action="store_true")
    p_push.add_argument("--keep-zip", action="store_true")

    p_retry = sub.add_parser("retry", help="跳过打包,用已有 UPLOAD/<task>.zip")
    p_retry.add_argument("task")

    sub.add_parser("refresh", help="强制刷 panel token/cookie")
    sub.add_parser("doctor", help="全链路自检")
    sub.add_parser("ls", help="列远端 /root/autodl-tmp/")

    p_rm = sub.add_parser("rm", help="删除远端 task 目录")
    p_rm.add_argument("task")

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

    p_grab = sub.add_parser("grab", help="轮询 AutoDL 市场,抢空闲机器")
    p_grab.add_argument("--gpu", action="append", default=[],
                        help="目标 GPU 型号(可多次,如 --gpu 'RTX 5090' --gpu 'RTX 4090')")
    p_grab.add_argument("--region", action="append", default=[],
                        help="目标区域 sign(可多次,如 --region west-B)")
    p_grab.add_argument("--cpu-ok", action="store_true",
                        help="也接受 CPU 实例")
    p_grab.add_argument("--min-idle", type=int, default=1,
                        help="至少多少张空闲 GPU 才算匹配(默认 1)")
    p_grab.add_argument("--poll", type=int, default=5,
                        help="轮询间隔秒(默认 5)")
    p_grab.add_argument("--max-iter", type=int, default=0,
                        help="最多轮询次数,0=无限(默认)")

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
            import traceback; traceback.print_exc()
        return e.exit_code
    except KeyboardInterrupt:
        err("已中断")
        return 130
    except Exception as e:
        err(f"未知错误: {e}")
        console.print("[yellow]提示:[/yellow] 运行 KUAKE_DEBUG=1 重试以获取完整 traceback")
        if os.environ.get("KUAKE_DEBUG"):
            import traceback; traceback.print_exc()
        return 1


def dispatch(args):
    cmd = args.cmd
    if cmd == "init":
        from kuake.commands import init
        init.run(no_smoke=args.no_smoke, ssh_key=args.ssh_key,
                 use_system_chrome=args.use_system_chrome)
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
    elif cmd == "ls":
        from kuake.commands import ls
        ls.run()
    elif cmd == "rm":
        from kuake.commands import rm
        rm.run(args.task)
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
            regions=args.region or None,
            cpu_ok=args.cpu_ok,
            min_idle_gpu=args.min_idle,
            poll_seconds=args.poll,
            max_iterations=args.max_iter,
            dry_run=True,
        )
    else:
        raise ValueError(f"Unknown command: {cmd}")


if __name__ == "__main__":
    sys.exit(main())
