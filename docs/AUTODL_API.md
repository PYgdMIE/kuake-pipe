# AutoDL.com 平台 API 文档 (kuake-pipe 角度)

> 整理 kuake-pipe 已发现的 AutoDL API endpoint, 以及可工具化的候选功能。
> 全部基于 2026-05 反向工程, 不是官方文档。AutoDL 改 API 时这份文档需要更新。

## 鉴权

**必需**: JWT in `Authorization` header,从 `localStorage.token` 拿。
单纯 cookies 不够 — 会 `AuthorizeFailed: 登录超时`。

kuake-pipe 通过 `kuake.autodl_api.load_jwt_from_storage_state()` 提取。

## 已实现 / 已 wrap 的 endpoint

| Endpoint | 方法 | 用途 | kuake 命令 |
|---|---|---|---|
| `/api/v1/instance` | POST | 列用户实例 | `kuake instances`, `kuake clone` |
| `/api/v1/user/machine/list` | POST | 列市场可租机器 | `kuake grab`, `kuake clone` |
| `/api/v1/region/list` | GET | 列区域枚举 | (内部用) |
| `/api/v1/machine/region/gpu_type` | POST | 列 region/GPU 组合 | (内部用) |
| `/api/v1/wallet/balance` | GET | 钱包余额 | (内部用,plan 预算) |
| `/api/v1/order/instance/create/payg` | POST | **创建 PAYG 实例 (扣费!)** | `kuake confirm-create` |

## 探到但未 wrap 的 endpoint

抓包记录在 `/tmp/kuake-autodl-trace.jsonl`(运行 `scripts/probe_autodl_create_flow.py` 生成)。

| Endpoint | 用途 | 可工具化候选 |
|---|---|---|
| `/api/v1/user/detail` | 用户详情 | `kuake whoami` |
| `/api/v1/user/member/detail` | 会员等级 / 折扣 | 集成进 grab 显示真实价 |
| `/api/v1/coupon_market` | 优惠券集市 | `kuake coupons` 列可领 |
| `/api/v1/user/followed_machine/list` | 关注的机器 | `kuake watch` 监控特定机器 |
| `/api/v1/instance/tag/list` | 实例标签 | 给实例打标签便于检索 |
| `/api/v1/machine/tag` | 机器标签 (高带宽 / 独享等) | grab 过滤选项 |
| `/api/v1/instance/count/v1` | 实例数量统计 | dashboard |
| `/api/v1/phone_area` | 手机区号 (用户管理) | 跳过 |
| `/api/v1/time_sync` | 服务器时间 | 跳过 |
| `/api/v1/user/sub_user/list` | 子账号 | `kuake users` 多账号管理 |
| `/api/v1/instance/release/info` | 释放实例信息 | 跳过 (sensitive) |
| `/api/v1/common` | 通用配置 | (内部用) |

## 还未发现的 endpoint (重要 + 缺)

| 功能 | 估计的 path | 影响 |
|---|---|---|
| 镜像列表 (公共 / 社区 / 私有) | `/api/v1/image/...` 但具体路径未验证 | clone 时只能用 `image` 字段字符串,不能列私有镜像让用户选 |
| 实例克隆 info (官方一键 clone) | `/api/v1/instance/clone/...` | 现在 kuake clone 是「找新机器 + 复制源 config」,不是 AutoDL 的原生 clone 功能 |
| 数据盘 / 系统盘扩容价格预查 | `/api/v1/.../disk/...` | 扩容时不知道会扣多少钱 |
| 镜像复现详情 | `/api/v1/community/reproduction/...` | 用社区镜像时缺 metadata |

要补的话: 在 AutoDL 控制台手动跑这些 flow,用 Playwright 抓 trace (`scripts/probe_autodl_create_flow.py` 改改可复用)。

## 已实现的 kuake 命令矩阵

| 命令 | 入参 | 是否 SSH | 是否扣费 |
|---|---|---|---|
| `kuake instances` | — | 不 | 不 |
| `kuake start [N]` | 实例编号 | 不 | 启动后会按时计费 |
| `kuake stop [N]` | 实例编号 | 不 | 不 |
| `kuake grab` | GPU/region 过滤 | 不 | **绝对不**(只 PLAN) |
| `kuake clone <src>` | 源实例 | 不 | **绝对不**(只 PLAN) |
| `kuake confirm-create` | plan 文件 | 不 | ⚠️ **会** |
| `kuake doctor` | — | 测一下 | 不 |
| `kuake ls` | — | 是 | 不 |
| `kuake rm` | task 名 | 是 | 不 (删本地+远端 zip) |
| `kuake push` | task + src | 是 | 不 (假设实例已在运行) |

## 待工具化的候选清单 (v0.5+)

按价值排序:

1. **`kuake whoami`** — 显示用户信息 + 钱包余额 + 会员等级。一行。
2. **`kuake coupons`** — 列可领优惠券 (从 `/api/v1/coupon_market`),应用到 plan 里
3. **`kuake watch <machine_id>`** — 关注特定机器/区,有空闲时 desktop notification
4. **`kuake images`** — 列我的私有镜像 + 公共镜像 (待 endpoint 探出)
5. **`kuake usage`** — 当月消费汇总 (`/api/v1/order/...` 类)
6. **`kuake snapshot <uuid>`** — 给实例做镜像快照 (AutoDL 有此功能)
7. **`kuake shell <N>`** — 自动 SSH 连接到第 N 号实例(读 config + 启动 ssh)

## 安全约束 (kuake-pipe 工程纪律)

1. **永远不要静默调 `/api/v1/order/...`**: 任何会产生订单 / 扣费 / 释放实例的 API,都要在 confirm-create 类命令里走 `input("YES")` 二次确认
2. **plan-first**: 改实例配置 / 创建 / 删除 等"会引起状态变化"的操作,先生成 plan,落盘,二次确认
3. **dry-run 默认**: 任何 `kuake xxx` 都要有 `--dry-run` 等价行为作为默认
4. **error 显示**: AutoDL 返回 `AuthorizeFailed` 时统一抛 `SessionDead`, 引导跑 `kuake init`

## 重新抓 trace 流程 (当 AutoDL 改 API 时)

```bash
.venv/bin/python scripts/probe_autodl_create_flow.py
# 浏览器会自动打开, 手动点到创建实例的页面, 看 trace.jsonl
```

`trace.jsonl` 每行一个 request/response 事件,可以 diff 老 trace 找出 endpoint 变化。
