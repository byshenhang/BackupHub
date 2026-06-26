# Backup-Hub

通用备份管理与调度平台。

## 功能特性

- **多类型备份执行器**：Git/GitLab 仓库备份（已实现），文件目录备份、数据库备份（即将支持）
- **多存储目标**：本地目录、阿里云 OSS（已实现），腾讯云 COS、WebDAV（即将支持）
- **定时调度**：基于 APScheduler 的 cron 调度，支持手动触发
- **执行历史**：完整的执行记录与日志，便于排查问题
- **凭证加密**：敏感信息 Fernet 加密存储
- **Web 管理后台**：Jinja2 + HTMX 服务端渲染，无需前端构建

## 快速开始

```bash
# 1. 克隆代码
git clone <repo-url> backup-hub
cd backup-hub

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，填入必要配置

# 5. 初始化数据库
python -m scripts.init_db

# 6. 启动服务
python -m app.main
```

浏览器打开 http://localhost:8000

## 技术栈

| 组件 | 选型 |
|------|------|
| Web 框架 | FastAPI |
| 模板引擎 | Jinja2 + HTMX |
| 任务调度 | APScheduler |
| ORM | SQLAlchemy |
| 数据库 | SQLite（可切换 PostgreSQL） |
| 凭证加密 | cryptography (Fernet) |
| Git 操作 | git CLI + httpx |
| OSS 上传 | oss2 |

## 目录结构

```
backup-hub/
├── app/                  # 应用主代码
│   ├── api/              # HTTP 接口
│   ├── core/             # 核心业务逻辑
│   ├── db/               # 数据库层
│   ├── executors/        # 备份执行器（可插拔）
│   ├── storages/         # 存储上传器（可插拔）
│   ├── alerts/           # 告警渠道
│   └── web/              # 前端模板
├── deploy/               # 部署配置
├── scripts/              # 运维脚本
├── tests/                # 测试
├── data/                 # 运行时数据
└── logs/                 # 日志
```

## 部署

详见 [deploy/README.md](deploy/README.md)

## License

MIT
