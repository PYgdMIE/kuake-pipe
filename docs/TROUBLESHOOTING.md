# 故障速查

## Playwright Chromium 下载失败

```
✗ Chromium 安装出错: ...
CHROMIUM_MIRROR_UNREACHABLE
```

镜像源全部不可达。手动:

```bash
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright python -m playwright install chromium
```

如还失败,试官方源(走代理):

```bash
HTTPS_PROXY=http://127.0.0.1:7890 python -m playwright install chromium
```

---

## `kuake init` 浏览器登录后没反应

最常见是 selector 失效(夸克或 AutoDL 页面改版)。带 debug 重跑:

```bash
KUAKE_DEBUG=1 kuake init
```

如 traceback 含 `ScraperFailed`,到 [issues](https://github.com/yourorg/kuake-pipe/issues) 报告,附:

- traceback 完整文本
- 夸克或 AutoDL 当前页面截图

临时绕过:手动编辑 `~/.kuake/config.toml` 填好字段即可。

---

## push 卡在「等夸克客户端上行」

工具会等最多 1 小时。如果一直没看到云端可见,常见原因:

| 检查项 | 怎么验证 |
|---|---|
| 夸克 PC 客户端在运行 | 任务栏看图标;或 `tasklist | findstr Quark` (Win) |
| 「备份」功能已开 | 客户端「设置 → 备份」开关 |
| 备份目录正确 | 客户端「备份」里的目标本地目录,应等于 `kuake doctor` 报告的 `local_backup_dir` |
| 网络通畅 | `kuake doctor` 第 4 项「夸克网盘可达」 |

可以手动重传:

```bash
kuake retry <task>
```

---

## SSH 连不上

```bash
kuake doctor
```

如 [7-9/12] 失败:

- 实例可能已关机 → 去 AutoDL 控制台开机
- IP / 端口变了(AutoDL 重新开机后会换) → `kuake init` 重新跑

如果用密钥模式,且密钥文件不见了:

```bash
kuake init --ssh-key      # 重新生成密钥并上传到服务器
```

---

## 服务器磁盘满

```bash
kuake ls            # 看哪些 task 占用多
kuake rm <task>     # 删旧的
```

或直接 SSH 进去清:

```bash
ssh root@<host> "rm -rf /root/autodl-tmp/<task>"
```

---

## storage_state 损坏 / refresh 一直失败

```
SESSION_DEAD: Refresh failed (session may be dead)
```

意味着 headless 刷新无法工作,夸克或 AutoDL 已要求重新扫码。

```bash
kuake init        # 重新登录,会复用其他配置,只刷登录态
```

---

## 想多实例切换

v1 不支持多 profile。临时方案是用 `KUAKE_HOME` 环境变量切根:

```bash
KUAKE_HOME=~/.kuake-prod kuake init
KUAKE_HOME=~/.kuake-prod kuake push ...

KUAKE_HOME=~/.kuake-dev  kuake init
KUAKE_HOME=~/.kuake-dev  kuake push ...
```

---

## 中文路径乱码

Windows 终端默认 GBK。`kuake` 启动时会 `sys.stdout.reconfigure(encoding='utf-8')`,理论上不会乱码。如果仍乱码:

```bash
chcp 65001
$env:PYTHONIOENCODING="utf-8"   # PowerShell
set PYTHONIOENCODING=utf-8       # cmd
```

---

## 完全卸载

```bash
kuake reset       # 清配置(会问 y/N)
pip uninstall kuake-pipe
# 删 ~/.kuake/ (如 reset 没删干净):
# Win:  rd /s /q %USERPROFILE%\.kuake
# Mac/Linux: rm -rf ~/.kuake
```
