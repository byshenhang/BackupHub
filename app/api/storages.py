"""存储目标相关 API 接口。

提供存储目标的 CRUD 操作，凭证信息加密存储。
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt
from app.db.session import get_db
from app.db.models import StorageTarget, StorageType

router = APIRouter(prefix="/api/storages", tags=["storages"])


# --- Pydantic 模型 ---

class StorageCreate(BaseModel):
    name: str
    storage_type: str  # "local", "oss", "cos", "webdav"
    config: dict = {}


class StorageUpdate(BaseModel):
    name: Optional[str] = None
    storage_type: Optional[str] = None
    config: Optional[dict] = None


class StorageResponse(BaseModel):
    id: int
    name: str
    storage_type: str
    config: dict  # 返回时解密
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


# --- 接口 ---

@router.get("", response_model=list[StorageResponse])
def list_storages(db: Session = Depends(get_db)):
    """获取所有存储目标列表。"""
    targets = db.query(StorageTarget).order_by(StorageTarget.created_at.desc()).all()
    result = []
    for t in targets:
        try:
            config = json.loads(decrypt(t.config)) if t.config else {}
        except Exception:
            config = {"error": "解密失败"}

        result.append(StorageResponse(
            id=t.id,
            name=t.name,
            storage_type=t.storage_type.value,
            config=config,
            created_at=t.created_at.isoformat() if t.created_at else None,
            updated_at=t.updated_at.isoformat() if t.updated_at else None,
        ))
    return result


@router.post("", response_model=StorageResponse)
def create_storage(data: StorageCreate, db: Session = Depends(get_db)):
    """创建新的存储目标。"""
    try:
        storage_type = StorageType(data.storage_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"不支持的存储类型：{data.storage_type}")

    # 加密配置
    encrypted_config = encrypt(json.dumps(data.config, ensure_ascii=False))

    target = StorageTarget(
        name=data.name,
        storage_type=storage_type,
        config=encrypted_config,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    return StorageResponse(
        id=target.id,
        name=target.name,
        storage_type=target.storage_type.value,
        config=data.config,
        created_at=target.created_at.isoformat() if target.created_at else None,
        updated_at=target.updated_at.isoformat() if target.updated_at else None,
    )


@router.put("/{storage_id}", response_model=StorageResponse)
def update_storage(storage_id: int, data: StorageUpdate, db: Session = Depends(get_db)):
    """编辑存储目标。"""
    target = db.query(StorageTarget).get(storage_id)
    if not target:
        raise HTTPException(status_code=404, detail="存储目标不存在。")

    if data.name is not None:
        target.name = data.name
    if data.storage_type is not None:
        try:
            target.storage_type = StorageType(data.storage_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"不支持的存储类型：{data.storage_type}")
    if data.config is not None:
        target.config = encrypt(json.dumps(data.config, ensure_ascii=False))

    db.commit()
    db.refresh(target)

    # 返回时解密
    try:
        config = json.loads(decrypt(target.config)) if target.config else {}
    except Exception:
        config = {"error": "解密失败"}

    return StorageResponse(
        id=target.id,
        name=target.name,
        storage_type=target.storage_type.value,
        config=config,
        created_at=target.created_at.isoformat() if target.created_at else None,
        updated_at=target.updated_at.isoformat() if target.updated_at else None,
    )


@router.delete("/{storage_id}")
def delete_storage(storage_id: int, db: Session = Depends(get_db)):
    """删除存储目标。"""
    target = db.query(StorageTarget).get(storage_id)
    if not target:
        raise HTTPException(status_code=404, detail="存储目标不存在。")

    # 检查是否有关联的任务
    from app.db.models import BackupJob
    jobs_count = db.query(BackupJob).filter(BackupJob.storage_target_id == storage_id).count()
    if jobs_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该存储目标被 {jobs_count} 个任务关联，请先解除关联后再删除。"
        )

    db.delete(target)
    db.commit()

    return {"message": f"存储目标 {target.name} 已删除。"}
