# Changelog

All notable changes to kuake-pipe are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Pending verification
- Real-account E2E pass against current AutoDL + Quark DOM (see `docs/MANUAL_TEST.md`)
- PyPI publishing
- GitHub Actions CI activation after first push to remote

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

### Test infrastructure
- 67 tests passing (unit + mock integration via requests-mock)
- Coverage: foundation modules 85-100%, domain modules 53-75%

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

[Unreleased]: https://github.com/pymie/kuake-pipe/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/pymie/kuake-pipe/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/pymie/kuake-pipe/releases/tag/v0.1.0
