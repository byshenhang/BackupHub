"""任务相关 API 接口。

提供任务的 CRUD 操作和手动触发功能。
"""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.api.auth import require_auth
from app.db.session import get_db
from app.db.models import BackupJob, ExecutionRecord, JobType, RunStatus, StorageTarget
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
    name: str = Field(min_length=1, max_length=200)
    job_type: str  # "git", "file", "database"
    cron_expression: str = "0 2 * * *"
    enabled: bool = True
    config: dict = Field(default_factory=dict)
    storage_target_id: Optional[int] = None
    retention_days: int = Field(default=30, ge=0, le=3650)


class JobUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    job_type: Optional[str] = None
    cron_expression: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None
    storage_target_id: Optional[int] = None
    retention_days: Optional[int] = Field(default=None, ge=0, le=3650)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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



# --- 接口 ---

def _safe_job_config(config: dict) -> dict:
    safe = dict(config)
    for key in {"gitlab_token", "github_token", "_github_token", "ssh_key"}:
        safe.pop(key, None)
    return safe


def _validate_cron(cron_expression: str):
    try:
        CronTrigger.from_crontab(cron_expression)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"无效的 cron 表达式：{exc}")


def _validate_storage_target(db: Session, storage_target_id: int | None):
    if storage_target_id is not None and db.get(StorageTarget, storage_target_id) is None:
        raise HTTPException(status_code=400, detail="选择的存储目标不存在。")


def _normalize_job_config(job_type: JobType, config: dict) -> dict:
    if job_type is not JobType.GIT:
        raise HTTPException(status_code=400, detail=f"任务类型 {job_type.value} 尚未实现。")

    normalized = dict(config)
    source_mode = normalized.get("source_mode")
    if not source_mode:
        source_mode = "single" if normalized.get("repository_url") else "gitlab"
    if source_mode not in {"single", "gitlab"}:
        raise HTTPException(status_code=400, detail="无效的 Git 来源模式。")

    normalized["source_mode"] = source_mode
    if source_mode == "single":
        repository_url = str(normalized.get("repository_url", "")).strip()
        parsed = urlparse(repository_url)
        is_ssh = repository_url.startswith("git@")
        if not is_ssh and (
            parsed.scheme not in {"http", "https", "ssh"} or not parsed.path
        ):
            raise HTTPException(status_code=400, detail="请输入有效的 Git 仓库 URL。")
        normalized["repository_url"] = repository_url
        normalized.pop("gitlab_url", None)
        normalized.pop("gitlab_token", None)
    else:
        gitlab_url = str(normalized.get("gitlab_url", "")).strip()
        if not gitlab_url:
            raise HTTPException(status_code=400, detail="GitLab URL 不能为空。")
        normalized["gitlab_url"] = gitlab_url.rstrip("/")
        normalized.pop("repository_url", None)

    return normalized


def _job_response(job: BackupJob) -> JobResponse:
    return JobResponse(
        id=job.id,
        name=job.name,
        job_type=job.job_type.value,
        cron_expression=job.cron_expression,
        enabled=job.enabled,
        config=_safe_job_config(json.loads(job.config) if job.config else {}),
        storage_target_id=job.storage_target_id,
        retention_days=job.retention_days,
        created_at=job.created_at.isoformat() if job.created_at else None,
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
    )

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
            config=_safe_job_config(json.loads(job.config) if job.config else {}),
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

    _validate_cron(data.cron_expression)
    _validate_storage_target(db, data.storage_target_id)
    job_config = _normalize_job_config(job_type, data.config)

    job = BackupJob(
        name=data.name,
        job_type=job_type,
        cron_expression=data.cron_expression,
        enabled=data.enabled,
        config=json.dumps(job_config, ensure_ascii=False),
        storage_target_id=data.storage_target_id,
        retention_days=data.retention_days,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 添加到调度器
    if job.enabled:
        add_job_to_scheduler(job.id, job.cron_expression, job.name)

    return _job_response(job)


@router.put("/{job_id}", response_model=JobResponse)
def update_job(job_id: int, data: JobUpdate, db: Session = Depends(get_db)):
    """编辑任务。"""
    job = db.get(BackupJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")

    existing_config = json.loads(job.config) if job.config else {}

    if data.name is not None:
        job.name = data.name
    if data.job_type is not None:
        try:
            job.job_type = JobType(data.job_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"不支持的任务类型：{data.job_type}")
    if data.cron_expression is not None:
        _validate_cron(data.cron_expression)
        job.cron_expression = data.cron_expression
    if data.enabled is not None:
        job.enabled = data.enabled
    incoming_config = dict(data.config) if data.config is not None else dict(existing_config)
    for secret_key in {"gitlab_token", "ssh_key"}:
        if not incoming_config.get(secret_key) and existing_config.get(secret_key):
            incoming_config[secret_key] = existing_config[secret_key]
    job.config = json.dumps(
        _normalize_job_config(job.job_type, incoming_config),
        ensure_ascii=False,
    )
    if "storage_target_id" in data.model_fields_set:
        _validate_storage_target(db, data.storage_target_id)
        job.storage_target_id = data.storage_target_id
    if data.retention_days is not None:
        job.retention_days = data.retention_days

    db.commit()
    db.refresh(job)

    # 更新调度器
    update_job_in_scheduler(job.id, job.cron_expression, job.name, job.enabled)

    return _job_response(job)


@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    """删除任务。"""
    job = db.get(BackupJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")

    # 从调度器移除
    remove_job_from_scheduler(job_id)

    # 删除关联的执行记录
    db.query(ExecutionRecord).filter(ExecutionRecord.job_id == job_id).delete()

    db.delete(job)
    db.commit()

    return {"message": f"任务 {job.name} 已删除。"}


@router.post("/{job_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_job_now(job_id: int, db: Session = Depends(get_db)):
    """手动立即触发任务执行。"""
    job = db.get(BackupJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")

    running = db.query(ExecutionRecord).filter(
        ExecutionRecord.job_id == job_id,
        ExecutionRecord.status == RunStatus.RUNNING,
    ).first()
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"任务已有运行中的执行记录 #{running.id}。",
        )

    # 异步执行，不阻塞请求
    _executor.submit(trigger_job_now, job_id)

    return {"message": f"任务 {job.name} 已触发执行。"}


@router.patch("/{job_id}/toggle")
def toggle_job(job_id: int, db: Session = Depends(get_db)):
    """启用/停用任务。"""
    job = db.get(BackupJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")

    if not job.enabled:
        _validate_cron(job.cron_expression)
    job.enabled = not job.enabled
    db.commit()

    # 更新调度器
    update_job_in_scheduler(job.id, job.cron_expression, job.name, job.enabled)

    status = "启用" if job.enabled else "停用"
    return {"message": f"任务 {job.name} 已{status}。", "enabled": job.enabled}
