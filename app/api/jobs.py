"""任务相关 API 接口。

提供任务的 CRUD 操作和手动触发功能。
"""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import require_auth
from app.db.session import get_db
from app.db.models import BackupJob, JobType
from app.core.scheduler import (
    add_job_to_scheduler,
    remove_job_from_scheduler,
    update_job_in_scheduler,
    trigger_job_now,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_auth)])

# 线程池用于异步执行手动触发的备份任务
_executor = ThreadPoolExecutor(max_workers=4)


# --- Pydantic 模型 ---

class JobCreate(BaseModel):
    name: str
    job_type: str  # "git", "file", "database"
    cron_expression: str = "0 2 * * *"
    enabled: bool = True
    config: dict = {}
    storage_target_id: Optional[int] = None
    retention_days: int = 30


class JobUpdate(BaseModel):
    name: Optional[str] = None
    job_type: Optional[str] = None
    cron_expression: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None
    storage_target_id: Optional[int] = None
    retention_days: Optional[int] = None


class JobResponse(BaseModel):
    id: int
    name: str
    job_type: str
    cron_expression: str
    enabled: bool
    config: dict
    storage_target_id: Optional[int]
    retention_days: int
    created_at: Optional[str]
    updated_at: Optional[str]
    last_run_status: Optional[str] = None
    next_run_time: Optional[str] = None

    class Config:
        from_attributes = True


# --- 接口 ---

@router.get("", response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    """获取所有任务列表。"""
    from app.core.scheduler import get_next_run_time

    jobs = db.query(BackupJob).order_by(BackupJob.created_at.desc()).all()
    result = []
    for job in jobs:
        # 获取最近一次执行状态
        last_run = job.runs[0] if job.runs else None
        last_status = last_run.status.value if last_run else None

        # 获取下次执行时间
        next_run = get_next_run_time(job.id)
        next_run_str = next_run.isoformat() if next_run else None

        result.append(JobResponse(
            id=job.id,
            name=job.name,
            job_type=job.job_type.value,
            cron_expression=job.cron_expression,
            enabled=job.enabled,
            config=json.loads(job.config) if job.config else {},
            storage_target_id=job.storage_target_id,
            retention_days=job.retention_days,
            created_at=job.created_at.isoformat() if job.created_at else None,
            updated_at=job.updated_at.isoformat() if job.updated_at else None,
            last_run_status=last_status,
            next_run_time=next_run_str,
        ))
    return result


@router.post("", response_model=JobResponse)
def create_job(data: JobCreate, db: Session = Depends(get_db)):
    """创建新的备份任务。"""
    # 验证任务类型
    try:
        job_type = JobType(data.job_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"不支持的任务类型：{data.job_type}")

    job = BackupJob(
        name=data.name,
        job_type=job_type,
        cron_expression=data.cron_expression,
        enabled=data.enabled,
        config=json.dumps(data.config, ensure_ascii=False),
        storage_target_id=data.storage_target_id,
        retention_days=data.retention_days,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 添加到调度器
    if job.enabled:
        add_job_to_scheduler(job.id, job.cron_expression, job.name)

    return JobResponse(
        id=job.id,
        name=job.name,
        job_type=job.job_type.value,
        cron_expression=job.cron_expression,
        enabled=job.enabled,
        config=data.config,
        storage_target_id=job.storage_target_id,
        retention_days=job.retention_days,
        created_at=job.created_at.isoformat() if job.created_at else None,
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
    )


@router.put("/{job_id}", response_model=JobResponse)
def update_job(job_id: int, data: JobUpdate, db: Session = Depends(get_db)):
    """编辑任务。"""
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")

    if data.name is not None:
        job.name = data.name
    if data.job_type is not None:
        try:
            job.job_type = JobType(data.job_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"不支持的任务类型：{data.job_type}")
    if data.cron_expression is not None:
        job.cron_expression = data.cron_expression
    if data.enabled is not None:
        job.enabled = data.enabled
    if data.config is not None:
        job.config = json.dumps(data.config, ensure_ascii=False)
    if data.storage_target_id is not None:
        job.storage_target_id = data.storage_target_id
    if data.retention_days is not None:
        job.retention_days = data.retention_days

    db.commit()
    db.refresh(job)

    # 更新调度器
    update_job_in_scheduler(job.id, job.cron_expression, job.name, job.enabled)

    return JobResponse(
        id=job.id,
        name=job.name,
        job_type=job.job_type.value,
        cron_expression=job.cron_expression,
        enabled=job.enabled,
        config=json.loads(job.config) if job.config else {},
        storage_target_id=job.storage_target_id,
        retention_days=job.retention_days,
        created_at=job.created_at.isoformat() if job.created_at else None,
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
    )


@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    """删除任务。"""
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")

    # 从调度器移除
    remove_job_from_scheduler(job_id)

    # 删除关联的执行记录
    from app.db.models import ExecutionRecord
    db.query(ExecutionRecord).filter(ExecutionRecord.job_id == job_id).delete()

    db.delete(job)
    db.commit()

    return {"message": f"任务 {job.name} 已删除。"}


@router.post("/{job_id}/run")
def run_job_now(job_id: int, db: Session = Depends(get_db)):
    """手动立即触发任务执行。"""
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")

    # 异步执行，不阻塞请求
    _executor.submit(trigger_job_now, job_id)

    return {"message": f"任务 {job.name} 已触发执行。"}


@router.patch("/{job_id}/toggle")
def toggle_job(job_id: int, db: Session = Depends(get_db)):
    """启用/停用任务。"""
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")

    job.enabled = not job.enabled
    db.commit()

    # 更新调度器
    update_job_in_scheduler(job.id, job.cron_expression, job.name, job.enabled)

    status = "启用" if job.enabled else "停用"
    return {"message": f"任务 {job.name} 已{status}。", "enabled": job.enabled}
