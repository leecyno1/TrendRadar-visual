# 形成独立新项目（迁移到你的 Git 仓库）

你现在这份代码是在原 TrendRadar 基础上增加了 Dashboard（前端页面 + 管理/浏览 API）与 ClawCloud Run 部署能力。要变成你自己的“独立新项目”，推荐按下面步骤操作（保留可选的 upstream）：

## 方案 A：直接把当前目录推到你的新仓库（最简单）

1. 在你的 Git 平台创建一个空仓库（不要勾选初始化 README/License）
2. 在当前项目目录执行：
   - 查看现有远端：`git remote -v`
   - （可选）把原仓库当 upstream：`git remote rename origin upstream`
   - 添加你的仓库为 origin：`git remote add origin <你的仓库地址>`（如果你没做上一步，改成 `git remote set-url origin ...`）
   - 推送：`git push -u origin master`（或 `main`，以你本地分支名为准）

## 方案 B：重新初始化一个全新的 Git 历史（更“干净”）

适合你不想带上原项目提交历史时使用：

1. 复制一份目录（避免破坏你当前工作区）：
   - `cp -R TrendRadar TrendRadar-dashboard`
2. 进入新目录：
   - `cd TrendRadar-dashboard`
3. 删除旧的 git 历史并重新初始化：
   - `rm -rf .git`
   - `git init`
   - `git add -A`
   - `git commit -m "init: TrendRadar dashboard"`
4. 绑定你的远端并推送：
   - `git remote add origin <你的仓库地址>`
   - `git push -u origin master`（或 `main`）

## 建议的仓库命名

- `trendradar-dashboard`
- `trendradar-claw`
- `trendradar-admin`

