"""页面路由。

FastAPI 渲染 Jinja2 模板返回 HTML 页面。
"""

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.auth import require_auth
from app.db.session import get_db
from app.db.models import BackupJob, ExecutionRecord, RunStatus, StorageTarget

router = APIRouter(tags=["pages"], dependencies=[Depends(require_auth)])

templates = Jinja2Templates(directory="app/web/templates")


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """首页 / 仪表盘。"""
    jobs_count = db.query(BackupJob).count()
    enabled_count = db.query(BackupJob).filter(BackupJob.enabled == True).count()
    runs_count = db.query(ExecutionRecord).count()
    success_count = db.query(ExecutionRecord).filter(
        ExecutionRecord.status == RunStatus.SUCCESS
    ).count()
    failed_count = db.query(ExecutionRecord).filter(
        ExecutionRecord.status == RunStatus.FAILED
    ).count()
    storages_count = db.query(StorageTarget).count()

    # 最近 5 条执行记录
    recent_runs = db.query(ExecutionRecord).order_by(
        ExecutionRecord.created_at.desc()
    ).limit(5).all()

    return templates.TemplateResponse(request, "index.html", {
        "jobs_count": jobs_count,
        "enabled_count": enabled_count,
        "runs_count": runs_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "storages_count": storages_count,
        "recent_runs": recent_runs,
    })


@router.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, db: Session = Depends(get_db)):
    """任务列表页面。"""
    jobs = db.query(BackupJob).order_by(BackupJob.created_at.desc()).all()
    return templates.TemplateResponse(request, "jobs.html", {"jobs": jobs})


@router.get("/jobs/new", response_class=HTMLResponse)
def job_new_page(request: Request, db: Session = Depends(get_db)):
    """新建任务页面。"""
    storages = db.query(StorageTarget).all()
    return templates.TemplateResponse(request, "job_form.html", {
        "job": None,
        "storages": storages,
    })


@router.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
def job_edit_page(request: Request, job_id: int, db: Session = Depends(get_db)):
    """编辑任务页面。"""
    job = db.query(BackupJob).get(job_id)
    if not job:
        return HTMLResponse("任务不存在", status_code=404)
    storages = db.query(StorageTarget).all()
    return templates.TemplateResponse(request, "job_form.html", {
        "job": job,
        "storages": storages,
    })


@router.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request, db: Session = Depends(get_db)):
    """执行历史页面。"""
    runs = db.query(ExecutionRecord).order_by(
        ExecutionRecord.created_at.desc()
    ).limit(100).all()
    return templates.TemplateResponse(request, "runs.html", {"runs": runs})


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail_page(request: Request, run_id: int, db: Session = Depends(get_db)):
    """执行详情页面。"""
    run = db.query(ExecutionRecord).get(run_id)
    if not run:
        return HTMLResponse("执行记录不存在", status_code=404)
    return templates.TemplateResponse(request, "run_detail.html", {"run": run})


@router.get("/storages", response_class=HTMLResponse)
def storages_page(request: Request, db: Session = Depends(get_db)):
    """存储目标管理页面。"""
    from app.core.crypto import decrypt
    storages_raw = db.query(StorageTarget).order_by(StorageTarget.created_at.desc()).all()
    # 解密配置以便模板展示
    storages = []
    for s in storages_raw:
        try:
            config = json.loads(decrypt(s.config)) if s.config else {}
        except Exception:
            config = {"error": "解密失败"}
        storages.append({
            "id": s.id,
            "name": s.name,
            "storage_type": s.storage_type,
            "config": config,
            "created_at": s.created_at,
        })
    return templates.TemplateResponse(request, "storages.html", {"storages": storages})
