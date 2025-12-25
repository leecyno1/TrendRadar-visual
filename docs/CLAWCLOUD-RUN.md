# ClawCloud Run 上线指南（TrendRadar Dashboard）

目标：在 ClawCloud Run 上运行一个容器，长期定时抓取 + 生成报告 + 提供 Web UI（Reports/Browse/Manage），并把数据持久化挂载到外部存储，容器重建/迁移后数据不丢。

> 本项目容器内部包含定时器（supercronic），不依赖平台额外的 Cron 产品。

## 1) 获取镜像（两种方式）

你可以让 Claw 自己构建，或直接拉取公开镜像（二者选其一）。

### 1.1 通过 Git 仓库构建（推荐：让 Claw 直接构建）

如果 ClawCloud Run 支持 “From Git / Build from Repository / Dockerfile build”，优先用这种方式：你只需要把代码推到 GitHub，然后在 Claw 选择仓库 + Dockerfile 即可自动构建镜像。

本项目的构建参数建议：

- **Repository**：你的 GitHub 仓库（例如：`https://github.com/leecyno1/TrendRadar-visual`）
- **Build Context**：仓库根目录（`.`）
- **Dockerfile Path**：`docker/Dockerfile`
- **Container Port**：`8080`

随后按本文的 “Persistent Storage” 和 “Environment Variables” 配置即可运行。

### 1.2 直接使用 GHCR 镜像（无需 Claw 构建）

如果你更希望 Claw 直接拉取公开镜像，本项目已提供 GHCR 构建工作流（见 `.github/workflows/ghcr.yml`）。公开镜像地址如下（Image Type 选 `Public`）：

- 主服务（抓取 + Dashboard）：`ghcr.io/leecyno1/trendradar-visual:latest`（推荐）
- MCP 服务（可选）：`ghcr.io/leecyno1/trendradar-visual-mcp:latest`

> 注意：首次构建后需要在 GitHub 的 “Packages” 页面把镜像可见性设为 Public（否则 Claw 拉取会 401）。

### 1.3 先构建并推送镜像（兼容方案：Docker Hub / 私有镜像仓库）

ClawCloud Run “Create App” 需要一个可拉取的镜像地址（Public/Private Registry 均可）。下面给出 Docker Hub 的例子：

1. 登录 Docker Hub：`docker login`
2. 在项目根目录构建镜像（主服务：抓取 + Web UI）：
   - `docker build -f docker/Dockerfile -t <你的DockerHub用户名>/trendradar-dashboard:latest .`
3. 推送镜像：
   - `docker push <你的DockerHub用户名>/trendradar-dashboard:latest`

（可选）如果你还要 MCP 服务（AI 分析），再构建并推送：
- `docker build -f docker/Dockerfile.mcp -t <你的DockerHub用户名>/trendradar-mcp:latest .`
- `docker push <你的DockerHub用户名>/trendradar-mcp:latest`

## 2) 在 ClawCloud Run 创建 App（主服务）

ClawCloud 文档里“从 Docker 迁移”的映射关系非常直接：`-p` → Container Port，`-e` → Environment Variables，`-v` → Local Storage（持久化挂载）。

参考：`https://docs.run.claw.cloud/clawcloud-run/migration/migrate-from-docker`

### 2.1 基础参数（建议）

- **Application Name**：`trendradar`
- **Image Type**：`Public`
- **Image Name**（二选一）：
  - GHCR：`ghcr.io/leecyno1/trendradar-visual:latest`
  - Docker Hub：`<你的DockerHub用户名>/trendradar-dashboard:latest`
- **Usage Type**：`Fixed`
- **Replicas**：`1`（SQLite + 本地存储场景不建议多副本）
- **CPU/Memory**：按需求（建议至少 0.5 Core / 512MB 起）

### 2.2 Network

- **Container Port**：`8080`

> 如果平台自动注入 `PORT`，请保证它和 Container Port 一致；必要时直接在环境变量里加一条：`PORT=8080`。

### 2.3 Persistent Storage（关键）

你的新闻数据（`output/` 下的 SQLite、HTML 报告等）必须持久化，否则容器重建就会丢。

推荐做法：**只挂载一个目录到容器的 `/data`**，由容器把 `/app/config` 与 `/app/output` 映射到 `/data` 下（避免平台不支持多挂载点）。

- **Advanced Configuration → Local Storage / Persistent Storage**
  - **Container Path**：`/data`
  - **Storage Size**：按需（建议 5GB+，跑久了会增长）

参考：`https://docs.run.claw.cloud/clawcloud-run/guide/app-launchpad/persistent-storage`

### 2.4 Environment Variables（建议一套可用的最小配置）

在 ClawCloud Run 的 “Advanced Configuration → Environment Variables” 填入：

- `TZ=Asia/Shanghai`
- `ENABLE_WEBSERVER=true`（开启 Dashboard；若平台注入了 `PORT` 且你没填此项，也会默认自动开启）
- `PORT=8080`（可选但推荐：显式与 Container Port 对齐）
- `RUN_MODE=cron`
- `CRON_SCHEDULE=*/30 * * * *`（示例：每 30 分钟抓取一次）
- `IMMEDIATE_RUN=true`（启动时先抓一次）
- `STORAGE_BACKEND=local`（建议固定为本地，避免 auto 判定差异）
- `STORAGE_HTML_ENABLED=true`
- `STORAGE_TXT_ENABLED=false`（可选：省空间）
- `USE_DATA_DIR=true`（启用单挂载目录模式）
- `DATA_DIR=/data`
- `ADMIN_TOKEN=<强随机字符串>`（强烈建议：保护 `/manage` 与 `/api/admin/*`）

> 说明：管理页保存配置时，会写入 `/app/config/*`。在 `USE_DATA_DIR=true` 且 `/data` 已挂载时，这些文件会落盘到外部存储中。

## 3) 初始化与访问

部署完成后：

- 打开 ClawCloud Run 提供的 **Public Address**
- Dashboard 首页：`/`
- 报告页：`/reports`
- 数据浏览：`/browse`
- 管理页：`/manage`
  - 如设置了 `ADMIN_TOKEN`，在页面中填入 token（会存到浏览器 localStorage），后续保存配置/触发抓取会自动带上请求头 `X-Admin-Token`。
- 健康检查：`/api/health`

## 4) （可选）部署 MCP 服务（AI 分析）

如果需要 MCP 服务（端口 3333）：

1. 再创建一个 App：
   - Image：`<你的DockerHub用户名>/trendradar-mcp:latest`
   - Container Port：`3333`
2. **同样挂载 `/data`**（确保它能读取主服务写入的 `/data/output` 与 `/data/config`）
3. 环境变量建议：
   - `TZ=Asia/Shanghai`
   - `USE_DATA_DIR=true`
   - `DATA_DIR=/data`

> 如果你无法在两个 App 之间共享同一份持久化存储，建议改用远程存储（S3/R2/OSS/COS）+ `PULL_ENABLED=true` 让 MCP 服务拉取数据。

## 5) 常见问题

### 5.1 报错：upstream connect error... delayed connect error: 111

这表示网关连不上容器端口（连接被拒绝），通常是 Web 服务没起来或监听端口不一致：

- 检查 App 的 **Container Port** 是否为 `8080`
- 检查是否启用 Web：`ENABLE_WEBSERVER=true`（或确认平台注入了 `PORT`，项目会默认自动开启）
- 确保 `PORT`（若存在）与 Container Port 一致（推荐直接配置 `PORT=8080`）
- 看容器日志是否出现 `🌐 启动 Web 服务器 (端口: ...)`；并访问 `GET /api/health`

- **为什么不建议多副本？**
  - 本地 SQLite + 单挂载目录模式本质是“单机状态”，多副本会带来数据一致性/锁问题。
- **管理页能改哪些参数？**
  - 直接编辑并保存 `config.yaml` 与 `frequency_words.txt`（完整覆盖项目参数）。注意：环境变量优先级高于配置文件，若你在平台设置了某些环境变量，会覆盖你在配置文件里的同名项。
