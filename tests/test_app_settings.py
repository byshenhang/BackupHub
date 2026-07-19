"""应用级加密设置测试。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.core.app_settings import (
    GITHUB_TOKEN_KEY,
    delete_secret,
    get_github_token,
    get_github_token_status,
    set_secret,
)
from app.db.session import Base


def test_github_token_database_override_and_environment_fallback(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "environment-token")

    assert get_github_token(db) == "environment-token"
    assert get_github_token_status(db)["source"] == "environment"

    set_secret(db, GITHUB_TOKEN_KEY, "database-token")
    assert get_github_token(db) == "database-token"
    assert get_github_token_status(db)["source"] == "database"

    assert delete_secret(db, GITHUB_TOKEN_KEY) is True
    assert get_github_token(db) == "environment-token"
    db.close()
