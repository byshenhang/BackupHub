# Backup-Hub

通用备份管理与调度平台。通过 Web 后台配置备份任务，平台按计划自动调度执行、上传到指定存储目标，并对每次执行进行记录和监控。

## 功能特性

- **登录认证** — 密码登录，Session 会话管理
- **Git/GitLab 备份** — 支持 GitHub 私有单仓库和 GitLab 全量项目，镜像克隆 + 增量更新
- **多存储目标** — 本地目录、阿里云 OSS、WebDAV（123 网盘/坚果云/Nextcloud 等）
- **定时调度** — cron 表达式调度，支持手动触发，并发保护
- **执行历史** — 完整的执行记录、耗时、产物大小、详细日志
- **保留策略** — 按天数自动清理旧备份，先确认新备份成功再清理
- **凭证加密** — 存储目标的连接配置 Fernet 加密存储
- **Web 管理后台** — Jinja2 + HTMX 服务端渲染，无需前端构建

## 快速开始（SOP）

### 1. 环境准备

```bash
# 克隆代码
git clone <repo-url> backup-hub
cd backup-hub

# 创建虚拟环境
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
# 复制配置模板
cp .env.example .env
```

编辑 `.env`，**必须配置**：

```ini
# 登录密码（必填，否则无法登录）
LOGIN_PASSWORD=your-password-here

# GitLab Token（仅使用 GitLab 全量备份时需要；URL 在任务页面配置）
GITLAB_TOKEN=glpat-xxxx

# 端口（默认 8000，被占用可改为其他）
PORT=8010
```

可选配置：

```ini
# 凭证加密密钥（留空则自动生成临时密钥，生产环境建议配置）
SECRET_KEY=
# 生成方式：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Session 加密密钥（留空则使用内置开发密钥）
SESSION_SECRET=

# 日志级别
LOG_LEVEL=INFO
```

### GitHub 私有仓库 Token

推荐使用 GitHub Fine-grained personal access token。可从以下官方入口创建：

- [创建 Fine-grained Token（已预填 Contents: read）](https://github.com/settings/personal-access-tokens/new?name=BackupHub&description=Read-only+repository+backup&contents=read)
- [GitHub 官方 Token 管理文档](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)

创建时按以下最小权限配置：

1. `Resource owner` 选择仓库所有者 `byshenhang`。
2. `Repository access` 选择 `Only select repositories`。
3. 只选择 `super-agent-kernel`。
4. `Repository permissions` 中将 `Contents` 设为 `Read-only`。
5. 设置合理的过期时间并生成 Token。
6. 登录 BackupHub，进入「应用设置」，保存 Token 后点击「测试仓库访问」。
7. 在「备份任务」中创建 Git 任务，将仓库 URL 填写为 HTTPS 克隆地址。

Token 等同密码，不要写入任务表单、README、日志或提交到 Git。BackupHub 通过临时 Git 配置传递 Token，镜像仓库的 remote URL 不保存 Token。
网页保存的 Token 会加密写入数据库并立即生效，无需重启。`.env` 的 `GITHUB_TOKEN` 仅作为可选回退配置。

如果权限测试提示无法连接 `github.com:443`，请先确认本机能访问 GitHub。原生运行可在 `.env` 配置 `HTTP_PROXY` 和 `HTTPS_PROXY`；Docker Desktop 容器应使用 `http://host.docker.internal:<代理端口>`，不能使用容器自身的 `127.0.0.1`。

### 123 网盘 WebDAV

在 123 网盘的 WebDAV 授权管理中创建一个具有“读写”权限的应用，使用该应用显示的账号和应用密码。配置格式：

```ini
WEBDAV_URL=https://webdav.123pan.cn/webdav/
WEBDAV_USERNAME=123网盘生成的WebDAV账号
WEBDAV_PASSWORD=123网盘生成的应用密码
WEBDAV_REMOTE_PATH=/GithubSync/
```

然后在管理后台创建 `WebDAV` 存储目标，填入相同配置。服务地址必须是 WebDAV 端点，不能填写 123 网盘普通网页地址。测试备份会上传为：

```text
/GithubSync/super-agent-kernel_YYYYMMDD_HHMMSS.tar.gz
```

压缩包内是完整的裸镜像仓库 `super-agent-kernel.git/`，包含分支、标签和 Git 历史，可用于完整恢复。

也可以直接从 `.env` 初始化或更新 WebDAV 存储目标：

```bash
python -m scripts.configure_webdav
```

脚本会将 WebDAV 凭证加密存入数据库。GitHub Token 在「应用设置」维护；仓库 URL、调度周期和存储目标在任务页面配置。先手动执行验证，成功后再启用定时调度。

### 3. 初始化数据库

```bash
python -m scripts.init_db
```

### 4. 启动服务

```bash
python -m app.main
```

服务启动后：
- **Web 管理后台**：http://localhost:8010（端口取决于 `.env` 配置）
- **API 文档**：http://localhost:8010/docs（FastAPI 自动生成）
- **健康检查**：http://localhost:8010/api/health

### 5. 使用流程

```
登录 → 创建存储目标 → 创建备份任务 → 手动触发测试 → 查看执行历史
```

1. **登录**：打开浏览器，输入 `.env` 中配置的密码
2. **创建存储目标**：侧边栏「存储目标」→ 新增，选择类型（本地/OSS/WebDAV）填写配置
3. **创建备份任务**：侧边栏「备份任务」→ 新建，选择任务类型、调度周期、关联存储目标
4. **手动触发**：任务列表中点击「执行」按钮，立即触发一次备份
5. **查看结果**：侧边栏「执行历史」查看状态、耗时、日志

## 技术栈

| 组件 | 选型 |
|------|------|
| Web 框架 | FastAPI |
| 模板引擎 | Jinja2 + HTMX |
| 任务调度 | APScheduler |
| ORM | SQLAlchemy 2.0 |
| 数据库 | SQLite（可切换 PostgreSQL） |
| 凭证加密 | cryptography (Fernet) |
| Git 操作 | git CLI + httpx |
| OSS 上传 | oss2 |
| WebDAV 上传 | requests + WebDAV HTTP methods |

## 目录结构

```
backup-hub/
├── app/                      # 应用主代码
│   ├── api/                  # HTTP 接口层
│   │   ├── auth.py           # 登录认证
│   │   ├── jobs.py           # 任务 CRUD + 手动触发
│   │   ├── runs.py           # 执行历史查询
│   │   ├── storages.py       # 存储目标 CRUD
│   │   └── pages.py          # 页面路由（Jinja2 渲染）
│   ├── core/                 # 核心业务逻辑
│   │   ├── runner.py         # 执行编排（执行器→上传器→清理→记录）
│   │   ├── scheduler.py      # APScheduler 调度管理
│   │   └── crypto.py         # 凭证加解密
│   ├── db/                   # 数据库层
│   │   ├── models.py         # ORM 模型（5 张表）
│   │   └── session.py        # 引擎与会话
│   ├── executors/            # 备份执行器（可插拔）
│   │   ├── base.py           # 抽象接口
│   │   ├── git.py            # Git/GitLab 执行器
│   │   └── registry.py       # 执行器注册表
│   ├── storages/             # 存储上传器（可插拔）
│   │   ├── base.py           # 抽象接口
│   │   ├── local.py          # 本地目录
│   │   ├── oss.py            # 阿里云 OSS
│   │   ├── webdav.py         # WebDAV
│   │   └── registry.py       # 上传器注册表
│   ├── alerts/               # 告警渠道（后续版本）
│   ├── web/templates/        # Jinja2 模板
│   └── main.py               # 程序入口
├── deploy/                   # 部署配置
│   ├── backup-hub.service    # systemd 单元文件
│   ├── install-service.bat   # Windows NSSM 安装脚本
│   └── README.md             # 部署文档
├── scripts/                  # 运维脚本
│   └── init_db.py            # 数据库初始化
├── data/                     # 运行时数据（自动创建）
│   ├── backup-hub.db         # SQLite 数据库
│   ├── repos/                # Git 镜像仓库（增量更新用）
│   └── temp/                 # 临时文件
├── logs/                     # 日志（自动创建）
├── .env.example              # 配置模板
├── requirements.txt          # 依赖清单
└── pyproject.toml            # 项目元数据
```

## 数据模型

| 表 | 说明 |
|----|------|
| `backup_jobs` | 备份任务（名称、类型、cron、配置、存储目标、保留天数） |
| `storage_targets` | 存储目标（名称、类型、加密连接配置） |
| `execution_records` | 执行记录（状态、时间、大小、日志、触发方式） |
| `alert_channels` | 告警渠道（后续版本） |

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（免登录） |
| POST | `/login` | 登录 |
| GET | `/logout` | 登出 |
| GET | `/api/jobs` | 任务列表 |
| POST | `/api/jobs` | 创建任务 |
| PUT | `/api/jobs/{id}` | 编辑任务 |
| DELETE | `/api/jobs/{id}` | 删除任务 |
| POST | `/api/jobs/{id}/run` | 手动触发 |
| PATCH | `/api/jobs/{id}/toggle` | 启用/停用 |
| GET | `/api/runs` | 执行历史 |
| GET | `/api/runs/{id}` | 执行详情 |
| GET/POST/PUT/DELETE | `/api/storages` | 存储目标 CRUD |

完整 API 文档：http://localhost:8010/docs

## 生产部署

详见 [deploy/README.md](deploy/README.md)

要点：
- Linux 用 systemd，Windows 用 NSSM，配置开机自启 + 崩溃重启
- **必须**配置 `LOGIN_PASSWORD` 和 `SECRET_KEY`
- 日志自动轮转（10MB/文件，保留 5 个）
- SQLite 文件在 `data/backup-hub.db`，定期备份

## Docker Compose

准备 `.env` 后构建并启动：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backup-hub
```

默认访问地址为 `http://localhost:8010`，可通过 `.env` 的 `BACKUP_HUB_PORT` 修改宿主机端口。容器内部固定监听 `8000`。

首次使用 123 网盘 WebDAV 时，可以从 `.env` 初始化存储目标：

```bash
docker compose exec backup-hub python -m scripts.configure_webdav
```

SQLite 数据库、Git 镜像缓存和日志分别保存在 `backuphub-data`、`backuphub-logs` Docker 卷中。停止服务不会删除数据：

```bash
docker compose down
```

只有明确需要清空全部容器数据时才使用 `docker compose down -v`。

## 开发调试

```bash
# 开启调试模式（自动重载）
DEBUG=true python -m app.main

# 删库重建（开发阶段）
rm data/backup-hub.db
python -m scripts.init_db
```

## License

MIT
