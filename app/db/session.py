"""数据库连接与会话管理。

使用 SQLAlchemy 同步引擎，SQLite 作为默认数据库。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """FastAPI 依赖注入用的数据库会话生成器。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
