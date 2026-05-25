# Changelog

All notable changes to kuake-pipe are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Roadmap
- Multi-profile native support (currently via `KUAKE_HOME`)
- Smoke test cloud cleanup (discover Quark delete endpoint)
- macOS verification on physical hardware
- Optional: direct Quark cloud upload (bypass PC client)
- PyPI publishing automation via GitHub Actions

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

[Unreleased]: https://github.com/pymie/kuake-pipe/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/pymie/kuake-pipe/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/pymie/kuake-pipe/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/pymie/kuake-pipe/releases/tag/v0.1.0
