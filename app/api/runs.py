"""执行记录相关 API 接口。

提供执行历史的查询功能。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import require_auth
from app.db.session import get_db
from app.db.models import ExecutionRecord, RunStatus

router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(require_auth)])


# --- Pydantic 模型 ---

class RunResponse(BaseModel):
    id: int
    job_id: int
    job_name: Optional[str] = None
    status: str
    started_at: Optional[str]
    finished_at: Optional[str]
    duration_seconds: Optional[int]
    artifact_size: Optional[int]
    remote_path: Optional[str]
    trigger_source: Optional[str]
    error_message: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class RunDetailResponse(RunResponse):
    log: Optional[str] = None


# --- 接口 ---

@router.get("", response_model=list[RunResponse])
def list_runs(
    job_id: Optional[int] = Query(None, description="按任务 ID 筛选"),
    status: Optional[str] = Query(None, description="按状态筛选：running/success/failed"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: Session = Depends(get_db),
):
    """获取执行历史列表。"""
    query = db.query(ExecutionRecord)

    if job_id is not None:
        query = query.filter(ExecutionRecord.job_id == job_id)
    if status is not None:
        try:
            query = query.filter(ExecutionRecord.status == RunStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值：{status}")

    records = query.order_by(ExecutionRecord.created_at.desc()).offset(offset).limit(limit).all()

    return [
        RunResponse(
            id=r.id,
            job_id=r.job_id,
            job_name=r.job.name if r.job else None,
            status=r.status.value,
            started_at=r.started_at.isoformat() if r.started_at else None,
            finished_at=r.finished_at.isoformat() if r.finished_at else None,
            duration_seconds=r.duration_seconds,
            artifact_size=r.artifact_size,
            remote_path=r.remote_path,
            trigger_source=r.trigger_source.value if r.trigger_source else None,
            error_message=r.error_message,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in records
    ]


@router.get("/{run_id}", response_model=RunDetailResponse)
def get_run_detail(run_id: int, db: Session = Depends(get_db)):
    """获取单条执行记录详情（含日志）。"""
    record = db.query(ExecutionRecord).get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="执行记录不存在。")

    return RunDetailResponse(
        id=record.id,
        job_id=record.job_id,
        job_name=record.job.name if record.job else None,
        status=record.status.value,
        started_at=record.started_at.isoformat() if record.started_at else None,
        finished_at=record.finished_at.isoformat() if record.finished_at else None,
        duration_seconds=record.duration_seconds,
        artifact_size=record.artifact_size,
        remote_path=record.remote_path,
        trigger_source=record.trigger_source.value if record.trigger_source else None,
        error_message=record.error_message,
        log=record.log,
        created_at=record.created_at.isoformat() if record.created_at else None,
    )
