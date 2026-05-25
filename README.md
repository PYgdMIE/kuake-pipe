# kuake-pipe

> 本地数据 → 夸克网盘 → AutoDL 服务器 全自动中转,顺带抢卡。零硬编码、凭据自动抓取、过期自动重登。

[![Tests](https://github.com/pymie/kuake-pipe/actions/workflows/test.yml/badge.svg)](https://github.com/pymie/kuake-pipe/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.0-blue)](CHANGELOG.md)

**支持平台**: Windows、macOS · **不支持**: Linux(夸克无客户端)

---

## 这是什么

如果你也在 AutoDL 上跑训练、用夸克网盘当数据中转,那这个工具是给你的。

旧痛点:
- AutoDL 实例换一台就要改 SSH 信息
- AutoPanel 鉴权头每月 F12 抓一次
- 整套配置散在多个文件,新机器要重新折腾
- 想"抢卡"还得自己刷网页

`kuake-pipe` 把这些都自动化:

```bash
pip install kuake-pipe
kuake init           # 一次性扫码登录,全部自动抓
kuake push myd ./data  # 之后只这一条
kuake grab           # 实时盯 GPU 空位,看到立刻提醒
```

---

## 工作原理

```
       ┌──────────┐                ┌────────────┐                ┌──────────────┐
       │  本地     │ ① 打包 zip      │  夸克 PC   │ ② 客户端备份    │  夸克云盘    │
       │  ./data  │ ────────────▶  │  客户端    │ ─────────────▶ │              │
       └──────────┘                │ (你已装)   │                └──────┬───────┘
                                   └────────────┘                       │
                                                                        │ ③ AutoPanel 下载
                                                                        ▼
                                                                ┌──────────────┐
                                                                │  AutoDL      │
                                                                │  服务器       │ ④ SSH 解压
                                                                │  实例         │ ───→ 完成
                                                                └──────────────┘
```

`kuake push` 一条命令依次走完四个阶段。**鉴权全部自动**:登录态过期 → 用保存的密码哈希重新登录 → 继续。

---

## 安装

```bash
pip install kuake-pipe
```

如果国内安装 Playwright Chromium 慢, `kuake init` 会**自动选淘宝镜像**;手动控制:
```bash
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright python -m playwright install chromium
```

---

## 前置条件

1. **Python 3.9+**
2. **夸克 PC 客户端** 已装并开启「备份」功能,目标本地目录如 `~/Downloads/UPLOAD/`
   - Win/Mac 下载: https://pan.quark.cn/download
3. **AutoDL 账号** 至少有一台开机的实例
4. **AutoPanel 独立密码** 已在 AutoDL 控制台「自定义服务」里设(纯数字也行)

---

## 首次配置 (`kuake init`)

```bash
kuake init
```

实际经历 1-3 分钟:

1. 自动下载 Playwright Chromium(国内镜像)
2. 弹出浏览器,跳到**微信扫码大 QR 页**(自动跳两次 tab,不用你点)
3. 你扫码登录 AutoDL → 自动列实例 → 默认选第一个运行中的
4. 自动抓 SSH 信息(剪贴板)和 AutoPanel URL
5. 浏览器跳到 AutoPanel → **你输独立密码**(只这一次手动)
6. 浏览器跳夸克网盘 → 你扫码登录夸克(只这一次手动)
7. 自动拿夸克 cookie → POST 到 AutoPanel 完成 Quark 绑定
8. 列 `/我的备份/` 子目录(走 AutoPanel API,不靠抓页面)→ 你选 PC 客户端备份的目录
9. SSH 测连接,smoke test 验证夸克客户端真在同步
10. 写盘 `~/.kuake/` 完事

之后每次 `kuake push <task> <src>` 就只是一条命令。

---

## 命令速查

```bash
# 主流程
kuake init                            # 首次配置 / 重新登录
kuake push <task> <src>               # 完整传输
kuake push <task> <src> --no-unzip    # 只下载不解压
kuake retry <task>                    # 跳过打包,用已有 UPLOAD/<task>.zip
kuake refresh                         # 手动刷 AutoPanel session

# 服务器侧
kuake doctor                          # 12 项全链路自检
kuake ls                              # 列远端 /root/autodl-tmp/
kuake rm <task>                       # 删远端 + 本地 zip

# AutoDL 实例管理 (v0.2+)
kuake instances                       # 列所有实例 + 状态色标
kuake start [N]                       # 开机第 N 号(默认第一台运行中的)
kuake stop  [N] [-y]                  # 关机第 N 号

# 抢卡 (v0.3+)
kuake grab                            # 任何卡有空闲都报
kuake grab --gpu "RTX 5090"           # 只盯 RTX 5090
kuake grab --gpu "RTX 5090" --auto-create  # 看到就买(扣费!)

# 重置
kuake reset                           # 清 ~/.kuake/
kuake reset --keep-credentials        # 仅清 config,留登录态
```

### 自动重登

`kuake init` 时如果你**新登录了 AutoPanel**(还没缓存 session),工具会监听 sign_in 请求保存密码哈希。

之后 token 过期时 `kuake push` 会自动:
1. 检测到 `AuthFailed` / `expired`
2. 用保存的哈希 `POST /sign_in` 拿新 session
3. 重试原请求

如果 init 时 AutoPanel 已经登录(缓存 session 在),没机会抓 sign_in 哈希。工具会警告:`refresh 将无法自动重登,需重跑 init`。

### 安装初始化时跳过 smoke test

```bash
kuake init --no-smoke
```

适合你确认夸克 PC 客户端配置一致只想快速做完 init 的场景。

---

## 国内网络

工具默认从淘宝镜像下载 Chromium:

```
https://npmmirror.com/mirrors/playwright
```

走代理 (API 调用):

```bash
export HTTPS_PROXY=http://127.0.0.1:7890
kuake doctor
```

---

## 故障速查

| 症状 | 原因 | 修 |
|---|---|---|
| `kuake push` 在 stage 2 卡死 | 夸克客户端未运行/未同步 UPLOAD 目录 | 客户端「设置→备份」检查目录列表 |
| `AUTH_EXPIRED` 后报 `kuake refresh` 也没救 | 没保存密码哈希(init 时已是登录态) | `kuake init` 重新走一遍 |
| `SESSION_DEAD` | session 失效且哈希缺 | 同上 |
| `SCRAPER_FAILED: No instances detected` | AutoDL 控制台 DOM 改了 | 编辑 [`src/kuake/browser/selectors.py`](src/kuake/browser/selectors.py) 添加 selector |
| `所有实例都已关机` | 字面意思 | 去 AutoDL 控制台开机,或用 `kuake start N` |
| `代号 codeInvalidRequestParams: 网盘不存在` | AutoPanel 没绑定 Quark | `kuake init` 重新跑(会自动绑定) |
| Chromium 下载卡死 | 国内网络 | 见上文国内网络 |

更多详见 [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)

---

## 凭据存储

```
~/.kuake/
├── config.toml              # 非敏感(host/port/路径)
├── credentials.toml         # 敏感(0600/icacls 加固),含:
│   ├── ssh password 或 key 路径
│   ├── AutoPanel session token
│   ├── AutoPanel 独立密码 SHA1 (用于自动 refresh)
│   └── 夸克 Cookie (用于 re-bind)
├── id_ed25519               # SSH 密钥(可选模式)
├── state/storage_state.json # Playwright session
└── .lock                    # 进程互斥锁
```

环境变量 `KUAKE_HOME` 覆盖根目录(多 profile 临时方案):

```bash
KUAKE_HOME=~/.kuake-prod kuake init
KUAKE_HOME=~/.kuake-dev  kuake init
```

---

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 通用错误 |
| 2 | 用户输入 / 参数错误 |
| 3 | 认证失败(token 死了) |
| 4 | 网络不可达 |
| 5 | SSH 错误 |
| 6 | 夸克云端同步超时 |
| 7 | 并发锁占用 |
| 130 | Ctrl+C |

---

## 开发

```bash
git clone https://github.com/pymie/kuake-pipe
cd kuake-pipe
pip install -e ".[dev]"
pytest -v
```

90+ 单测覆盖核心逻辑(pack / panel_api / config / selectors fallback / EOF handling)。

DOM-依赖的部分(scraper 命中 AutoDL/夸克页面)用 [`docs/MANUAL_TEST.md`](docs/MANUAL_TEST.md) 的人工 checklist 验证。

### Selector 维护

AutoDL 或夸克页面改版,scraper 会失效。修复点集中在 [`src/kuake/browser/selectors.py`](src/kuake/browser/selectors.py)。每个 `SelectorSet` 有多个 fallback 策略,加一条新的策略就能恢复。

欢迎 PR 添加 fallback。详见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

---

## 已知限制

- **smoke test 留 1KB 测试文件在云端**:删除 API 没探到,要手动到 quark 网盘里清
- **session 自动恢复 2s 检测略激进**:偶尔需重扫码
- **macOS 未在物理机验证**:代码兼容但首次跑可能有 path / Gatekeeper 小坑
- **多 profile**:目前用 `KUAKE_HOME` 环境变量切换,v0.4 计划做内建支持
- **`kuake stop` 慎用**:误关运行中的训练实例无法挽回

---

## License

MIT
