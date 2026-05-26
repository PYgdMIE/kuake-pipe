# Changelog

All notable changes to kuake-pipe are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **`kuake grab` v2** — 找到匹配机器 → 生成完整 `/api/v1/order/instance/create/payg` payload → 落盘到 `~/.kuake/plans/`,**绝不下单**
  - 新选项: `--gpu-count`, `--expand-data-disk`, `--system-disk-expand`, `--image`, `--any-region`
  - 旧 `--auto-create` 行为废弃,统一改成 PLAN 模式
- **`kuake clone <source>`** — 从已有实例的 detail 提取镜像/GPU/扩容配置,在市场上找一台空闲机器生成"开同款"PLAN(dry-run)
  - 源实例可用 1-based 索引或 uuid 前缀
  - `--same-region` 限制只在源实例同区找
- **`kuake confirm-create --plan-file <p.json>`** — 唯一会真下单的入口
  - 需输入字面 `YES`(大写),其它任何输入(含 `y` / `yes`)都会取消
  - 显示扣费提示 + 单价 + 完整 plan
- **AutoDL JWT 加载** — `kuake.autodl_api.load_jwt_from_storage_state()` 从 `localStorage.token` 提取,补全旧 cookie-only 鉴权的不足
- **`kuake.autodl_planner`** — 纯 dataclass + 序列化,plan 与发送完全解耦
- **测试**: +21 个 (autodl_planner + grab + clone + confirm-create 安全门),总 143/143 通过,覆盖 53%

### Roadmap
- Multi-profile native support (currently via `KUAKE_HOME`)
- Quark cloud delete endpoint (cleanup uploaded smoke / push files)
- True parallel multipart upload (compute incremental `x-oss-hash-ctx`)
- Resume-on-failure for uploads (persist `upload_id` + `etags`)
- 阿里云盘 (Aliyun pan) 作为 Quark 之外的备选上传后端
- AutoDL 深挖: 实例克隆 API 直查 / 磁盘扩容 API / 镜像列表 / 优惠券应用
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
