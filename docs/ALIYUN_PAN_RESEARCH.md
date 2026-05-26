# 阿里云盘 (Aliyun Drive) 集成调研

> Status: **research only, not implemented**. v0.5 候选。
> 目的:作为夸克网盘之外的第二上行后端,扩大 kuake-pipe 适用面。

## TL;DR

阿里云盘比夸克更容易集成:
- 协议公开度更高(Aliyun PDS 已有官方 API 文档)
- 第三方 Python SDK 维护更活跃(`aligo`)
- 同样支持 cookie + JWT 鉴权
- 同样切片上传到 OSS,endpoint pattern 更规范

**预估工程量**: 3-5 天(对照 Quark 的协议逆向 + 单测 + 集成 +文档)。

---

## 鉴权对比

| 维度 | Quark | Aliyun Drive |
|---|---|---|
| 登录态 | Cookie (`pan.quark.cn` domain) | refresh_token + access_token (OAuth2 风格) |
| 鉴权 header | `Cookie: ...` | `Authorization: Bearer <access_token>` |
| Token 刷新 | 内部 SSO 自动续 | `/v2/account/token` with refresh_token |
| 扫码登录 | 夸克扫码 | 支付宝扫码 |

实现方式:
- `kuake init --quark` (现状) → 走 Quark 流程
- `kuake init --aliyun` (新) → 走支付宝扫码 + refresh_token 存到 credentials.toml

## 关键 API endpoint (推测,需逆向确认)

```
POST https://api.aliyundrive.com/v2/file/create
  Body: { drive_id, parent_file_id, name, type: 'file', size, content_hash_name: 'sha1' }
  Resp: { upload_id, part_info_list[{part_number, upload_url}] }

PUT  {part_info_list[i].upload_url}
  Body: <part bytes>
  Resp: ETag

POST https://api.aliyundrive.com/v2/file/complete
  Body: { drive_id, file_id, upload_id }
```

对比 Quark:
- 不需要 `auth_meta` 额外签名步骤 — upload_url 已是预签 URL
- 直接 PUT 不需 OSS-style Authorization
- **更简单**

## 第三方 SDK 候选

| SDK | 维护 | 接口质量 | 备注 |
|---|---|---|---|
| `aligo` (PyPI) | 活跃 (2026) | 高 | 二维码登录 + 完整 file/share/upload API |
| `aliyunpan-python` | 一般 | 中 | 较老但够用 |
| `aliyun-drive-uploader` | 死 | — | 跳过 |

推荐:`aligo`。但我们已经在 Quark 那边的踩坑经验告诉我:三方库**容易 bitrot**(Quark `quarkpan` 库已经因为 endpoint 改了而失效一年)。所以做正经集成时仍然要:

1. 用 SDK 跑通 prototype 上传
2. 抓 trace 看真实流量(`scripts/probe_aliyun_upload.py` 类比 Quark)
3. 写自己的 `kuake/aliyun_uploader.py`(参照 `quark_uploader.py` 的结构)
4. 单测覆盖 ≥90%

## 与 AutoPanel 的集成

AutoDL 的 AutoPanel 是否支持阿里云盘?

- AutoPanel `netdisk_list` 看,默认绑定 `quark1` 类型
- 是否有 `aliyun1` 类型待确认。需要在 AutoPanel UI 上看「网盘管理」是否能加阿里云盘
- 若不支持,这条路就只能上传到阿里云盘但 AutoDL 服务器侧没法触发下载 — 退路:工具自己 SSH 把 zip wget/curl 下来(URL 来自阿里云盘分享链接)

**这一步要先在 AutoDL 控制台手动试一下能否绑定阿里云盘**,再决定继续投入。

## 设计草图

`kuake/uploader.py` (新抽象层):

```python
class CloudUploader(Protocol):
    def upload(self, path: Path, parent_id: str, *, on_progress=None) -> UploadResult: ...
    def resolve_or_create_folder(self, cloud_path: str) -> str: ...

# kuake/quark_uploader.py 实现 CloudUploader
# kuake/aliyun_uploader.py 实现 CloudUploader
# push.py 根据 config 选哪一个
```

config.toml v0.5 schema:
```toml
[cloud]
provider = "quark"  # 或 "aliyun"
backup_path = "/kuake-uploads"

[cloud.quark]
cookie = "..."  # 现 credentials.toml.quark.cookie 移过来

[cloud.aliyun]
refresh_token = "..."
drive_id = "..."   # 主云盘 ID,会在 init 时自动获取
```

## 工作量拆解

- [ ] AutoPanel 是否支持阿里云盘验证(15min)
- [ ] 阿里云盘登录流程 + token 持久化(0.5 天)
- [ ] `aliyun_uploader.py` 协议实现(1 天)
- [ ] Mock 测试 + 真账号 smoke(0.5 天)
- [ ] CloudUploader 抽象 + push 路由(0.5 天)
- [ ] init 加 `--provider` flag(0.5 天)
- [ ] 文档 + README 更新(0.5 天)

**总计:~3 天,假设 AutoPanel 端支持。**

## 待办

1. 在 AutoDL 网页 AutoPanel 上手动看「网盘管理」是否能选阿里云盘 — 这是 go/no-go gate
2. 如果不行,改另一条思路:用阿里云盘直接生成下载链接,服务器 SSH 端 wget 下来,跳过 AutoPanel
