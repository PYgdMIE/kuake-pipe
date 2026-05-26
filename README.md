# kuake-pipe

> 本地数据 → 夸克网盘 → AutoDL 服务器 全自动中转 + **抢卡 / 下单 / 配凭据 / 推数据 一条命令端到端**。

[![Tests](https://github.com/PYgdMIE/kuake-pipe/actions/workflows/test.yml/badge.svg)](https://github.com/PYgdMIE/kuake-pipe/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.5.0-blue)](CHANGELOG.md)

**支持平台**: Windows · macOS · **Linux**(v0.4 起,不再依赖夸克 PC 客户端)

---

## TL;DR — 三种使用方式

```bash
pip install git+https://github.com/PYgdMIE/kuake-pipe
kuake init    # 一次性扫码 (AutoDL + Quark),仅首次
```

```bash
# ① 命令行  —— 适合脚本化、CI、熟悉 CLI 的用户
kuake push my-dataset ./data

# ② Web UI  —— 适合点选、看实时状态、有图形化偏好
kuake serve                  # 浏览器自动打开 http://127.0.0.1:8765

# ③ 全自动端到端  —— 适合 Claude Code / Codex / 无人值守批处理
KUAKE_AUTOPANEL_PASSWORD=xxxx kuake auto \
  --gpu "RTX 3080 Ti" --task my-exp --src ./data \
  --expand-data-disk 100 --max-market-iter 100
```

`./data` 自动打包 → 通过 Quark Cloud API **直接上传**到云盘 → AutoPanel 触发服务器下载 → SSH 解压到 `/root/autodl-tmp/my-dataset/`。**全程零点击**。

---

## v0.4 重大变更

**砍掉了夸克 PC 客户端依赖**。0.3 及以前必须先装夸克客户端 + 在 GUI 里配置「备份」目录,这是 Linux 不支持的根因,也是新用户最大的踩坑点。

v0.4 改用 cookie 鉴权直接调 Quark Cloud HTTP API 上传(协议逆向自 pan.quark.cn 网页版),收益:

- ✅ **Linux 也能跑** — 没有任何 GUI 客户端依赖
- ✅ **零 GUI 配置** — `kuake init` 只问 1 个云端目录,默认 `/kuake-uploads`
- ✅ **stage 2 不再有 60s+ 等待** — 直接 PUT,失败立刻报错
- ✅ **headless / CI 友好** — 服务器、Docker 容器都能跑

旧用户的 config 兼容(`local_backup_dir` 字段被静默忽略)。

---

## 这是什么 / 为什么

如果你也在 AutoDL 跑训练,用夸克网盘当数据中转,你大概经历过这些:

| 旧痛点 | kuake 的解决 |
|---|---|
| 换 AutoDL 实例就要改 SSH 信息 | `kuake init` 一次抓全,实例换了就重跑 |
| AutoPanel 鉴权头每月 F12 抓 | 自动 sign_in + 过期自动重登 |
| 夸克 Cookie 手工粘贴 | Playwright 扫码完自动抓 + 自动绑定到 AutoPanel |
| 必须装夸克 PC 客户端 + GUI 配「备份」目录 | **v0.4 起直接 HTTP API 上传,不依赖客户端** |
| 想抢卡得自己刷网页 | `kuake grab` 后台轮询,看到立刻提醒(可选自动下单) |
| 多个零散脚本散落 | 一个 CLI 11 个子命令统一管理 |

---

## 工作原理

```
       ┌──────────┐                ┌──────────────┐
       │  本地     │ ① 打包 zip      │  夸克云盘    │
       │  ./data  │ ───────────────▶│  (直接 API   │
       └──────────┘   ② HTTP 上传    │   上传)      │
                                    └──────┬───────┘
                                           │ ③ AutoPanel 触发服务器下载
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
- Linux: 包管理器(apt / yum / pacman)装 python3.9+

### 2. AutoDL 控制台设独立密码
- [AutoDL 控制台](https://www.autodl.com/console/) → 任一实例 → 自定义服务 → 设密码(纯数字也行,例如 `220405`)
- **记住这个密码,kuake init 会要**

### 3. 装 kuake-pipe
```bash
pip install git+https://github.com/PYgdMIE/kuake-pipe
# 或本地:
git clone https://github.com/PYgdMIE/kuake-pipe && cd kuake-pipe && pip install -e .
```

### 4. 跑 init
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
| 8 | 回车选默认云端目录(`/kuake-uploads`) | 不存在则自动创建 |
| 9 | 等 | SSH 测连接 + smoke test 上传 1KB 验证 |
| 10 | ✓ | 写盘 `~/.kuake/{config,credentials}.toml` |

只需要在 step 3 / 6 / 7 三处实际操作(扫码 + 输独立密码)。

### 5. 第一次 push
```bash
mkdir test && echo "hello world" > test/file.txt
kuake push first-try ./test
```

几秒后,服务器上 `/root/autodl-tmp/first-try/file.txt` 就有了。

### 全自动模式(CI / 脚本化)

整条 `kuake init` 默认只剩 2 处手动:**扫 AutoDL QR + 扫 Quark QR**(账号绑定的必经步骤,无法自动化)。其它都能用 flag / env var 一次给齐:

```bash
KUAKE_AUTOPANEL_PASSWORD=220405 \
kuake init \
  --instance 1 \
  --ssh-key \
  --cloud-dir /kuake-uploads \
  --no-smoke \
  --headless     # ⚠ 已有 storage_state 时才能用 (跳过浏览器可见)
```

`kuake push` 没有任何交互,跑就行:

```bash
kuake push my-task ./data
```

---

## Web UI(`kuake serve`)

```bash
kuake serve                # 默认 http://127.0.0.1:8765, 自动开浏览器
kuake serve --port 9000 --no-browser
```

单页三个 tab,对应三种主任务:

### 🎯 抢卡 tab — 实时市场监督 + 一键锁卡

- **左侧过滤栏**:GPU 型号下拉 / 最少空闲张数 / 区域多选 chips(动态从市场数据收集)/ 也接受 CPU 实例
- **创建配置**:卡数 / 数据盘扩容 / 系统盘扩容 / **三级镜像选择器**(框架 → 版本 → Python → CUDA,5 个框架预置)
- **实时轮询**:开关 + 间隔可调(3 / 5 / 10 / 30 秒)+ 连续 3 次失败自动退避
- **市场表**:价格列默认升序;每行可展开看详细配置(CPU 核数 / 每卡内存 / GPU 显存 / 主机磁盘 / CUDA / 驱动 / OS / CPU 型号 / TFLOPS)
- **锁定**:点机器行的「锁定」→ 弹模态显示 PLAN 摘要 + 必输大写 `YES` → POST 真下单
- **桌面通知**:抢到机器后弹系统通知(失焦也能收到)

### 📦 上传 tab — 离线无人值守

- **原生路径选择器**:点「选目录 / 选文件」按钮 → 后端 tkinter 弹本机系统对话框 → 填回绝对路径(解决浏览器拖拽只能拿文件名的限制)
- **push 参数 toggle**:`--no-unzip` / `--keep-zip` 两个复选框
- **取消运行中**:红色按钮,后端 terminate 子进程 + 标记 `cancelled`
- **4 阶段进度条**:打包 → 上传夸克 → AutoPanel 拉取 → SSH 解压,当前阶段橙色脉冲,已完成的变绿
- **历史 job**:状态 pill(running/completed/failed/cancelled/interrupted),失败的一键重试(复用 task + src + flags)
- **离线持久**:**关闭浏览器、刷新页面、重启服务器都不影响**进行中的 job(job state 落 `~/.kuake/jobs/`,SSE 重连自动 tail)
- **远端文件**:点击刷新调 `kuake ls` 列服务器侧文件,每行可删
- **桌面通知**:完成时弹系统通知

### 🤖 全自动 tab — 端到端一键

- **完整表单**:GPU / max-iter / 卡数 / 数据盘 / 系统盘 / 镜像 / ready-timeout / **AutoPanel 密码**(password 输入,不落盘)/ 云端目录 / 任务名 / 本地路径 / push 参数 / **stop-after 停点**
- **5 阶段进度条**:轮询市场 → 下单 → 等就绪 → init 配凭据 → push 推数据
- **stop-after 4 个挡位**:
  - `create` 仅下单后停(异步等待场景)
  - `ready` 等机器开机后停(准备上 SSH)
  - `init` 配好 `~/.kuake/{config,credentials}.toml` 停
  - `push` 完整跑完(默认)
- **启动前 confirm**:列 GPU + stop-after,防误操作
- **真扣费警告**:UI 底部固定提示框,所有挡位都明示

---

## CC / Codex 自动化场景

`kuake auto` + `kuake serve` 的 REST API 可以让 AI 工具(Claude Code、Codex CLI)一句话发起完整链路。

### 场景 A:CLI 形式(子进程调起)

```bash
# Claude Code 在 Bash tool 里执行
KUAKE_AUTOPANEL_PASSWORD=$KUAKE_PW kuake auto \
  --gpu "RTX 5090" \
  --task experiment-2026-05-26 \
  --src /workspaces/training-data \
  --expand-data-disk 200 \
  --max-market-iter 0      # 0 = 无限等到抢到
```

阻塞直到全链完成。exit 0 = 成功;非 0 = 任一阶段失败,stderr 有原因。

### 场景 B:HTTP 形式(`kuake serve` 启动后调 REST)

```bash
# 启动一次 (后台)
kuake serve --no-browser &

# 发请求, 拿 job_id
curl -X POST http://127.0.0.1:8765/api/auto-start \
  -H "Content-Type: application/json" \
  -d '{
    "autopanel_password": "'"$KUAKE_PW"'",
    "gpu": ["RTX 5090"],
    "task": "experiment-2026-05-26",
    "src": "/workspaces/training-data",
    "expand_data_disk_gb": 200,
    "stop_after": "push"
  }'
# → {"job_id": "abc123def456"}

# 流式看日志
curl -N http://127.0.0.1:8765/api/push-stream/abc123def456
```

### 关键命令(给 AI 自己调)

| 命令 | 用途 |
|---|---|
| `kuake auto --stop-after create` | 仅下单,返回 uuid 给后续阶段 |
| `kuake wait-running <uuid>` | 阻塞到 `status=running`(独立,可单独用)|
| `kuake init --instance N --headless` | 无头模式 init(`storage_state` 已存在时)|
| `kuake confirm-create --plan-file X --yes` | 跳过 stdin YES(3s grace 防误)|

### 仍绕不掉的人工(三件)

1. **首次扫两次微信码**(AutoDL + Quark)— 个人微信账号
2. **Token 过期重扫**(AutoDL JWT / Quark cookie)
3. **下单的 3 秒 grace 窗口** — `--yes` 启用后不弹 stdin,但仍打印警告 + 3 秒 Ctrl+C 抢救

除以上,**全可 CC/Codex 一行调起**。

---

## 命令速查

```bash
# ── 数据传输 ────────────────────────────────────────────
kuake init                            # 首次配置 / 重新登录
kuake init --headless                 # 无头模式 (要求 storage_state 已存在, auto 用)
kuake push <task> <src>               # 完整传输 (打包→上行→下载→解压)
kuake push <task> <src> --no-unzip    # 只下载不解压
kuake push <task> <src> --keep-zip    # 保留本地 zip
kuake retry <task>                    # 跳过打包,用已有 UPLOAD/<task>.zip
kuake refresh                         # 手动刷 AutoPanel session
kuake doctor                          # 12 项全链路自检

# ── 远端文件管理 ────────────────────────────────────────
kuake ls                              # 列远端 /root/autodl-tmp/
kuake rm <task>                       # 删远端 + 本地 zip

# ── 实例管理 ───────────────────────────────────────────
kuake instances                       # 列所有实例 + 状态色标
kuake whoami                          # 钱包余额 + 实例数 (只读)
kuake start [N]                       # 开机第 N 号
kuake stop  [N] [-y]                  # 关机第 N 号 ⚠️ 慎用
kuake wait-running <uuid|N|前缀>       # 阻塞到 status=running (脚本化 chain 用)

# ── 抢卡 + 克隆 + 下单 (默认 PLAN dry-run,绝不下单) ─────────
kuake grab                            # 任何卡 / 任何区 → 生成 PLAN
kuake grab --gpu "RTX 5090"           # 只盯特定型号
kuake grab --gpu "RTX PRO 6000" --min-idle 2
kuake grab --region west-B --poll 3
kuake grab --cpu-ok                   # 也接受 CPU 实例
kuake grab --gpu-count 2 --expand-data-disk 100 --system-disk-expand 20

kuake clone                           # 交互选源实例 → 找同 GPU 新机器 → PLAN
kuake clone 1                         # 用第 1 号实例作为源
kuake clone <uuid前缀> --same-region   # uuid 前缀指定源 + 限制同区

# ⚠️ 真下单的唯一入口 (会扣费)
kuake confirm-create --plan-file ~/.kuake/plans/plan_xxxx.json         # 交互输 YES
kuake confirm-create --plan-file ... --yes                              # CC/Codex: 3s grace

# ── 端到端自动化 (CC/Codex 一键调) ──────────────────────
kuake auto --gpu "RTX 3080 Ti" \
  --task my-exp --src ./data \
  --expand-data-disk 100 \
  --max-market-iter 100               # grab→create→wait→init→push

kuake auto --stop-after create        # 仅下单返回 uuid
kuake auto --stop-after ready         # 等就绪后停
kuake auto --stop-after init          # 配好凭据停
kuake auto --stop-after push          # 完整 (默认)

# ── Web UI ─────────────────────────────────────────────
kuake serve                           # 启本地 :8765 + 开浏览器 (三 tab)
kuake serve --port 9000 --no-browser  # 自定义端口 + 不开浏览器

# ── 配置 ──────────────────────────────────────────────
kuake reset                           # 清 ~/.kuake/(弹确认)
kuake reset --keep-credentials        # 仅清 config,留登录态
kuake --version
kuake --help
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

`config.toml` 长这样(v0.4):
```toml
[instance]
host = "connect.westd.seetacloud.com"
port = 43306
user = "root"
auth_mode = "key"                    # 或 "password"

[panel]
base = "https://a412422-xxxx-xxxx.westd.seetacloud.com:8443"
fs_id = "quark1"

[quark]
cloud_backup_path = "/kuake-uploads" # 不存在会自动创建

[remote]
tmp_dir = "/root/autodl-tmp"

[meta]
created_at = "2026-05-26T22:10:00"
last_refresh = "2026-05-26T22:10:00"
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
| `QUARK_UPLOAD_FAILED` 报 403 / 401 | Quark cookie 过期,跑 `kuake init` 重扫 Quark 二维码 |
| `AUTH_EXPIRED` 后报 `kuake refresh` 也没救 | 缺密码哈希,见 [#2](docs/TROUBLESHOOTING.md#2-auth_expired-报错但-kuake-refresh-也不行) |
| `SCRAPER_FAILED: No instances detected` | AutoDL DOM 改了,见 [#3](docs/TROUBLESHOOTING.md#3-session_dead--scraper_failed) |
| Chromium 下载卡死 | [#4](docs/TROUBLESHOOTING.md#4-playwright-chromium-下载失败) |
| `所有实例都已关机` | [#5](docs/TROUBLESHOOTING.md#5-所有实例都已关机) |
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
pytest -v                                    # 240+ tests pass
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

| 限制 | 说明 | 状态 |
|---|---|---|
| smoke test 留 1KB 测试文件在云端 | Quark 删除 API 未探到 | 待 |
| Linux / 物理 Mac 未在真机长跑验证 | 代码兼容,首次可能有 path 坑 | 等用户反馈 |
| 上传暂未真并发 | parallel_upload 需要计算增量 SHA1 hash_ctx,目前是单连接 + 4MB 分片(顺序) | v0.6 |
| 上传无断点续传 | upload_id + parts 状态本地化未做 | v0.6 |
| 多 profile 用 KUAKE_HOME 切换 | 内建支持还没做 | v0.6 |
| `kuake stop` 慎用 | 误关训练实例无法挽回 | 加二次确认改进 |
| ~~`--auto-create` 没真实下单跑过~~ | ~~API 截了但没真买~~ | ✅ v0.5 真账号验证, payload schema 修复 |
| ~~confirm-create 必须人工输 YES~~ | ~~CC/Codex 自动化无法用~~ | ✅ v0.5 加 `--yes` flag + 3s grace |
| ~~kuake init 弹浏览器无法 hands-off~~ | ~~自动化中断点~~ | ✅ v0.5 加 `--headless`(storage_state 有效时) |
| ~~Web UI 缺失~~ | ~~只有 CLI~~ | ✅ v0.5 `kuake serve` 三 tab |

---

## 实现细节

| 维度 | |
|---|---|
| Python 模块 | 35 个 (`src/kuake/`) — 含 `quark_uploader.py` / `autodl_planner.py` / `server.py` / `commands/auto.py` 等 |
| CLI 子命令 | **18 个** (init/push/retry/refresh/doctor/whoami/ls/rm/reset/instances/start/stop/grab/clone/confirm-create/wait-running/auto/serve) |
| Web UI 路由 | 14 个 REST (`/api/market`, `/auto-start`, `/push-stream/<id>` 等) |
| 单元测试 | **240+**(覆盖 server 路由 / auto chain / 上传 / grab planner / quark_uploader 等)|
| 真账号 E2E | Quark 直接上传 / confirm-create 真下单 / clone +data disk PLAN 全部跑通 |

### 关键技术决策

- **协议逆向 (v0.4)**:用 Playwright 启动 headed Chromium 上传 5KB 测试文件,intercept 所有请求,落 HAR + JSONL trace,识别出 Quark PUT 真实 host 是 `{bucket}.pds.quark.cn`(原 `quarkpan` 库 hardcode 的 `oss-cn-shenzhen.aliyuncs.com` 自 2025 起已 404)
- **AutoDL create payload (v0.5)**:用 Playwright `route.abort()` 截获真实 POST body,确认 `expand_data_disk` 单位是字节、`coupon_id_list/duration/num` 拆在顶层 `price_info`、`cg_application_info` 有 4 个子字段(`scripts/probe_create_intercept.py` 是这个流程的工具脚本,以后 AutoDL 改 schema 时可重抓)
- **payg_price 单位修正 (v0.5)**:之前按"分"(0.01 元)算,实际是"厘"(0.001 元),价格全部 ×10 偏差;一次性纠正 + 测试用例的 fixture 值同步更新
- **`_spawn_job` 公共助手 (v0.5)**:push 和 auto 共享 runner + log 持久化 + cancel + SSE 队列,通过 `kind` 字段区分;`_detect_stage` 返回 `(n, total)` 同时支持 push 4 段 + auto 5 段
- **绕过 GUI 客户端**:Cookie 已经被 init 阶段抓住(供 AutoPanel 绑定用),再喂给我们自己的 uploader 就能直接调 Quark Cloud HTTP API,完全跳过夸克客户端的「备份」功能
- **保留 panel API**:stage 3(服务器侧从云盘下载)仍然走 AutoPanel,因为这是 AutoDL 提供的代下载服务 — 这不是 kuake 引入的依赖,而是 AutoDL 的产品形态

---

## License

MIT — see [LICENSE](LICENSE)
