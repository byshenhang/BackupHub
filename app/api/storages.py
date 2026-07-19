"""存储目标 CRUD、凭证保护和连接测试。"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import require_auth
from app.core.crypto import decrypt, encrypt
from app.db.models import StorageTarget, StorageType
from app.db.session import get_db
from app.storages.registry import get_storage


router = APIRouter(
    prefix="/api/storages",
    tags=["storages"],
    dependencies=[Depends(require_auth)],
)

SECRET_FIELDS = {"password", "access_key_secret"}
REQUIRED_FIELDS = {
    StorageType.LOCAL: {"path"},
    StorageType.OSS: {
        "access_key_id",
        "access_key_secret",
        "endpoint",
        "bucket",
    },
    StorageType.WEBDAV: {"url", "username", "password"},
}


class StorageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    storage_type: str
    config: dict = Field(default_factory=dict)


class StorageUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    storage_type: Optional[str] = None
    config: Optional[dict] = None


class StorageResponse(BaseModel):
    id: int
    name: str
    storage_type: str
    config: dict
    created_at: Optional[str]
    updated_at: Optional[str]


class StorageTestRequest(BaseModel):
    storage_id: Optional[int] = None
    storage_type: Optional[str] = None
    config: dict = Field(default_factory=dict)


def sanitize_storage_config(config: dict) -> dict:
    safe = dict(config)
    for field in SECRET_FIELDS:
        configured = bool(safe.pop(field, None))
        safe[f"{field}_configured"] = configured
    return safe


def _validate_storage_config(storage_type: StorageType, config: dict):
    missing = [
        field
        for field in REQUIRED_FIELDS.get(storage_type, set())
        if not str(config.get(field, "")).strip()
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"存储配置缺少字段：{', '.join(sorted(missing))}",
        )


def _merge_storage_config(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    for key, value in incoming.items():
        if key in SECRET_FIELDS and not value:
            continue
        merged[key] = value
    return merged


def _decrypt_target_config(target: StorageTarget) -> dict:
    try:
        return json.loads(decrypt(target.config)) if target.config else {}
    except Exception:
        raise HTTPException(status_code=500, detail="存储配置解密失败。")


def _storage_response(target: StorageTarget, config: dict) -> StorageResponse:
    return StorageResponse(
        id=target.id,
        name=target.name,
        storage_type=target.storage_type.value,
        config=sanitize_storage_config(config),
        created_at=target.created_at.isoformat() if target.created_at else None,
        updated_at=target.updated_at.isoformat() if target.updated_at else None,
    )


def _test_storage_config(storage_type: StorageType, config: dict):
    _validate_storage_config(storage_type, config)
    try:
        get_storage(storage_type.value).test_connection(config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"连接测试失败：{exc}")


@router.get("", response_model=list[StorageResponse])
def list_storages(db: Session = Depends(get_db)):
    targets = db.query(StorageTarget).order_by(StorageTarget.created_at.desc()).all()
    return [
        _storage_response(target, _decrypt_target_config(target))
        for target in targets
    ]


@router.post("", response_model=StorageResponse)
def create_storage(data: StorageCreate, db: Session = Depends(get_db)):
    try:
        storage_type = StorageType(data.storage_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="不支持的存储类型。")

    _validate_storage_config(storage_type, data.config)
    target = StorageTarget(
        name=data.name,
        storage_type=storage_type,
        config=encrypt(json.dumps(data.config, ensure_ascii=False)),
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return _storage_response(target, data.config)


@router.put("/{storage_id}", response_model=StorageResponse)
def update_storage(
    storage_id: int,
    data: StorageUpdate,
    db: Session = Depends(get_db),
):
    target = db.get(StorageTarget, storage_id)
    if target is None:
        raise HTTPException(status_code=404, detail="存储目标不存在。")

    original_type = target.storage_type
    if data.name is not None:
        target.name = data.name
    if data.storage_type is not None:
        try:
            target.storage_type = StorageType(data.storage_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="不支持的存储类型。")

    existing = (
        _decrypt_target_config(target)
        if target.storage_type == original_type
        else {}
    )
    merged = _merge_storage_config(existing, data.config or {})
    _validate_storage_config(target.storage_type, merged)
    target.config = encrypt(json.dumps(merged, ensure_ascii=False))

    db.commit()
    db.refresh(target)
    return _storage_response(target, merged)


@router.post("/test")
def test_storage(data: StorageTestRequest, db: Session = Depends(get_db)):
    existing = {}
    if data.storage_id is not None:
        target = db.get(StorageTarget, data.storage_id)
        if target is None:
            raise HTTPException(status_code=404, detail="存储目标不存在。")
        storage_type = target.storage_type
        existing = _decrypt_target_config(target)
    elif data.storage_type is not None:
        try:
            storage_type = StorageType(data.storage_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="不支持的存储类型。")
    else:
        raise HTTPException(status_code=400, detail="缺少存储类型或存储目标 ID。")

    config = _merge_storage_config(existing, data.config)
    _test_storage_config(storage_type, config)
    return {"ok": True, "message": "存储连接测试成功。"}


@router.post("/{storage_id}/test")
def test_saved_storage(storage_id: int, db: Session = Depends(get_db)):
    target = db.get(StorageTarget, storage_id)
    if target is None:
        raise HTTPException(status_code=404, detail="存储目标不存在。")
    _test_storage_config(target.storage_type, _decrypt_target_config(target))
    return {"ok": True, "message": "存储连接测试成功。"}


@router.delete("/{storage_id}")
def delete_storage(storage_id: int, db: Session = Depends(get_db)):
    target = db.get(StorageTarget, storage_id)
    if target is None:
        raise HTTPException(status_code=404, detail="存储目标不存在。")

    from app.db.models import BackupJob

    jobs_count = db.query(BackupJob).filter(
        BackupJob.storage_target_id == storage_id
    ).count()
    if jobs_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该存储目标被 {jobs_count} 个任务关联，请先解除关联。",
        )

    db.delete(target)
    db.commit()
    return {"message": f"存储目标 {target.name} 已删除。"}
