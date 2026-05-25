"""Display layer translations. Errors raise in English; CLI prints from here."""
from __future__ import annotations

MESSAGES_ZH: dict[str, str] = {
    "GENERIC": "未知错误",
    "GENERIC.hint": "运行 `kuake doctor` 自检,或带 KUAKE_DEBUG=1 重试",
    "USER_INPUT": "参数错误",
    "USER_INPUT.hint": "运行 `kuake --help` 查看用法",
    "AUTH_EXPIRED": "AutoPanel token 已过期且自动刷新失败",
    "AUTH_EXPIRED.hint": "运行 `kuake refresh` 重新扫码登录",
    "SESSION_DEAD": "登录态彻底失效或缺保存的密码哈希",
    "SESSION_DEAD.hint": "运行 `kuake init` 重新扫码登录(refresh 已无能为力)",
    "NETWORK": "网络不可达",
    "NETWORK.hint": "检查网络连接;公司网络下设置 HTTPS_PROXY",
    "CHROMIUM_MIRROR_UNREACHABLE": "Playwright Chromium 镜像源全部不可达",
    "CHROMIUM_MIRROR_UNREACHABLE.hint": "手动运行 `python -m playwright install chromium`",
    "SSH_CONNECT_FAILED": "SSH 连接失败",
    "SSH_CONNECT_FAILED.hint": "确认 AutoDL 实例已开机,检查 config.toml 里 host/port",
    "SSH_CMD_FAILED": "远端命令执行失败",
    "SSH_CMD_FAILED.hint": "运行 `kuake doctor` 检查服务器状态",
    "CLOUD_TIMEOUT": "夸克云端同步超时",
    "CLOUD_TIMEOUT.hint": "确认夸克 PC 客户端正在运行,且已开启对该目录的备份",
    "CONCURRENCY_LOCK": "另一个 kuake 进程正在运行",
    "CONCURRENCY_LOCK.hint": "等待其他进程完成,或删除 ~/.kuake/.lock(如确信无进程)",
    "PLATFORM_UNSUPPORTED": "当前平台不支持",
    "PLATFORM_UNSUPPORTED.hint": "kuake-pipe v1 仅支持 Windows 和 macOS(夸克无 Linux 客户端)",
    "SCRAPER_FAILED": "网页内容抓取失败,可能是夸克/AutoDL 页面改版",
    "SCRAPER_FAILED.hint": "请到 https://github.com/pymie/kuake-pipe/issues 提交 issue",
    "CONFIG_MISSING": "未找到配置文件",
    "CONFIG_MISSING.hint": "运行 `kuake init` 完成首次配置",
    "CONFIG_CORRUPT": "配置文件损坏",
    "CONFIG_CORRUPT.hint": "运行 `kuake reset` 清除并重新 `kuake init`",
}


def t(key: str) -> str:
    return MESSAGES_ZH.get(key, key)
