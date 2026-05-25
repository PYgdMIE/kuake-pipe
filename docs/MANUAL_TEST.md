# Manual E2E Test Checklist (v0.3.0)

Run these against a real AutoDL instance + real Quark account before tagging a release.
Automated unit/mock tests cover the protocol layer; this file covers DOM + network behaviour.

## Pre-test setup

- [ ] Fresh venv: `python -m venv .venv && source .venv/bin/activate`
- [ ] `pip install -e ".[dev]"`
- [ ] Clear test directory: `rm -rf ~/.kuake` (or `rd /s /q %USERPROFILE%\.kuake`)
- [ ] Confirm at least one AutoDL instance is **运行中**
- [ ] Confirm Quark PC client is installed, "备份" is enabled, and targets `~/Downloads/UPLOAD`

Tip: use `KUAKE_HOME=/tmp/kuake-test` to isolate test runs from your real config.

---

## T1: `kuake init` full flow

```bash
kuake init
```

- [ ] Playwright Chromium auto-installs from npmmirror (if not present)
- [ ] Browser opens, navigates to `autodl.com/wx-login`
- [ ] **Auto-switches to QR mode** (no manual click required)
- [ ] **Auto-redirects to `open.weixin.qq.com`** (big QR page)
- [ ] You scan WeChat QR → ✓ AutoDL 已登录
- [ ] Instance list shown with **status color badge** (`运行中` green / `已关机` yellow)
- [ ] Default = first running instance
- [ ] Choose `1` → SSH info captured via clipboard (host/port/user/password)
- [ ] AutoPanel URL captured (`https://aXXX.westd.seetacloud.com:8443/?token=jupyter-...`)
- [ ] Asked SSH key mode → answer `n` for password mode
- [ ] AutoPanel page loads:
  - **First time**: shows password prompt — enter standalone password
  - **Already logged in**: monitor page directly; tool captures token automatically
- [ ] ✓ AutoPanel token captured (len=40)
- [ ] Quark page → scan QR → ✓ 夸克网盘已登录
- [ ] ✓ 抓到 Quark cookie (~1000 chars)
- [ ] First time: ✓ Quark 网盘已绑定 AutoPanel. Repeat init: ✓ 已绑定 1 个网盘,跳过绑定
- [ ] `/我的备份/` listed via panel API (not web scrape) — shows your PC backup folder
- [ ] Choose folder + subdir (default `UPLOAD`) + local dir (default `~/Downloads/UPLOAD`)
- [ ] ✓ whoami=root (SSH test)
- [ ] ✓ 配置已写入 `~/.kuake/`
- [ ] Smoke test (skip with `--no-smoke` for fast tests):
  - 1KB file written to local backup dir
  - Polls cloud for 60s
  - On success: ✓ 夸克客户端同步链路畅通
- [ ] ✓ kuake init 完成

---

## T2: smoke test failure diagnostic

Stop the Quark PC client temporarily, then:

```bash
rm -rf ~/.kuake-test && KUAKE_HOME=~/.kuake-test kuake init
```

- [ ] At smoke test step, after 60s timeout:
- [ ] ✗ 夸克客户端同步链路异常
- [ ] ! 本地 `~/.kuake-test/.../kuake_smoke_<ts>.zip` 仍在 — 客户端可能未运行,或未监听该目录
- [ ] Init still completes (warning, not error) — config is saved for later

---

## T3: `kuake push` main flow

```bash
mkdir test-data && echo "hello" > test-data/file.txt
kuake push smoke ./test-data
```

- [ ] [1/4] 打包 → `~/Downloads/UPLOAD/smoke.zip` (small size, md5 shown)
- [ ] [2/4] 等夸克客户端上行 — file appears in cloud within tens of seconds
- [ ] [3/4] 触发 AutoPanel 下载 — task_done observed
- [ ] [4/4] 服务器解压 → `/root/autodl-tmp/smoke/file.txt`
- [ ] Verify server-side:
  ```bash
  ssh root@<host> -p <port> "cat /root/autodl-tmp/smoke/file.txt"
  # → hello
  ```

---

## T4: `kuake retry`

After T3, the local zip is still in `~/Downloads/UPLOAD/smoke.zip` (unless `--keep-zip` was not set and unzip succeeded).

```bash
kuake retry smoke
```

- [ ] [0] 使用已有 ... zip
- [ ] Skips stage 1 (no repack)
- [ ] Enters stage 2 → stage 3 → stage 4
- [ ] Completes

If zip is gone: `kuake retry` reports clear error.

---

## T5: auto refresh on AuthFailed

Corrupt the panel auth in credentials.toml:

```bash
sed -i 's/authorization = ".*"/authorization = "BROKEN"/' ~/.kuake/credentials.toml
kuake push refresh-test ./test-data
```

- [ ] [2/4] reports AuthFailed
- [ ] Logs `轮询出错 (将重试):` mentioning auth issue
- [ ] If `standalone_password_sha1` is saved:
  - Auto sign_in fires, new token obtained
  - Push resumes and completes
- [ ] If sha1 missing (init was via already-logged-in AutoPanel):
  - Raises `SESSION_DEAD`
  - Hint: 运行 `kuake init` 重新扫码登录(refresh 已无能为力)

---

## T6: `kuake doctor`

```bash
kuake doctor
```

- [ ] 12/12 items all green (`✓`)
- [ ] Exit code 0
- [ ] Includes `Quark 网盘已绑定 (AutoDL_Quark)`

Break tests:

- [ ] Kill network → doctor reports `夸克网盘不可达` / `AutoPanel 不可达`
- [ ] Corrupt config → reports `配置损坏`

---

## T7: error paths

- [ ] `kuake push bad/task ./test-data` → exit 2, USER_INPUT
- [ ] `kuake push smoke ./nonexistent` → exit 2
- [ ] `kuake retry nonexistent` → exit 2, clear error
- [ ] `kuake bogus` → exit 2, argparse error
- [ ] Run `kuake` with no config → exit 1, CONFIG_MISSING
- [ ] `KUAKE_DEBUG=1 kuake <command>` prints full traceback on errors

---

## T8: concurrency lock

Terminal A:
```bash
kuake push longrun ./large-data
```

Terminal B (within same machine):
```bash
kuake push other ./small
```

- [ ] Terminal B exits immediately with code 7 (CONCURRENCY_LOCK)
- [ ] Error msg mentions 另一个 kuake 进程

---

## T9: instance lifecycle

```bash
kuake instances
```

- [ ] Lists all instances with status badge
- [ ] Each: `[N] 状态色块  区域 / 名称`

```bash
kuake start 1
```

- [ ] If target is running: no-op or quick return
- [ ] If target is stopped: clicks 开机 button, waits for status change
- [ ] ⚠️ DO NOT TEST `kuake stop` on instances you care about

---

## T10: cleanup

```bash
kuake rm smoke
```

- [ ] Confirms deletion (y/N)
- [ ] Deletes `/root/autodl-tmp/smoke/` on server
- [ ] Deletes local `~/Downloads/UPLOAD/smoke.zip`

```bash
kuake reset
```

- [ ] Asks confirmation
- [ ] Removes `~/.kuake/`

`kuake doctor` afterwards → CONFIG_MISSING.

---

## T11: cross-platform

If you have access to both Windows and macOS:

- [ ] Repeat T1 + T3 on macOS
- [ ] Check `credentials.toml` is `-rw-------` (chmod 600)
- [ ] Confirm Quark Mac client backup target works the same way

If you only have Windows: mark T11 as "skipped, Mac not tested".

---

## T12: `kuake grab` (v0.3+)

```bash
kuake grab --max-iter 3 --poll 2
```

- [ ] Polls market API every 2s
- [ ] When any GPU has `gpu_idle_num >= 1`: prints match
- [ ] `--auto-create` actually calls `/order/instance/create/payg` (don't test on real account unless you accept the bill)

---

## Pre-release checks

- [ ] `pytest` → 90+ passing
- [ ] `python -m build --wheel` → produces `dist/kuake_pipe-*.whl`
- [ ] Fresh venv install from wheel:
  ```bash
  python -m venv /tmp/kuake-fresh
  source /tmp/kuake-fresh/bin/activate
  pip install dist/kuake_pipe-0.3.0-py3-none-any.whl
  kuake --version
  kuake --help
  ```
- [ ] Tag `v0.3.0` on git
- [ ] `git push --tags`
- [ ] GitHub Release created with CHANGELOG excerpt
