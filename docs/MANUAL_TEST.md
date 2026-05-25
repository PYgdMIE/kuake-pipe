# Manual E2E Test Checklist

Run these against a real AutoDL instance + real Quark account before tagging a release.
Automated unit/mock tests cover the protocol layer; this file covers DOM + network behaviour.

## Setup

- [ ] 全新虚拟环境
  ```bash
  python -m venv .venv
  source .venv/bin/activate  # or .venv\Scripts\Activate.ps1 on Windows
  ```
- [ ] `pip install -e ".[dev]"`
- [ ] 删 `~/.kuake/` 模拟全新用户
  ```bash
  rm -rf ~/.kuake  # or rd /s /q %USERPROFILE%\.kuake
  ```
- [ ] 关闭夸克客户端的备份功能(或换一个目录),用于 smoke test 失败诊断

---

## T1: `kuake init` 全流程

- [ ] `kuake init`
- [ ] Playwright Chromium 自动从国内镜像下载
- [ ] 浏览器弹出 AutoDL 登录页
- [ ] 扫码后自动跳转到实例列表
- [ ] CLI 列出实例并提问选择(默认 1)
- [ ] 自动抓取 SSH 信息(host/port/user/password)显示正确
- [ ] CLI 询问 SSH 模式 → 选 "y" 密钥模式
- [ ] 自动生成 `~/.kuake/id_ed25519` 并上传公钥到服务器
- [ ] 后续 `ssh -i ~/.kuake/id_ed25519 -p <port> root@<host>` 可以无密码连上
- [ ] 浏览器跳 AutoPanel,自动抓取鉴权头(无 401)
- [ ] 跳夸克网盘,扫码登录
- [ ] CLI 列备份目录并提问选择
- [ ] CLI 询问子目录名(默认 UPLOAD)
- [ ] 测 SSH 显示 whoami / df
- [ ] config.toml + credentials.toml 写入正确
  ```bash
  cat ~/.kuake/config.toml
  cat ~/.kuake/credentials.toml
  ```
- [ ] storage_state.json 存在且 > 1KB
- [ ] smoke test 通过 → 看到 "夸克客户端同步链路畅通"
- [ ] 凭据文件权限正确
  - Mac/Linux: `ls -la ~/.kuake/credentials.toml` 显示 `-rw-------`
  - Win: `icacls %USERPROFILE%\.kuake\credentials.toml` 仅显示当前用户

---

## T2: smoke test 失败诊断

- [ ] 在夸克客户端里关闭「备份」开关
- [ ] `kuake init` (从头跑一遍)
- [ ] smoke test 60s 超时
- [ ] 看到 "夸克客户端同步链路异常" + "未运行/未开备份" 诊断
- [ ] 重新开启「备份」并 `kuake init` 一次,验证恢复

---

## T3: `kuake push` 主流程

- [ ] 准备测试数据
  ```bash
  mkdir test-data
  echo "hello world" > test-data/file.txt
  mkdir test-data/sub
  echo "x" > test-data/sub/y.txt
  ```
- [ ] `kuake push smoke ./test-data`
- [ ] [1/4] 打包显示 spinner
- [ ] [2/4] 显示等夸克客户端上行
- [ ] [3/4] 显示 AutoPanel 下载
- [ ] [4/4] 显示服务器解压
- [ ] 服务器侧验证
  ```bash
  ssh root@<host> "ls -la /root/autodl-tmp/smoke/"
  ```
  应该看到 `file.txt` 和 `sub/y.txt`

---

## T4: `kuake retry`

- [ ] 立刻再跑 `kuake retry smoke` (UPLOAD/smoke.zip 还在)
- [ ] [0] 跳过打包,直接走 stage 2-4
- [ ] 完成

---

## T5: 自动 refresh

- [ ] 手动破坏 token
  ```bash
  # 编辑 ~/.kuake/credentials.toml,把 panel.authorization 改成 "Bearer broken"
  ```
- [ ] `kuake push test2 ./test-data`
- [ ] 应该看到 stage 2 期间触发 refresh(可能开一瞬间 headless 浏览器)
- [ ] refresh 成功后 push 继续完成

---

## T6: `kuake doctor`

- [ ] `kuake doctor`
- [ ] 12 项全部显示 ✓ (绿色)
- [ ] 退出码 0

破坏后再跑:

- [ ] 关掉网络/拔网线
- [ ] `kuake doctor` 应该 [4/12] [5/12] 失败
- [ ] 退出码 2

---

## T7: 错误路径

- [ ] `kuake push bad/task ./test-data` → exit 2 (USER_INPUT) + 中文错误信息
- [ ] `kuake push noexist ./does-not-exist` → exit 2
- [ ] `kuake refresh` 时改坏 storage_state → exit 3 (SESSION_DEAD)

---

## T8: 并发锁

终端 A:
```bash
kuake push longtask ./large-data    # 选个大文件让它跑久点
```

终端 B (同时):
```bash
kuake push other ./small
```

- [ ] 终端 B 应该立即 exit 7 (CONCURRENCY_LOCK) + 提示

---

## T9: `kuake ls` / `kuake rm`

- [ ] `kuake ls`
- [ ] 看到 `/root/autodl-tmp/smoke/` 等目录
- [ ] `kuake rm smoke` (确认 y)
- [ ] 远端 + 本地 zip 都删
- [ ] `kuake ls` 不再有 smoke

---

## T10: 清理

- [ ] `kuake reset` → 弹确认 → 输 y
- [ ] `~/.kuake/` 清空
- [ ] 再 `kuake doctor` → CONFIG_MISSING

---

## T11: 跨平台

至少在 **两个平台** 跑一遍 T1-T3:

- [ ] Windows 11
- [ ] macOS Sonoma+

中文路径(用户名/备份目录含中文)在 Windows 跑一次:

- [ ] 用 `C:\Users\张三\Downloads\备份\` 作为本地备份目录
- [ ] init + push 都正常,无乱码

---

## 发布前检查

- [ ] `pytest` 全过(应 67+ 通过)
- [ ] `python -m build --wheel` 出 wheel
- [ ] 全新 venv 装 wheel,`kuake --help` 正常
- [ ] Tag `v0.1.0`,推 PyPI
