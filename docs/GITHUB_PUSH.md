# AuraDash — 推送到 GitHub 全流程

本文件面向「已安装 git，但本机尚未登录 GitHub」的情况。三步即可发布：

## 方式 A：GitHub CLI（推荐，交互最少）

```
winget install --id GitHub.cli -e
gh auth login
```
按提示选择 `GitHub.com` → `HTTPS` → 浏览器授权（复制网页显示的一次性代码到浏览器即可）。

随后运行仓库内脚本：

```
powershell -ExecutionPolicy Bypass -File tools\push_github.ps1
```

它会自动：初始化仓库 → 提交 → 创建 GitHub 仓库（名称 AuraDash）→ 推送。

## 方式 B：Git Credential Manager（凭据弹窗）

首次 `git push` 时，Git 凭据管理器会弹出浏览器窗口，登录 GitHub 授权一次即可，之后凭据由系统保管。

```
git init -b main
git add .
git commit -m "feat: AuraDash v1.0.0 - Windows 悬浮硬件监控仪表盘"
git branch -M main
git remote add origin https://github.com/<你的用户名>/AuraDash.git
git push -u origin main
```

## 方式 C：个人访问令牌（PAT）

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens**（建议：仅授予 `AuraDash` 仓库读写、7 天有效期）
2. 推送时输入用户名 + 令牌作为密码（令牌等同密码，用完可撤销）

## 发布后建议

- 仓库设置 → Releases → 上传 `dist\AuraDash\AuraDash.exe` 与 `installer\AuraDash_Setup_1.0.0.exe`
- 网页 GitHub → Deploy keys / README 展示（README 内嵌截图已就绪）
