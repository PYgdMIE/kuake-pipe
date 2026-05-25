# kuake-pipe

> 本地数据 → 夸克网盘 → AutoDL 服务器 全自动中转。**零硬编码 / 凭据自动抓取 / token 过期自动重登 / 实时抢卡**。

[![Tests](https://github.com/PYgdMIE/kuake-pipe/actions/workflows/test.yml/badge.svg)](https://github.com/PYgdMIE/kuake-pipe/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.0-blue)](CHANGELOG.md)

**支持**: Windows、macOS · **不支持**: Linux(夸克网盘无 Linux 客户端)

---

## TL;DR

```bash
pip install kuake-pipe         # 还没发 PyPI 前: pip install git+https://github.com/PYgdMIE/kuake-pipe
kuake init                     # 一次性扫码 + 输独立密码,全部自动
kuake push my-dataset ./data   # 之后只这一条命令
```

`./data` 自动打包 → 夸克客户端上行 → AutoPanel 触发服务器下载 → SSH 解压到 `/root/autodl-tmp/my-dataset/`。**全程零点击**。

---

## 这是什么 / 为什么

如果你也在 AutoDL 跑训练,用夸克网盘当数据中转,你大概经历过这些:

| 旧痛点 | kuake 的解决 |
|---|---|
| 换 AutoDL 实例就要改 SSH 信息 | `kuake init` 一次抓全,实例换了就重跑 |
| AutoPanel 鉴权头每月 F12 抓 | 自动 sign_in + 过期自动重登 |
| 夸克 Cookie 手工粘贴 | Playwright 扫码完自动抓 + 自动绑定到 AutoPanel |
| 想抢卡得自己刷网页 | `kuake grab` 后台轮询,看到立刻提醒(可选自动下单) |
| 多个零散脚本散落 | 一个 CLI 11 个子命令统一管理 |

---

## 工作原理

```
       ┌──────────┐                ┌────────────┐                ┌──────────────┐
       │  本地     │ ① 打包 zip      │  夸克 PC   │ ② 客户端备份    │  夸克云盘    │
       │  ./data  │ ────────────▶  │  客户端    │ ─────────────▶ │              │
       └──────────┘                │  (你已装)  │                └──────┬───────┘
                                   └────────────┘                       │
                                                                        │ ③ AutoPanel 下载
                                                                        ▼
                                                                ┌──────────────┐
                                                                │  AutoDL      │
                                                                │  服务器       │ ④ SSH 解压
                                                                │  实例         │ ───→ 完成
                                                                └──────────────┘
```

`kuake push` 一条命令依次走完四个阶段。Token 过期 → 用保存的密码哈希自动重登 → 继续。**整条链路从来不需要你打开浏览器二次操作**(除非新实例首次绑定)。

---

## 5 分钟上手

### 1. 装 Python 3.9+
- Win: [python.org](https://www.python.org/downloads/) 或 conda
- Mac: `brew install python@3.12`

### 2. 装夸克 PC 客户端 + 开启「备份」
- [pan.quark.cn/download](https://pan.quark.cn/download)
- 设置 → 备份 → **添加目录** `~/Downloads/UPLOAD` (或任何你想要的)
- 确认这个目录列表里的开关是**开着**的

### 3. AutoDL 控制台设独立密码
- [AutoDL 控制台](https://www.autodl.com/console/) → 任一实例 → 自定义服务 → 设密码(纯数字也行,例如 `220405`)
- **记住这个密码,kuake init 会要**

### 4. 装 kuake-pipe
```bash
pip install git+https://github.com/PYgdMIE/kuake-pipe
# 或本地:
git clone https://github.com/PYgdMIE/kuake-pipe && cd kuake-pipe && pip install -e .
```

### 5. 跑 init
```bash
kuake init
```

实际经过(整个 1-3 分钟):

| 步骤 | 你做什么 | kuake 在做什么 |
|---|---|---|
| 1 | 等 | Playwright Chromium 自动从淘宝镜像下载 |
| 2 | 等 | 浏览器弹出 → 自动切到微信扫码大 QR 页 |
| 3 | **扫码 AutoDL** | session 保存到 `~/.kuake/state/storage_state.json` |
| 4 | 回车选默认(第一个运行中实例) | 自动抓 SSH 信息(剪贴板) |
| 5 | 回车选默认密码模式 | 跳到 AutoPanel |
| 6 | **输独立密码 + 回车** | 拦截 sign_in 请求 → 抓 session token + 密码 SHA1 |
| 7 | **扫码夸克网盘** | 提取 Quark Cookie |
| 8 | 回车选默认 | POST `/netdisk/oauth/quark` 自动绑定 |
| 9 | 选 PC 备份目录(默认 1) | 走 panel API 列 `/我的备份/` |
| 10 | 等 | SSH 测连接 + smoke test 验证夸克客户端同步 |
| 11 | ✓ | 写盘 `~/.kuake/{config,credentials}.toml` |

### 6. 第一次 push
```bash
mkdir test && echo "hello world" > test/file.txt
kuake push first-try ./test
```

5-60 秒后(取决于夸克客户端同步速度),服务器上 `/root/autodl-tmp/first-try/file.txt` 就有了。

---

## 命令速查

```bash
# 主流程
kuake init                            # 首次配置 / 重新登录
kuake push <task> <src>               # 完整传输 (打包→上行→下载→解压)
kuake push <task> <src> --no-unzip    # 只下载不解压
kuake push <task> <src> --keep-zip    # 保留本地 zip
kuake retry <task>                    # 跳过打包,用已有 UPLOAD/<task>.zip
kuake refresh                         # 手动刷 AutoPanel session (自动 refresh 失败时)

# 服务器侧管理
kuake doctor                          # 12 项全链路自检
kuake ls                              # 列远端 /root/autodl-tmp/
kuake rm <task>                       # 删远端 + 本地 zip

# AutoDL 实例管理
kuake instances                       # 列所有实例 + 状态色标
kuake start [N]                       # 开机第 N 号(默认第一台已关机的)
kuake stop  [N] [-y]                  # 关机第 N 号 ⚠️ 慎用

# 抢卡 (v0.3+)
kuake grab                            # 任何卡有空闲都报
kuake grab --gpu "RTX 5090"           # 只盯 RTX 5090
kuake grab --gpu "RTX PRO 6000" --min-idle 2  # 至少 2 张卡空闲
kuake grab --region west-B --poll 3   # 西北B区,每3秒轮询
kuake grab --cpu-ok                   # 也接受 CPU 实例
kuake grab --auto-create              # ⚠️ 看到匹配就自动下单(扣费!)

# 配置
kuake reset                           # 清 ~/.kuake/(弹确认)
kuake reset --keep-credentials        # 仅清 config,留登录态
kuake --version
kuake --help                          # 总命令清单
kuake <command> --help                # 单命令选项
```

---

## 环境变量

| 变量 | 默认 | 作用 |
|---|---|---|
| `KUAKE_HOME` | `~/.kuake` | 配置根目录(多 profile 临时方案) |
| `KUAKE_DEBUG` | unset | 设了之后异常时打印完整 traceback |
| `KUAKE_DEBUG_LOG` | unset | 设了的话,把整个运行时间线写到该文件 |
| `KUAKE_TARGET` (probe only) | - | grab 测试用,选目标关键字 |
| `PLAYWRIGHT_DOWNLOAD_HOST` | 淘宝镜像 | 自定义 Chromium 下载源 |
| `HTTPS_PROXY` / `HTTP_PROXY` | - | 走代理(全 panel API 走) |

多 profile 例子:
```bash
KUAKE_HOME=~/.kuake-prod kuake init     # 第一个 profile
KUAKE_HOME=~/.kuake-dev  kuake init     # 第二个 profile
KUAKE_HOME=~/.kuake-prod kuake push ...
```

---

## 配置文件 `~/.kuake/`

```
~/.kuake/
├── config.toml              # 非敏感(host/port/路径),示例如下
├── credentials.toml         # 敏感(chmod 600 / Win icacls),示例如下
├── id_ed25519               # SSH 密钥(可选模式)
├── state/storage_state.json # Playwright session
└── .lock                    # 进程互斥锁
```

`config.toml` 长这样:
```toml
[instance]
host = "connect.westd.seetacloud.com"
port = 43306
user = "root"
auth_mode = "password"               # 或 "key"

[panel]
base = "https://a412422-xxxx-xxxx.westd.seetacloud.com:8443"
fs_id = "quark1"

[quark]
local_backup_dir = "C:/Users/mie/Downloads/UPLOAD"
cloud_backup_path = "/我的备份/来自:xxx 电脑备份/UPLOAD"

[remote]
tmp_dir = "/root/autodl-tmp"

[meta]
created_at = "2026-05-25T22:10:00"
last_refresh = "2026-05-25T22:10:00"
```

`credentials.toml`:
```toml
[ssh]
password = "..."                     # 或 key_path
key_path = ""

[panel]
authorization = "<40-char-hex>"      # session token (会自动刷新)
autodl_token = "<jupyter-token>"     # JupyterLab token(实例级)
expires_estimate = "2026-06-25T..."
standalone_password_sha1 = "<sha1>"  # 用于自动 refresh

[quark]
cookie = "<full Quark Cookie header>"
```

---

## 自动重登机制

Token 过期(`AuthFailed` / `expired` / `401`)时, `kuake push` 自动:

1. 检测响应 → 标记 `expired`
2. 用 `credentials.toml` 里保存的 `standalone_password_sha1` 调 `POST /sign_in`
3. 拿新 token 更新 credentials.toml
4. 重试原请求

⚠️ **如果你 init 时 AutoPanel 已经登录态在**(浏览器 cookie 缓存),工具拦截不到 sign_in 请求,没法保存哈希。后续 token 过期需要 `kuake init` 重跑。

防止此类情况: `init` 前先在浏览器清 AutoPanel cookies,或 `rm ~/.kuake/state/storage_state.json` 强制重扫。

---

## 国内网络

工具默认从淘宝镜像 [npmmirror](https://npmmirror.com/mirrors/playwright) 下载 Chromium。

自定义:
```bash
PLAYWRIGHT_DOWNLOAD_HOST=https://playwright.azureedge.net python -m playwright install chromium
```

走代理:
```bash
# Win PowerShell
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
kuake doctor

# Mac/Linux
export HTTPS_PROXY=http://127.0.0.1:7890
kuake doctor
```

---

## Debug 完整记录

要把整条链路记下来给开发者诊断:

```powershell
# Win
$env:KUAKE_DEBUG_LOG = "$env:USERPROFILE\kuake-trace.log"
kuake init
# 把 kuake-trace.log 发给开发者
```

```bash
# Mac/Linux
KUAKE_DEBUG_LOG=~/kuake-trace.log kuake init
```

日志包含:
- 运行环境(版本 / Python / OS / argv)
- 每条 console 输出对应的时间戳
- 每个 panel API 请求 URL + body + 响应码 + 响应 snippet (`REQ ... / RES ...`)
- 异常完整 traceback (`kuake.exc` logger)

报 issue 时附 trace log 能秒级定位 selector 失效 / auth 异常 / 上传卡死。

---

## 故障速查

| 症状 | 修 |
|---|---|
| `kuake push` 在 stage 2 卡死 | 夸克客户端没在同步,见 [TROUBLESHOOTING #1](docs/TROUBLESHOOTING.md#1-kuake-push-在-stage-2等夸克客户端上行卡死) |
| `AUTH_EXPIRED` 后报 `kuake refresh` 也没救 | 缺密码哈希,见 [#2](docs/TROUBLESHOOTING.md#2-auth_expired-报错但-kuake-refresh-也不行) |
| `SCRAPER_FAILED: No instances detected` | AutoDL DOM 改了,见 [#3](docs/TROUBLESHOOTING.md#3-session_dead--scraper_failed) |
| Chromium 下载卡死 | [#4](docs/TROUBLESHOOTING.md#4-playwright-chromium-下载失败) |
| `所有实例都已关机` | [#5](docs/TROUBLESHOOTING.md#5-所有实例都已关机) |
| 备份目录列出来不对 | [#8](docs/TROUBLESHOOTING.md#8-夸克备份目录抓不到-pc-客户端的备份) |
| 中文乱码 | [#11](docs/TROUBLESHOOTING.md#11-中文路径乱码) |

完整 13 个症状: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

---

## 退出码(脚本化用)

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 通用错误 |
| 2 | 用户输入 / 参数错误 |
| 3 | 认证失败(token 死了,需 init) |
| 4 | 网络不可达 |
| 5 | SSH 错误 |
| 6 | 夸克云端同步超时 |
| 7 | 并发锁占用 |
| 130 | Ctrl+C |

---

## 安全说明

- 凭据存 `~/.kuake/credentials.toml`,Posix `chmod 600`,Win `icacls` 限当前用户读写
- **不存明文 AutoPanel 密码** —— 只存 SHA1 哈希
- Quark Cookie 是个长字符串,跟你普通浏览器 cookie 一样安全等级
- 推荐使用 `kuake init --ssh-key` 走密钥模式,不存 SSH 明文密码
- **不要把 `~/.kuake/credentials.toml` 上传任何云端 / 共享**

---

## 开发

```bash
git clone https://github.com/PYgdMIE/kuake-pipe
cd kuake-pipe
python -m venv .venv
source .venv/bin/activate                    # Win: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -v                                    # 90+ tests pass
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。Selector 失效是最高频贡献场景。

### 测试

| 层 | 工具 | 覆盖范围 |
|---|---|---|
| Unit | pytest | pack / panel_api / config / selectors / EOF / parse helpers |
| Mock 集成 | requests-mock | panel API 三态过期检测、refresh 链路 |
| 真账号 E2E | docs/MANUAL_TEST.md | T1-T12 人工 checklist |

DOM-依赖的部分会随 AutoDL/夸克页面改版失效,修复点集中在 [`src/kuake/browser/selectors.py`](src/kuake/browser/selectors.py)。

---

## 已知限制

| 限制 | 说明 | 计划 |
|---|---|---|
| smoke test 留 1KB 测试文件在云端 | Quark 删除 API 未探到 | v0.4 |
| session 自动恢复检测 2s 太短 | 偶尔需重扫码 | v0.4 调到 5s |
| macOS 未在物理机验证 | 代码兼容,首次可能有 path / Gatekeeper 坑 | 等用户反馈 |
| 多 profile 用 KUAKE_HOME 切换 | 内建支持还没做 | v0.4 |
| `--auto-create` 没真实下单跑过 | API 截了但没真买 | 等用户反馈 |
| `kuake stop` 慎用 | 误关训练实例无法挽回 | 加二次确认改进 |

---

## v0.3.0 实现细节

| 维度 | |
|---|---|
| Python 模块 | 30 个 (`src/kuake/`) |
| CLI 命令 | 11 (`init/push/retry/refresh/doctor/ls/rm/reset/instances/start/stop/grab`) |
| 单元测试 | 90+ |
| 真账号 E2E | T1-T10 通过 (T11 Mac 待验,T9b 故意跳) |
| 代码行数 | ~3000(src) + ~1300(tests) + ~1500(docs) |

发现并修的关键 bug(随便选几个):
- `code="AuthFailed"` 未被识别为过期 → fix is_expired_response
- refresh 在 push 内被调用 lock 冲突 → 拆 `_do_refresh()` 无锁版
- SessionDead 被 AutoExpired 覆盖丢失上下文 → 让原异常传播
- AutoPanel 已登录态时拦截不到 sign_in 哈希 → warn + 引导
- Quark 备份目录抓的是公开聚合页非文件树 → 改 panel API 列

---

## License

MIT — see [LICENSE](LICENSE)
