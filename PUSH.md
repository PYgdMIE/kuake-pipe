# 推到 GitHub 一键指南

## 1. 在 GitHub 创建仓库

打开 https://github.com/new

- Owner: **PYgdMIE**
- Repository name: **kuake-pipe**
- Public
- ⚠️ **不要勾任何 "Initialize this repository with..." 选项**(README/LICENSE/.gitignore 本地都有了)

点 "Create repository"。

## 2. 配 git 身份(如果还没配)

```bash
git config --global user.name "PYgdMIE"
git config --global user.email "pymie0405@gmail.com"   # 你的 GitHub 邮箱
```

## 3. 选认证方式

### 方式 A: HTTPS + Personal Access Token (最简单,推荐第一次)

1. https://github.com/settings/tokens → **Generate new token (classic)**
2. 勾 `repo` 权限,生成 → 复制 token (`ghp_xxx...`)
3. 接 remote:
   ```powershell
   cd C:\Users\mie\Downloads\kuake
   git remote add origin https://github.com/PYgdMIE/kuake-pipe.git
   git branch -M main
   git push -u origin main
   # 提示用户名: PYgdMIE
   # 提示密码:粘 ghp_xxx token
   git tag v0.3.0
   git push origin v0.3.0
   ```

### 方式 B: SSH (一次配,长期省心)

```powershell
# 生成 SSH key (Win PowerShell)
ssh-keygen -t ed25519 -C "pymie0405@gmail.com"
# 一路回车不设密码

# 复制公钥到剪贴板
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | Set-Clipboard
```

打开 https://github.com/settings/ssh/new → 标题随便 → 粘贴 → Add SSH key。

测试 + push:
```powershell
ssh -T git@github.com    # 应该返回 "Hi PYgdMIE! ..."
cd C:\Users\mie\Downloads\kuake
git remote add origin git@github.com:PYgdMIE/kuake-pipe.git
git branch -M main
git push -u origin main
git tag v0.3.0
git push origin v0.3.0
```

## 4. 验证

- 网页打开 https://github.com/PYgdMIE/kuake-pipe → 看到 README
- 点 Actions tab → test workflow 应该自动跑(几分钟出绿)
- 点 Releases (没有的话点 Tags) → 看到 v0.3.0

## 5. 到 GitHub 网页做的事(可选,提质感)

- 仓库主页 About → **Description**: `本地→夸克→AutoDL 全自动数据中转 + 抢卡`
- About → **Topics**: `autodl`, `quark-pan`, `python`, `cli`, `automation`, `playwright`
- About → 勾上 "Releases"
- Releases 页面 → "Draft a new release" → 选 v0.3.0 tag → 把 CHANGELOG.md 里 v0.3.0 段复制进 description → Publish

---

## 故障

| 问题 | 修 |
|---|---|
| `Authentication failed` (HTTPS) | token 没勾 `repo` 权限,重新生成 |
| `Permission denied (publickey)` | SSH key 没加到 GitHub |
| `remote: Repository not found` | 仓库没创/拼写错 owner/repo |
| CI 跑红 | 看 Actions 日志,跟我反馈 |
