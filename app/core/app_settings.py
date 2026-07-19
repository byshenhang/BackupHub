"""应用级加密设置读写。"""

from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt, encrypt
from app.db.models import AppSetting


GITHUB_TOKEN_KEY = "github_token"


def get_secret(db: Session, key: str) -> str:
    setting = db.get(AppSetting, key)
    if setting is None:
        return ""
    return decrypt(setting.encrypted_value)


def set_secret(db: Session, key: str, value: str) -> AppSetting:
    value = value.strip()
    if not value:
        raise ValueError("密钥不能为空。")

    setting = db.get(AppSetting, key)
    if setting is None:
        setting = AppSetting(key=key, encrypted_value="")
        db.add(setting)
    setting.encrypted_value = encrypt(value)
    db.commit()
    db.refresh(setting)
    return setting


def delete_secret(db: Session, key: str) -> bool:
    setting = db.get(AppSetting, key)
    if setting is None:
        return False
    db.delete(setting)
    db.commit()
    return True


def get_github_token(db: Session) -> str:
    return get_secret(db, GITHUB_TOKEN_KEY) or settings.GITHUB_TOKEN


def get_github_token_status(db: Session) -> dict:
    setting = db.get(AppSetting, GITHUB_TOKEN_KEY)
    if setting is not None:
        return {
            "configured": True,
            "source": "database",
            "updated_at": (
                setting.updated_at.isoformat() if setting.updated_at else None
            ),
        }
    return {
        "configured": bool(settings.GITHUB_TOKEN),
        "source": "environment" if settings.GITHUB_TOKEN else None,
        "updated_at": None,
    }
