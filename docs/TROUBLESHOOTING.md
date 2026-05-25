# 故障速查

## 1. `kuake push` 在 stage 2「等夸克客户端上行」卡死

最常见的问题,**不是 kuake 的 bug**。

```
· [2/4] 等夸克客户端上行 → /我的备份/来自:xxx/UPLOAD/yourtask.zip
   ...waiting (remain 3580s)
```

zip 已经落到本地 `~/Downloads/UPLOAD/` 但不上行到云端。

检查清单：

1. **夸克 PC 客户端在运行吗?**(任务栏看图标 / `tasklist | findstr Quark`)
2. **客户端「设置 → 备份」开关开了吗?**
3. **「备份目录」列表里有 `C:\Users\mie\Downloads\UPLOAD`(或你 init 时填的那个) 吗?**
4. **客户端登录的账号 == 你 `kuake init` 时扫码的账号吗?** 不同账号会导致 PC 备份到 A 账号但 AutoPanel 用 B 账号 cookie

用 panel API 直接查云端可以验证客户端是否在同步:

```bash
kuake doctor    # 应该看到 [6/12] Quark 网盘已绑定 (AutoDL_Quark)
```

如果云端能正确显示已经上传过的旧文件(`du -sh` 类的命令显示出来)而新文件传不上,通常是**客户端被暂停**或**目录列表里少了那个目录**。

---

## 2. `AUTH_EXPIRED` 报错但 `kuake refresh` 也不行

```
✗ AutoPanel token 已过期且自动刷新失败
提示: 运行 `kuake refresh` 重新扫码登录
```

通常发生在: `kuake init` 时 AutoPanel **已经处于登录态**(浏览器有 session),所以工具没机会拦截 sign_in 请求拿到密码哈希。后面 token 过期没法自动重登。

检查:

```bash
cat ~/.kuake/credentials.toml | grep standalone_password_sha1
# 如果是空 → 没保存哈希
```

解决: **`kuake init` 重跑一遍**。在跑之前清掉 AutoPanel session 让工具能拦截:

- 在浏览器里 logout AutoPanel
- 或删除 storage_state: `rm ~/.kuake/state/storage_state.json`

---

## 3. `SESSION_DEAD` / `SCRAPER_FAILED`

```
✗ 登录态彻底失效或缺保存的密码哈希
提示: 运行 `kuake init` 重新扫码登录(refresh 已无能为力)
```

`kuake init` 跑一次就好。

如果 init 也报 `SCRAPER_FAILED: No AutoDL instances detected`,说明 AutoDL 控制台页面 DOM 改了。

临时手动修复: 编辑 [`src/kuake/browser/selectors.py`](../src/kuake/browser/selectors.py),给失败的 `SelectorSet` 加一条新策略,然后:

```bash
pip install -e .       # 重新装(editable 模式)
kuake init
```

或者到 GitHub 开 issue,附浏览器 DOM 截图(F12 → Elements → 相关元素 outerHTML)。

---

## 4. Playwright Chromium 下载失败

```
✗ CHROMIUM_MIRROR_UNREACHABLE
```

工具默认从 [npmmirror 淘宝镜像](https://npmmirror.com/mirrors/playwright) 拉,如果挂了:

```bash
PLAYWRIGHT_DOWNLOAD_HOST=https://playwright.azureedge.net python -m playwright install chromium
```

或走代理:

```bash
HTTPS_PROXY=http://127.0.0.1:7890 python -m playwright install chromium
```

---

## 5. `所有实例都已关机`

```
✗ 参数错误
详情: 所有实例都已关机 — 请到 AutoDL 控制台开机后重跑 `kuake init`
```

字面意思。**去 [AutoDL 控制台](https://www.autodl.com/console/instance/list) 开机**,或:

```bash
kuake start    # 默认开第一个已关机的实例(会扣费!)
```

---

## 6. `Expected 2 copy icons in cell[7], found 0` 类的 selector 异常

实例处于 **已关机 / 开机中** 状态时,没有 SSH 信息,scraper 抓不到。

解决: 等实例「运行中」再跑 init。或选另一台运行中的实例。

新版 kuake 在 [`extract_instance_details`](../src/kuake/browser/autodl_scraper.py) 已先检测状态,会直接给清晰错误。

---

## 7. AutoPanel 跳转后没显示密码登录界面

```
· [在浏览器里] 打开 AutoPanel,如果显示登录页请输入独立密码...
· [在浏览器里] 如果已经直接进 AutoPanel 主页,则无需任何操作
```

直接进了 AutoPanel 主页(不要密码) → 说明 AutoPanel session 已生效。工具继续在后台抓 token,什么都不用做。

---

## 8. 夸克备份目录抓不到 PC 客户端的备份

`kuake init` 列出来只有 "来自:分享" / "来自:BT磁力链下载",**没有你的 PC 客户端备份目录**。

可能原因:

1. **你扫码登的夸克账号 ≠ PC 客户端登的账号**(常见)
   - 解决: 退出当前账号,扫 PC 客户端那个账号的码
2. **PC 客户端从来没成功备份过**
   - 检查客户端「设置 → 备份」是否真的开了 + 监听了某个本地目录
3. **新版 kuake 已经用 panel API 列目录绕开了** —— 如果还是抓不到,可能账号确实没有 PC 备份

新版 kuake v0.3.0 优先用 panel API 列 `/我的备份/`,比抓页面可靠多了。

---

## 9. `code: codeInvalidRequestParams · msg: 您当前操作的网盘不存在`

AutoPanel 上没有绑定 Quark 网盘。

`kuake init` 会自动检测 + 绑定。如果在 v0.2 之前 init 过,可能没绑定:

```bash
kuake init    # v0.3+ 会自动重新检测并绑定
```

---

## 10. 服务器侧磁盘满 / 想清理旧 task

```bash
kuake ls         # 看哪些 task 占用多
kuake rm <task>  # 删远端 + 本地 zip
```

---

## 11. 中文路径乱码

新版 CLI 在入口 `sys.stdout.reconfigure(encoding='utf-8')` 应该没问题。

如果还乱码:

```bash
chcp 65001                                  # cmd
$env:PYTHONIOENCODING="utf-8"               # PowerShell  
export PYTHONIOENCODING=utf-8               # bash
```

---

## 12. session 偶尔自动检测失败让我重扫码

工具尝试在 2 秒内检测已保存的 AutoDL session,网络慢时可能不够。

临时手动修复: 编辑 [`src/kuake/browser/autodl_scraper.py`](../src/kuake/browser/autodl_scraper.py),把 `wait_login` 里的 `timeout=2000` 改成 `timeout=5000`。

---

## 13. 完全卸载

```bash
kuake reset                                 # 清配置(弹确认)
pip uninstall kuake-pipe
# 兜底:
# Win:  rd /s /q %USERPROFILE%\.kuake
# Mac/Linux: rm -rf ~/.kuake
```

---

## 还是不通?

到 [GitHub Issues](https://github.com/pymie/kuake-pipe/issues) 提 issue,附:

1. `kuake doctor` 完整输出
2. `KUAKE_DEBUG=1 kuake <command>` 的 traceback
3. OS + Python 版本(`kuake --version`)

selector 失效类问题,**附浏览器 DOM 截图**会大幅加速修复。
