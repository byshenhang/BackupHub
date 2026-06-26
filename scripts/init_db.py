"""初始化数据库脚本。

创建所有表结构。用法：python -m scripts.init_db
"""

import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import Base, engine
from app.db.models import BackupJob, StorageTarget, ExecutionRecord, AlertChannel  # noqa: F401


def init_database():
    """创建所有数据库表。"""
    print("正在创建数据库表...")
    Base.metadata.create_all(bind=engine)
    print("数据库表创建完成。")


if __name__ == "__main__":
    init_database()
