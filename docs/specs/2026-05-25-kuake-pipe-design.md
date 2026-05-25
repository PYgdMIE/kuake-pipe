# kuake-pipe v1 设计文档

**日期**: 2026-05-25
**作者**: 与 Claude 协作
**状态**: 设计完成，待实施

---

## 1. 背景与动机

现有 `C:\Users\mie\Downloads\kuake\` 是一个本地数据 → 夸克网盘 → AutoDL 服务器的自动化中转管线。痛点：

- SSH 连接信息硬编码在两个 `.py` 文件中，换 AutoDL 实例必须双处同步改
- AutoPanel 鉴权头约一个月过期，需手动 F12 抓取
- 夸克客户端备份目录路径含 PC 名，跨电脑迁移失败
- 现有代码以脚本形态散落，无 CLI、无 pip 包，难以发布与分发

**目标**: 重构为发布级 pip 包 `kuake-pipe`（CLI 命令 `kuake`），消灭所有可消灭的人工步骤，使任意 Windows/macOS 用户能通过 `pip install kuake-pipe && kuake init` 在数分钟内打通从本地到 AutoDL 服务器的完整管线。

---

## 2. 设计输入（已与用户对齐）

| 维度 | 决定 | 理由 |
|---|---|---|
| 目标用户 | AutoDL + 夸克网盘用户的通用工具 | 公开发布到 GitHub + PyPI |
| 自动化范围 | 完全自动（含 Playwright 浏览器自动化抓凭据） | 用户希望消灭月度 F12 |
| 分发形态 | `pip install kuake-pipe`，CLI 命令 `kuake` | 标准化、跨平台、低门槛 |
| 首次登录 | Playwright 可见浏览器，用户扫码/SMS 登录一次，保存 storage_state | 夸克/AutoDL 都不支持无人值守登录 |
| Profile | 单 profile | 用户单实例为主，多实例属 v1.5 |
| 凭据存储 | 明文 TOML + 跨平台 ACL 加固 | 简单、不引入加密复杂度 |
| 过期处理 | 自动 headless 重刷，失败回退 `kuake init` | 多数情况下用户零感知 |
| 云端路径 | init 时枚举夸克备份目录让用户选 | 跨电脑/跨账号兼容 |
| 平台 | v1 仅 Windows + macOS（Linux 无夸克客户端） | 物理约束 |
| 交付策略 | 一次性大爆炸 v1（含 Playwright 全套） | 用户决定 |

---

## 3. 包结构

```
kuake-pipe/                          # GitHub 仓库根
├── pyproject.toml                   # 包元数据、依赖、entry_points
├── README.md                        # 顶部放夸克客户端配置截图 + 国内镜像 + 故障速查
├── LICENSE                          # MIT
├── .gitignore                       # 排除 ~/.kuake/、Playwright 浏览器缓存
├── docs/
│   ├── specs/2026-05-25-kuake-pipe-design.md   # 本文档
│   ├── MANUAL_TEST.md               # E2E 人工 checklist
│   └── TROUBLESHOOTING.md           # 故障速查
├── src/kuake/
│   ├── __init__.py                  # __version__
│   ├── cli.py                       # 入口：UTF-8 stdout + i18n 输出层 + 文件锁
│   ├── platform_guard.py            # Linux 早退；Windows icacls；macOS Gatekeeper 提示
│   ├── i18n.py                      # error.code → 中文/英文消息表
│   ├── errors.py                    # 异常类（英文 raise），配 i18n.code
│   ├── config.py                    # 原子写（tmp+rename）+ 跨平台 ACL 强化
│   ├── concurrency.py               # ~/.kuake/.lock 双平台文件锁
│   ├── progress.py                  # rich.progress 封装
│   ├── proxy.py                     # 探测 HTTPS_PROXY，配 paramiko SOCKS
│   ├── pack.py                      # zip 打包 + md5
│   ├── panel_api.py                 # +expiry_check 三态判 + 自动 refresh hook
│   ├── ssh_exec.py                  # 支持密码/密钥双模 + unzip 检测/兜底
│   ├── commands/
│   │   ├── init.py
│   │   ├── push.py
│   │   ├── retry.py
│   │   ├── refresh.py
│   │   ├── doctor.py
│   │   ├── reset.py
│   │   ├── ls.py
│   │   └── rm.py
│   └── browser/                     # 全部 lazy import；仅 init/refresh 触发加载
│       ├── __init__.py
│       ├── installer.py             # 国内 PLAYWRIGHT_DOWNLOAD_HOST 镜像 + 自动 install
│       ├── session.py               # storage_state 原子写
│       ├── selectors.py             # 多层 fallback selector 集中表
│       ├── autodl_scraper.py        # 实例列表 + SSH + AutoPanel URL
│       ├── panel_scraper.py         # 拦截请求抓 auth headers
│       ├── quark_scraper.py         # 枚举云端备份目录
│       └── smoke_test.py            # init 末尾上传 1KB 验证夸克客户端是否同步
└── tests/
    ├── fixtures/                    # HTML 快照，用于 selector 失效预警
    ├── test_config_atomic.py
    ├── test_pack.py
    ├── test_panel_api.py
    ├── test_panel_expiry.py
    ├── test_browser_selectors.py
    ├── test_concurrency_lock.py
    └── test_ssh_unzip_fallback.py
```

---

## 4. CLI 表面

```
kuake init [--no-smoke] [--ssh-key]    # 首次配置向导
kuake push <task> <src> [--no-unzip] [--keep-zip]
kuake retry <task>                     # 跳过 stage1，复用 UPLOAD/<task>.zip
kuake refresh                          # 强制刷 panel token + cookie
kuake doctor                           # 全链路自检
kuake ls                               # 远端任务列表
kuake rm <task>                        # 远端删除 + 本地 UPLOAD/<task>.zip
kuake reset [--keep-credentials]       # 清空 ~/.kuake/
kuake --version | -V
kuake --help | -h
```

### 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 通用错误 |
| 2 | 用户输入错误 |
| 3 | 认证错误（refresh 也救不了） |
| 4 | 网络错误 |
| 5 | SSH 远端命令失败 |
| 6 | 云端同步超时 |
| 7 | 并发锁占用 |

---

## 5. 端到端数据流

### 5.1 `kuake init`（首次，约 2-5 分钟）

```
1.  platform_guard       → 非 Win/Mac 早退
2.  concurrency.acquire  → ~/.kuake/.lock 独占
3.  browser.installer    → 检测 Chromium，无则设国内镜像 + playwright install chromium
4.  browser.session      → 启动 headed Chromium
5.  autodl_scraper.login → 跳 AutoDL 登录页，等用户扫码（120s 超时）
6.  autodl_scraper.list  → 抓实例列表（多层 selector fallback）
7.  CLI prompt           → 选实例
8.  autodl_scraper       → 抓 SSH 信息 + AutoPanel URL
9.  ssh_key 模式可选     → 生成 ed25519 → 通过 SSH 自动写入服务器 ~/.ssh/authorized_keys
10. panel_scraper        → 跳 AutoPanel，拦截首个请求抓 auth headers
11. quark_scraper.login  → 跳夸克网盘，等用户扫码
12. quark_scraper.list   → 列 /我的备份/ 子目录
13. CLI prompt           → 选 PC 备份目录 + 下级目录
14. ssh_exec.test        → 连一次 paramiko，跑 whoami && df -h
15. config.atomic_write  → 写 ~/.kuake/config.toml + credentials.toml
16. session.save         → storage_state.json 原子写
17. smoke_test           → 1KB temp.zip → poll 云端 60s
18. cleanup              → 删 temp
19. browser.close + lock.release
```

### 5.2 `kuake push <task> <src>`（无浏览器，纯 HTTP+SSH）

```
1.  platform_guard + lock
2.  validate task 名（[a-zA-Z0-9_-]+）
3.  config.load → 离过期 <24h 主动 refresh
4.  pack.make_zip → UPLOAD/<task>.zip + md5 + 进度条
5.  panel_api.find_by_path → 轮询云端
    - expiry_check 异常 → lazy import browser → headless refresh → retry 1 次
    - 超时 60min → exit 6
6.  panel_api.trigger_download
7.  panel_api.wait_task → 显示 progress
8.  ssh_exec.unzip_remote
    - which unzip → apt install -y unzip → Python zipfile 兜底
9.  rich 总结输出
10. lock.release
```

### 5.3 过期自动刷新（透明发生在 push 中）

```
panel_api 请求 → expiry_check 三态判定
  - 200 OK & code=success                            → 正常返回
  - 401 / code!=success / Content-Type=text/html     → AuthExpired
触发 refresh:
  - lazy import playwright
  - launch headless + storage_state.json
  - 跳 AutoPanel URL，截获 auth headers
  - 更新 credentials.toml
  - 若 storage_state 也失效 → 抛 SessionDead → 提示 kuake refresh（非 headless）
原请求 retry 一次
```

---

## 6. 错误处理与 i18n

异常分层：

```python
# errors.py
class KuakeError(Exception):
    code: str         # 'AUTH_EXPIRED' / 'SSH_CONNECT_FAILED' / ...
    hint_key: str     # 对应 i18n 表
    exit_code: int    # 1-7

# i18n.py
MESSAGES_ZH = {
    'AUTH_EXPIRED': 'AutoPanel token 已过期且刷新失败',
    'auth.expired.hint': '请运行 `kuake refresh` 重新扫码登录',
    ...
}

# cli.py 顶层捕获
try:
    run()
except KuakeError as e:
    console.print(f"[red]✗[/red] {i18n.t(e.code)}")
    console.print(f"[yellow]提示:[/yellow] {i18n.t(e.hint_key)}")
    sys.exit(e.exit_code)
```

每个异常**必须**带 hint_key，避免"用户看错误信息但不知道下一步"。

---

## 7. P0-P2 优化项 → 模块映射

| 优先级 | 优化点 | 落地位置 |
|---|---|---|
| P0-1 | Python 3.9+ 兼容 | pyproject deps: `tomli;python_version<"3.11"` |
| P0-2 | Chromium 国内镜像 | `browser/installer.py` 自动设 PLAYWRIGHT_DOWNLOAD_HOST |
| P0-3 | scraper 抗 DOM 变动 | `browser/selectors.py` 三层 fallback + fixtures 测试 |
| P0-4 | Windows ACL + SSH 密钥 | `platform_guard.py` icacls + `commands/init.py` 密钥模式 |
| P0-5 | smoke test 验证夸克客户端 | `browser/smoke_test.py` init 末尾跑 |
| P1-6 | 进度条 | `progress.py` + push 各阶段调用 |
| P1-7 | lazy import Playwright | `browser/__init__.py` 仅 init/refresh import |
| P1-8 | UTF-8 中文路径 | `cli.py` 入口 stdout.reconfigure |
| P1-9 | unzip 检测兜底 | `ssh_exec.py` which → apt → zipfile |
| P1-10 | 过期三态判定 | `panel_api.py` expiry_check |
| P2-11 | task ls/rm | `commands/ls.py`, `commands/rm.py` |
| P2-12 | 并发锁 | `concurrency.py` |
| P2-13 | 代理探测 | `proxy.py` + doctor |
| P2-14 | 中英分层 | `errors.py` + `i18n.py` |
| P2-15 | 原子 config + reset | `config.py` + `commands/reset.py` |

---

## 8. 依赖列表

| 依赖 | 用途 | 是否必装 |
|---|---|---|
| paramiko | SSH | ✅ |
| requests | AutoPanel HTTP | ✅ |
| playwright | 浏览器自动化 | ✅（Chromium lazy install） |
| rich | 进度条/彩色输出 | ✅ |
| tomli | TOML 读（<3.11） | 条件 |
| tomli-w | TOML 写 | ✅ |

---

## 9. 配置文件

### `~/.kuake/config.toml`（非敏感）
```toml
[instance]
host = "connect.westd.seetacloud.com"
port = 34267
user = "root"
auth_mode = "password"          # 或 "key"

[panel]
base = "https://xxx.autodl.host"
fs_id = "quark1"

[quark]
local_backup_dir = "C:/Users/mie/Downloads/UPLOAD"
cloud_backup_path = "/我的备份/来自：xxx 电脑备份/UPLOAD"

[remote]
tmp_dir = "/root/autodl-tmp"

[meta]
created_at = "2026-05-25T01:30:00"
last_refresh = "2026-05-25T01:30:00"
```

### `~/.kuake/credentials.toml`（敏感，0600 / icacls）
```toml
[ssh]
password = "xxx"                # 或 key_path
key_path = "~/.kuake/id_ed25519"

[panel]
authorization = "Bearer ..."
autodl_token = "..."
expires_estimate = "2026-06-25T01:30:00"
```

### `~/.kuake/state/storage_state.json`
Playwright 标准格式，含 AutoDL/夸克 cookies + localStorage。

### `~/.kuake/.lock`
fcntl/msvcrt 文件锁。

---

## 10. 测试策略

| 层 | 内容 | 工具 |
|---|---|---|
| 单元 | pack/md5、TOML 原子写、expiry_check 三态、selector fallback、文件锁、SSH key 生成 | pytest |
| 集成（mock） | fixtures/*.html 喂 Playwright route 拦截，验证 scraper 在 DOM 变动下命中 | pytest-playwright |
| 集成（mock HTTP） | panel_api 全 mock，含过期三态、超时 | requests_mock |
| E2E（人工） | docs/MANUAL_TEST.md 五个 checklist | 人 |

覆盖目标：单元 + mock 集成 ≥ 80%。E2E 不进 CI。

---

## 10.A 具体取值明确化（自审补充）

### Playwright Chromium 国内镜像 fallback 顺序

`browser/installer.py` 在调用 `playwright install chromium` 前，按以下顺序探测可用镜像：

1. `https://npmmirror.com/mirrors/playwright`（淘宝）
2. `https://playwright.azureedge.net`（官方，作为兜底）

通过 `requests.head()` 探测 200 ms 内能否响应，命中则设 `PLAYWRIGHT_DOWNLOAD_HOST` 环境变量。
如全部失败 → 抛 `ChromiumMirrorUnreachable`，提示用户手动 `playwright install chromium`。

### session 失效判定

`refresh` 流程：

1. headless 用 storage_state 启动浏览器
2. 跳 AutoPanel URL，等待请求拦截到 auth headers
3. **判定标准**：
   - 跳转回登录页（URL 含 `/login`）→ `SessionDead`
   - 30s 内没抓到任何 `/autopanel/v1/*` 请求 → `SessionDead`
   - 抓到 401 响应 → `SessionDead`
4. `SessionDead` → 抛异常 → CLI 提示用户跑 `kuake refresh`（headed 模式重扫码）

### doctor 检查项

| # | 检查 | 通过判据 | 失败提示 |
|---|---|---|---|
| 1 | 配置文件存在 | `~/.kuake/config.toml` + `credentials.toml` 都存在 | "未配置，请先跑 kuake init" |
| 2 | TOML 可解析 | 解析无异常 | "配置文件损坏，建议 kuake reset" |
| 3 | 本地备份目录可写 | `os.access(dir, W_OK)` | 报路径 |
| 4 | 网络可达夸克 | `requests.head('https://pan.quark.cn', timeout=5)` | "夸克网盘无法访问，检查网络/代理" |
| 5 | 网络可达 AutoPanel | `requests.head(panel.base, timeout=5)` | 同上 |
| 6 | AutoPanel token 未过期 | `panel.workdir()` 跑通 | "token 过期，将自动 refresh" |
| 7 | SSH 连通 | paramiko 连一次 `whoami` | 报具体错误 |
| 8 | 服务器磁盘 | `df -h /root/autodl-tmp` 剩余 >1GB | "服务器磁盘不足" |
| 9 | 服务器 unzip | `which unzip` 或 `python3 -c "import zipfile"` | "无解压工具，将用兜底方案" |
| 10 | Playwright Chromium 已装 | 检测 `~/.cache/ms-playwright/` | "尚未安装，init 时自动装" |
| 11 | storage_state 有效 | 解析 JSON 且非空 | "登录态失效，重跑 init/refresh" |
| 12 | 锁未占用 | 试探性 acquire 再 release | "另一个 kuake 进程在跑" |

doctor 返回 0=全过、1=有警告（黄色）、2=有错误（红色）。

### 文件锁粒度

`~/.kuake/.lock` 是**整个工具的进程互斥锁**——同一时刻最多一个 `kuake` 命令在跑。
理由：v1 单 profile，不需要细粒度；多任务并行属 v1.5。

实现：
- Windows：`msvcrt.locking()` + atexit 释放
- macOS：`fcntl.flock(LOCK_EX | LOCK_NB)`
- 获取失败立刻退出，exit 7

### TOML 原子写

```python
def atomic_write(path: Path, data: dict):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(tomli_w.dumps(data).encode('utf-8'))
    tmp.replace(path)        # Posix/Windows 都原子
    if sys.platform == 'darwin':
        path.chmod(0o600)
    elif sys.platform == 'win32':
        subprocess.run(['icacls', str(path), '/inheritance:r',
                        '/grant:r', f'{getpass.getuser()}:(R,W)'],
                       check=False)
```

### Smoke test 失败诊断逻辑

`browser/smoke_test.py` 等 60s 云端可见：

```
若 60s 后云端找不到 temp 文件：
  case A: 本地备份目录里 temp.zip 还在     → 客户端没在跑或没监听该目录
  case B: 本地 temp.zip 已被客户端取走但云端没有 → 客户端在跑但备份功能未开启该目录
  case C: 时间戳 < 1 min 内本地客户端进程不存在 → 客户端未启动
按 case 输出不同 hint
```

---

## 11. 发布流程

1. `pyproject.toml` 配置 build-system = hatchling
2. GitHub Actions：push tag `v*` → 跑测试 → build → 推 PyPI
3. README 头条放：
   - 一行安装：`pip install kuake-pipe`
   - 一行启动：`kuake init`
   - 国内镜像 fallback 命令
   - 夸克客户端配置截图

---

## 12. 非目标（v1 明确不做）

- Linux 支持（夸克无客户端）
- 多 profile 并发（v1.5）
- AutoDL 实例开关机（超出"上传"范畴）
- 加密凭据（明文 + ACL 足够）
- 交互式 push 向导（CLI 参数即可）
- 上传到 Quark Web API（仅夸克客户端备份路径）
- 服务器侧的复杂后处理（仅解压）

---

## 13. 风险与缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| AutoDL 控制台 DOM 改版 | 中 | 多层 fallback selector + fixtures 监控 |
| 夸克网盘 DOM 改版 | 中 | 同上 |
| Playwright Chromium 镜像失效 | 低 | README 提供多镜像 fallback |
| 夸克客户端弃用「备份」功能 | 低 | smoke test 早期发现，README 给替代方案 |
| AutoPanel API 变更 | 低 | 集中在 panel_api.py，易热修 |
| 用户公司网络阻断 | 中 | doctor 命令明确诊断 |
