"""应用配置加载模块。

从环境变量和 .env 文件读取配置，提供统一的配置访问接口。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（backup-hub/）
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载 .env 文件
load_dotenv(BASE_DIR / ".env")


class Settings:
    """应用配置项，从环境变量读取。"""

    # 服务
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Shanghai")

    # 数据库
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'backup-hub.db'}")

    # 凭证加密主密钥
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    # 登录
    LOGIN_PASSWORD: str = os.getenv("LOGIN_PASSWORD", "")
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")

    # GitLab（服务地址由 Web 任务配置提供）
    GITLAB_TOKEN: str = os.getenv("GITLAB_TOKEN", "")

    # GitHub 私有仓库访问令牌（仓库 URL 由任务配置提供）
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

    # WebDAV（测试和初始化配置）
    WEBDAV_URL: str = os.getenv("WEBDAV_URL", "")
    WEBDAV_USERNAME: str = os.getenv("WEBDAV_USERNAME", "")
    WEBDAV_PASSWORD: str = os.getenv("WEBDAV_PASSWORD", "")
    WEBDAV_REMOTE_PATH: str = os.getenv("WEBDAV_REMOTE_PATH", "/backup-hub/")

    # 日志
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # 路径
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    REPOS_DIR: Path = BASE_DIR / "data" / "repos"
    LOGS_DIR: Path = BASE_DIR / "logs"
    TEMP_DIR: Path = BASE_DIR / "data" / "temp"


settings = Settings()

# 确保必要目录存在
for dir_path in [settings.DATA_DIR, settings.REPOS_DIR, settings.LOGS_DIR, settings.TEMP_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)
