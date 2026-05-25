# kuake-pipe

> 本地 → 夸克网盘 → AutoDL 服务器 全自动数据中转。零硬编码,凭据自动抓取,过期自动刷新。

[![Tests](https://img.shields.io/badge/tests-67%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

**支持平台**: Windows、macOS  (Linux 上夸克网盘无客户端,暂不支持)

---

## 一行安装

```bash
pip install kuake-pipe
kuake init
```

`kuake init` 会自动:

1. 下载 Playwright Chromium(自动选国内镜像)
2. 弹出浏览器,你扫码登录 AutoDL 和 夸克网盘 一次
3. 抓取所有 SSH 信息、AutoPanel token、备份路径
4. 跑一次 smoke test 验证链路

之后:

```bash
kuake push my-dataset ./data
```

完。本地 zip 打包 → 夸克客户端上行 → AutoPanel 下发 → 服务器解压。**0 手动操作**。

---

## 前置条件

1. **Python 3.9+**
2. **夸克 PC 客户端 已安装并开启「备份」**(指向某个本地目录,如 `~/Downloads/UPLOAD`)
   - Win/Mac 下载: https://pan.quark.cn/download
3. **AutoDL 实例已开机**(kuake 不会替你开机)

---

## 命令速查

```bash
kuake init                            # 首次配置向导
kuake init --no-smoke                 #   跳过末尾上传验证
kuake init --ssh-key                  #   强制密钥模式

kuake push <task> <src>               # 完整流程
kuake push <task> <src> --no-unzip    #   只下载不解压
kuake push <task> <src> --keep-zip    #   保留本地 zip

kuake retry <task>                    # 跳过打包,用已有 UPLOAD/<task>.zip

kuake refresh                         # 强制刷 panel token
kuake doctor                          # 全链路自检 (12 项)
kuake ls                              # 远端任务列表
kuake rm <task>                       # 删除远端 + 本地 zip
kuake reset                           # 清空 ~/.kuake/
kuake reset --keep-credentials        #   仅清 config 不清登录态
```

---

## 工作原理

```
┌─────────────────┐                                    ┌──────────────────┐
│  本地 ./data    │                                    │  AutoDL 服务器   │
└────────┬────────┘                                    │  /root/autodl-   │
         │ kuake push                                  │      tmp/<task>/ │
         ▼                                             └────────▲─────────┘
┌─────────────────┐    备份同步      ┌──────────┐  HTTP API     │
│  本地 UPLOAD/   │ ───────────────▶│  夸克云  │ ──────────────┘
│  <task>.zip     │  (夸克PC客户端) │   端     │  (AutoPanel)
└─────────────────┘                  └──────────┘
```

kuake 包揽:
- **本地 zip 打包** (stage 1)
- **轮询夸克云端可见性** (stage 2)
- **触发 AutoPanel 下载** (stage 3)
- **SSH 进服务器解压** (stage 4)

凭据通过 Playwright 自动捕获,过期自动 headless 刷新。

---

## 国内网络

`kuake init` 默认从淘宝镜像下载 Chromium。如自动选择失败,手动:

```bash
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright python -m playwright install chromium
```

对 API 走代理:

```bash
export HTTPS_PROXY=http://127.0.0.1:7890
kuake doctor
```

---

## 故障速查

| 症状 | 原因 | 操作 |
|---|---|---|
| `kuake push` 卡在 stage 2「等夸克客户端上行」 | 夸克客户端未运行 / 未开备份 / 备份目录不匹配 | 检查夸克 PC 客户端,运行 `kuake doctor` |
| `AUTH_EXPIRED` | panel token 过期且自动刷新失败 | `kuake refresh`(headed 模式) |
| `SESSION_DEAD` | 登录态彻底过期 | `kuake init` 重新登 |
| `SCRAPER_FAILED` | AutoDL/夸克页面 DOM 改版 | 提 issue,临时方案手动编辑 `~/.kuake/config.toml` |
| Chromium 下载卡死 | 国内网络 | 见上文国内网络段 |

更多见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

---

## 安全说明

- 凭据存放在 `~/.kuake/credentials.toml`
- POSIX 上 `chmod 600`,Windows 上 `icacls` 限制为当前用户
- 推荐使用 SSH 密钥模式(`kuake init --ssh-key`),避免密码明文
- 没有任何凭据上行到第三方服务

---

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 通用错误 |
| 2 | 用户输入错误 |
| 3 | 认证错误 |
| 4 | 网络错误 |
| 5 | SSH 错误 |
| 6 | 云端同步超时 |
| 7 | 并发锁占用 |
| 130 | 用户 Ctrl+C |

---

## 配置文件位置

```
~/.kuake/
├── config.toml              # 非敏感(host/port/路径)
├── credentials.toml         # 敏感(0600/icacls)
├── id_ed25519               # SSH 私钥(密钥模式)
├── state/
│   └── storage_state.json   # Playwright session
└── .lock                    # 进程互斥锁
```

环境变量 `KUAKE_HOME` 可覆盖根目录(用于测试或多用户隔离)。

---

## 开发

```bash
git clone <repo>
cd kuake-pipe
pip install -e ".[dev]"
pytest -v
```

详情见 [docs/specs/2026-05-25-kuake-pipe-design.md](docs/specs/2026-05-25-kuake-pipe-design.md)

---

## 贡献

DOM 抓取的 selectors 集中在 [`src/kuake/browser/selectors.py`](src/kuake/browser/selectors.py)。
夸克/AutoDL 页面改版时,只需在这里加一条 fallback strategy 即可恢复。

---

## License

MIT — see [LICENSE](LICENSE)
