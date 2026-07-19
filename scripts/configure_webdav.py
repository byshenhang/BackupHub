"""从 .env 创建或更新 WebDAV 存储目标。"""

import json

from app.config import settings
from app.core.crypto import encrypt
from app.db.models import StorageTarget, StorageType
from app.db.session import Base, SessionLocal, engine


STORAGE_NAME = "GithubSync"


def configure():
    required = {
        "WEBDAV_URL": settings.WEBDAV_URL,
        "WEBDAV_USERNAME": settings.WEBDAV_USERNAME,
        "WEBDAV_PASSWORD": settings.WEBDAV_PASSWORD,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f".env 缺少配置：{', '.join(missing)}")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        target = db.query(StorageTarget).filter(
            StorageTarget.name == STORAGE_NAME
        ).first()
        if target is None:
            target = StorageTarget(name=STORAGE_NAME)
            db.add(target)

        storage_config = {
            "url": settings.WEBDAV_URL,
            "username": settings.WEBDAV_USERNAME,
            "password": settings.WEBDAV_PASSWORD,
            "remote_path": settings.WEBDAV_REMOTE_PATH,
            "verify_ssl": True,
        }
        target.storage_type = StorageType.WEBDAV
        target.config = encrypt(json.dumps(storage_config, ensure_ascii=False))
        db.commit()
        print(f"Configured WebDAV storage: id={target.id}, name={target.name}")
    finally:
        db.close()


if __name__ == "__main__":
    configure()
