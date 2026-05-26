# Changelog

All notable changes to kuake-pipe are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/).

## [0.6.0] — 2026-05-26

**主线**: 产品级硬化 — Web UI auth/CSRF + CC/Codex 编排稳定性 + PyPI/Docker 发版自动化 + 长跑健壮性。

### Added

#### 🟠 安全 (默认行为)
- **`kuake serve` token 认证默认 ON** — 启动 `secrets.token_urlsafe(24)` 生成随机 token, URL 自带 `?token=`, 同时支持 HttpOnly cookie + `X-Kuake-Token` header 三种入口
- **CSRF Origin 校验** — POST/PUT/DELETE 有 Origin 时必须 same-origin, 无 Origin (curl/程序) 放行
- **`kuake serve --no-auth`** — 显式关闭 (本机使用可); `--host 0.0.0.0 + --no-auth` 同时用会 warn

#### 🟡 CC / Codex 自动化稳定性
- **`--json` 输出模式** — 5 个命令 (`instances` / `whoami` / `wait-running` / `grab` / `auto`) 支持。rich 噪音切 stderr, stdout 仅 JSON。`auto --json` 用 try/except 包链路, 成功/失败都 emit `{success, stage_reached, new_uuid, ...}`
- **`kuake status` 命令** — 外部查 jobs 状态。列最近 N / 单 job 详情 / `--only-running` 过滤 / `--json`。 启动时 sweep_stale 自动把 PID 死的 running 标 interrupted
- **`kuake auto --fail-rollback`** — 链中失败 (在 created 之后) → 自动 `kuake stop <new_uuid> -y` 防扣费;不 release (避免误删数据);rollback 结果写入 JSON 输出 `{rollback_attempted, rollback_ok}`
- **`kuake init --headless` 预检** — `list_instances(page_size=1)` ping JWT, 过期立即 raise UserInputError 引导重扫, 不卡 headless QR 页
- **Windows cancel 用 CTRL_BREAK_EVENT** — `_spawn_job` 加 `CREATE_NEW_PROCESS_GROUP`, cancel 时 `send_signal(CTRL_BREAK_EVENT)`, 子进程的 finally 块 (SSH 断连 / FileLock 释放 / 临时 zip 删除) 有机会跑;3s timeout 后才硬 kill

#### 🟢 长跑健壮性
- **Job log rotation** — `JobStore.prune_old(keep_count=100, max_age_days=14)`; `kuake serve` 启动时调; 进行中的 job (status=running) 永不删
- **Config schema 校验** — `validate_config` / `validate_credentials` 在 `read_*` 后调;检查 host/user 非空 / port 范围 / auth_mode 取值 / panel_base http(s):// / 云端 + 远端路径必须绝对 / SSH 凭据至少一种;多错一次报全

#### 📦 发版自动化
- **`.github/workflows/release.yml`** — tag `v*.*.*` 触发 4 个 job:
  - build sdist + wheel
  - publish PyPI (OIDC trusted publishing, 不需要 API token secret)
  - publish ghcr.io Docker image (`latest` + `<version>` 双 tag)
  - GitHub Release with extracted CHANGELOG section
- **Dockerfile + .dockerignore** — `python:3.12-slim` + Chromium 运行时依赖 + `fonts-noto-cjk`; `pip install . && playwright install chromium`; `ENTRYPOINT=kuake`, 挂载 `~/.kuake` 即可用

### Changed

- `kuake serve` 默认启用 token 认证 (老的零 auth 行为需显式加 `--no-auth`)
- `_detect_stage` 返回 `(n, total)` 而非 `int`, SSE event:stage 携带 total (前端按 4/5 算进度百分比)
- `_spawn_job` 公共助手抽出 push 和 auto 共享的 runner + 队列 + cancel 逻辑

### 测试

- 33 个新单测 (Round 2 + 3 + 4 加起来):
  - server auth/CSRF 11
  - --json + status + fail-rollback + headless 16
  - config validation + prune 17 - 1 已有 = 17 新
- 总 **284 / 284 测试通过 + ruff 干净**

### 发布渠道 (用户侧一次性配置)

- **PyPI**: 在 https://pypi.org/manage/account/publishing/ 配 trusted publisher (project=`kuake-pipe`, workflow=`release.yml`, environment=`pypi`)
- **GHCR Docker**: 自动, push tag 即发到 `ghcr.io/PYgdMIE/kuake-pipe:0.6.0`

---

## [0.5.0] — 2026-05-26

**主线**: 加 Web UI (`kuake serve`) + 端到端自动化 (`kuake auto`),让工具从「CLI 给老手」升级到「点选 + AI 编排」都行。

### Added

#### Web UI (`kuake serve`)
- 本地 Flask server (默认 `127.0.0.1:8765`), 启动自动开浏览器, vanilla JS 单页 + editorial dark theme
- **三个 tab**:
  - **抢卡** — 实时市场监督 + 详情可展开行 (CPU/内存/GPU 显存/磁盘/CUDA/驱动/OS) + 三级镜像选择器 (Framework → Version → Python → CUDA, 5 个预置框架) + 区域 chips 多选 + 轮询间隔可调 (3/5/10/30s) + 失败退避 + JWT 过期专项提示 + 模态 `YES` 输入门
  - **上传** — 后端 tkinter 原生文件/目录选择器 + `--no-unzip` / `--keep-zip` toggle + 取消运行中 (terminate 子进程) + 4 阶段进度条 (打包/上传/AutoPanel/SSH) + 历史 job 一键重试 + 远端文件面板 (kuake ls/rm) + 完成桌面通知
  - **全自动** — 完整表单 + 5 阶段进度条 + `stop-after` (create/ready/init/push) + 启动前 confirm 防误操作
- **Job 持久化**: 状态落 `~/.kuake/jobs/<id>.json` + log 文件, 浏览器刷新/重启 server 后 SSE 自动重连仍在跑的任务
- **15 个 REST 路由**: `/api/market` `/instances` `/grab-plan` `/clone-plan` `/confirm-create` `/push-start` `/auto-start` `/push-cancel/<id>` `/push-stream/<id>` `/jobs[/<id>]` `/pick-path` `/remote/ls` `/remote/rm` `/image-presets`

#### 端到端自动化 (CC / Codex CLI 编排)
- **`kuake auto`** — `grab → confirm-create → wait → init → push` 一条命令跑完, 5 个阶段任一失败 raise + 非零退出
  - `--stop-after create|ready|init|push` 4 个挡位
  - `--gpu` / `--region` / `--gpu-count` / `--expand-data-disk` / `--system-disk-expand` / `--image` / `--max-market-iter` / `--ready-timeout` / `--autopanel-password` / `--cloud-dir` / `--task` / `--src` / `--no-unzip` / `--keep-zip` 全 flag 化
- **`kuake wait-running <target>`** — 阻塞到 `status=running`, target 支持 uuid / 1-based 索引 / uuid 前缀
- **`kuake confirm-create --yes`** — 跳过 stdin `YES` 等待, 3s grace + Ctrl+C 抢救 (CC/Codex 用)
- **`kuake init --headless`** — 浏览器无头模式 (要求 `storage_state` 已存在), `kuake auto` 第 4 步自动加, 实现真正零界面端到端
- `AutoDLClient.wait_until_running(uuid, timeout, poll, progress_cb)` — 状态变化时 callback, 不刷屏

### Changed

#### 关键 bug 修复
- **`payg_price` 单位修正** (×10 偏差) — 之前按"分"(0.01 元) 算, 实际是"厘"(0.001 元):
  - 修复前 RTX 3080 Ti 显示 `¥10.30/h`, 实际 `¥1.03/h`
  - `/100` → `/1000`, 6 处测试 fixture 同步更新 (`2900` → `29000`)
- **`confirm-create` payload schema 重写** — v0.4 自承"从未真账号触发", 实测时 AutoDL 返回 `RequestParameterIsWrong`:
  - 用 Playwright `route.abort()` 截获真实 POST body (`scripts/probe_create_intercept.py`)
  - 修 6 处差异: `expand_data_disk` 是字节不是 GB, `cg_application_info` 4 子字段 (多 `current_version_id` / `image_id`), 新增 `instance_name` / `reproduction_id`, `coupon_id_list` / `duration` / `num` 拆到顶层 `price_info`, `system_disk_change_size` 只在非零时发送
  - **真账号验证**: TITAN Xp `uuid 1c0641804d-11a4d915` + clone +100G `uuid 83d14ab034-84782557` 都跑通

### Fixed
- Web UI 镜像选择器点 option 后自动收起 (renderImagePopup 重建 innerHTML 后 click 冒泡误判"点外面")
- Web UI 镜像选择器 popup 排版 (display: block 覆盖 flex 导致列纵向堆叠)
- Web UI 选择 GPU 型号后不自动刷新市场 (filter change 没 handler)

### 实地验证 + 测试
- **真账号 E2E** 跑通: confirm-create 真下单 (¥0.52/h TITAN Xp), clone + 100G 数据盘真下单, 全程零卡死
- **240/240 单元测试通过 + ruff 干净**, 含 server 路由 38 个 + auto chain 18 个 + 镜像/分阶段检测/cancel/远程文件等

### Roadmap (v0.6+)
- Web UI token auth + CSRF 防护
- `--json` 输出模式 (CC/Codex 解析友好)
- `kuake status` 命令外部查询
- `kuake auto --fail-rollback` 失败时自动 stop 实例
- Multi-profile native support (currently via `KUAKE_HOME`)
- Quark cloud delete endpoint (cleanup uploaded smoke / push files)
- True parallel multipart upload (compute incremental `x-oss-hash-ctx`)
- Resume-on-failure for uploads (persist `upload_id` + `etags`)
- 阿里云盘 (Aliyun pan) 作为 Quark 之外的备选上传后端
- PyPI publishing automation via GitHub Actions

---

## [0.4.0] — 2026-05-26

**Breaking**: 砍掉夸克 PC 客户端「备份」功能依赖,改用 cookie 鉴权的直接 Quark Cloud API 上传。Linux / headless / CI 环境现在都能跑。

### Added

- **`kuake/quark_uploader.py`** — 纯 HTTP 直接上传到 Quark Cloud
  - 协议逆向自 pan.quark.cn 网页版(2026-05),上传走 `{bucket}.pds.quark.cn`(原 `quarkpan` 库 hardcode 的 `oss-cn-shenzhen.aliyuncs.com` 已失效)
  - 支持单分片(<5MB)和多分片(>=5MB,4MB 块)路径
  - 秒传检测(MD5+SHA1)
  - 自动创建云端目标目录(`resolve_or_create_folder`)
- 9 个新单测(`tests/test_quark_uploader.py`)覆盖正常路径 + 失败注入 + endpoint 回归测试

### Changed

- **`kuake init` 全自动化 flags** — 除两次 QR 扫码外,其它步骤都能脚本化:
  - `--instance N` 跳过实例选择交互
  - `--autopanel-password PWD` 或 `KUAKE_AUTOPANEL_PASSWORD` env var,Playwright 自动填表
  - `--cloud-dir PATH` 跳过云端目录 prompt
  - `--ssh-key` 显式选密钥模式 (默认 password,不再弹 Confirm)
- **`kuake push` stage 2** 不再轮询夸克客户端同步,直接 HTTP PUT 到云端
  - 打包目录从 `local_backup_dir` 改成 `KUAKE_HOME/staging/` (自动建)
  - stage 2 失败模式从「1 小时超时」改成「立刻报错」(上传协议直接返回 HTTP 错误)
- **`kuake init`** 不再问「PC 备份目录 / 子目录 / 本地备份目录」3 个 prompt
  - 只问 1 个:云端上传目录(默认 `/kuake-uploads`)
  - smoke test 改为直接上传 1KB 文件验证 cookie 链路,不需要 GUI 客户端在跑
- **`kuake doctor`** 第 3 项从「本地备份目录可写」改成「打包暂存目录可写」(`KUAKE_HOME/staging`)
- **`kuake/platform_guard.py`** 不再拦截 Linux(夸克客户端依赖已删)
- **Config schema**: `quark.local_backup_dir` 字段废弃(保留兼容旧 config 读取,新 init 不再写出)

### Removed

- `kuake/browser/smoke_test.py` 旧版「等夸克客户端同步」逻辑(替换为直接上传验证)
- `PlatformUnsupported` 异常类不再抛出(保留 import 路径兼容)

### Fixed

- macOS / Linux 用户不再被夸克 PC 客户端「备份」功能的 GUI 设置卡住
- `kuake push` 大幅提速:不再有 stage 2 的 60s+ 轮询等待

### Migration from 0.3.x

- 旧 config 的 `quark.local_backup_dir` 字段会被静默忽略,无需手动改
- 旧 `cloud_backup_path`(`/我的备份/.../UPLOAD`)继续可用 — 新版会上传到这个路径
- 全新安装建议跑 `kuake reset --keep-credentials && kuake init` 重新走简化流程

### Tests

- 99 unit + mock 集成测试通过(原 90 + 新 9)
- 端到端验证:Quark 直接上传 protocol(单分片 / 多分片 / 秒传)在真账号上跑通

---

## [0.3.0] — 2026-05-25

This release rewrites the AutoPanel + Quark integration based on the **new auth model**
(verified against AutoPanel v6.16.0 in May 2026) and adds the GPU **抢卡** command.

### Added

- **`kuake grab`** — poll AutoDL market for available GPU/CPU machines
  - Filter by GPU type (`--gpu "RTX 5090"`), region, CPU-OK
  - Dry-run by default; `--auto-create` actually buys
- **AutoPanel sign_in chain** — POST `/autopanel/v1/sign_in` with SHA1 of standalone password
- **Quark auto-binding** — POST `/autopanel/v1/netdisk/oauth/quark` with user's Quark Cookie
- **WeChat-QR auto-redirect** — `kuake init` auto-clicks "微信扫码登录" then "微信快捷登录" to land on the larger `open.weixin.qq.com` QR page
- **`--use-system-chrome`** — launch Playwright with user's actual Chrome profile (Chrome must be closed)
- **EOF-safe prompts** — `_safe_prompt` / `_prompt_index` no longer crash on closed stdin
- **Quark backup folder via panel API** — lists `/我的备份/` subdirs through AutoPanel HTTP API (more reliable than scraping the web UI)
- **Status-aware instance display** — `kuake init` and `kuake instances` show 运行中/已关机 with color badge; init defaults to first running instance
- **doctor checks Quark binding** — verifies `netdisk_list` includes Quark fs_id

### Changed

- **`PanelClient.sign_in()`** issues sign_in API call and updates Authorization header
- **`PanelClient.bind_quark()`** wraps the cookie-binding POST
- **`PanelClient.netdisk_list()`** returns list of bound netdisks
- **Authorization header model**: now accepts the 40-char hex session token (no Bearer prefix). Pre-login Authorization is literal `"null"`.
- **`kuake refresh`** uses saved `standalone_password_sha1` + pure HTTP sign_in (no browser)
- **`refresh.run(_hold_lock=False)`** for the auto-refresh callback path inside `push` (avoids lock conflict)
- **AutoDL session reuse**: `kuake init` saves `storage_state.json` immediately after AutoDL + Quark login; subsequent inits skip QR if cookies still valid
- **AutoDL login page**: `wait_until="domcontentloaded"` + 60s timeout to avoid blocking on slow trackers

### Fixed

- **`is_expired_response`** now catches `code="AuthFailed"`, `code="NoAuth"`, and msg containing `"独立密码"` / `"请重新登录"` / `"登录已失效"` — earlier missed AutoPanel's actual error code
- **`SessionDead` propagation** — when `refresh_callback()` fails, the original `SessionDead` propagates to the CLI top, giving the correct hint (`run kuake init`) instead of misleading `kuake refresh`
- **`SESSION_DEAD.hint`** — now correctly says `kuake init` (was suggesting `kuake refresh` which had just failed)
- **Stopped instance error** — clearer message: "该实例已关机 — 请先到 AutoDL 控制台开机"
- **Quark cookies extracted from Playwright context** (not from stale `~/.quark/cookie.txt`)

### Tests

- 90 unit + mock-integration tests pass
- T1-T10 of `docs/MANUAL_TEST.md` validated against real AutoDL + Quark account
- T11 (cross-platform Mac) pending physical hardware

---

## [0.2.0] — 2026-05-25

### Added
- `kuake instances` — list AutoDL instances with power status via headless browser
- `kuake start [N]` — power on AutoDL instance N (default 1)
- `kuake stop [N] [-y]` — power off AutoDL instance N
- New module `src/kuake/browser/autodl_actions.py`
- Selectors for power on/off buttons, status, and confirmation dialog

### Test coverage
- 74/74 passing (added 7 CLI parser + target resolution tests)

---

## [0.1.0] — 2026-05-25

Initial implementation.

### Added
- Project scaffolding: pyproject.toml, src layout, MIT license, .gitignore
- 8 CLI commands: `init`, `push`, `retry`, `refresh`, `doctor`, `ls`, `rm`, `reset`
- 27 Python modules across foundation / domain / browser / commands layers

### Foundation utilities
- `errors.py` + `i18n.py` — typed exceptions with Chinese display layer
- `platform_guard.py` — Linux early-exit + Windows icacls / macOS chmod 600
- `config.py` — atomic TOML write (tmp + os.replace) with ACL hardening
- `concurrency.py` — cross-platform file lock (msvcrt / fcntl)
- `progress.py` — rich progress bars + UTF-8 stdout helper
- `proxy.py` — HTTPS_PROXY detection

### Domain modules
- `pack.py` — zip packaging + md5
- `panel_api.py` — AutoPanel HTTP client with 3-state expiry detection (401 / code / HTML) and auto-refresh hook
- `ssh_exec.py` — SSH wrapper with password/key dual-mode and three-tier unzip fallback (native unzip → apt install → python zipfile)

### Browser automation
- `browser/installer.py` — Chromium auto-install with CN mirror fallback (npmmirror first)
- `browser/session.py` — Playwright session lifecycle + storage_state atomic IO
- `browser/selectors.py` — centralized DOM selectors with multi-tier fallback strategies
- `browser/autodl_scraper.py` — AutoDL login + instance enumeration + SSH info extraction
- `browser/panel_scraper.py` — AutoPanel auth header interception
- `browser/quark_scraper.py` — Quark Pan login + backup folder enumeration
- `browser/smoke_test.py` — post-init link validation with detailed failure diagnostic

### Documentation
- README with installation, command reference, troubleshooting
- `docs/TROUBLESHOOTING.md` — symptom-cause-fix table
- `docs/MANUAL_TEST.md` — 11-section E2E checklist for human verification
- `docs/specs/2026-05-25-kuake-pipe-design.md` — full design document
- `docs/superpowers/plans/2026-05-25-kuake-pipe-v1.md` — implementation plan

### Platform
- Windows 10/11
- macOS 12+
- (Linux unsupported: Quark has no Linux client)
- Python 3.9+

[Unreleased]: https://github.com/PYgdMIE/kuake-pipe/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/PYgdMIE/kuake-pipe/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/PYgdMIE/kuake-pipe/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/PYgdMIE/kuake-pipe/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/PYgdMIE/kuake-pipe/releases/tag/v0.1.0
