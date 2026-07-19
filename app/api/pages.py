"""页面路由。

FastAPI 渲染 Jinja2 模板返回 HTML 页面。
"""

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.auth import require_auth
from app.api.storages import sanitize_storage_config
from app.core.crypto import decrypt
from app.db.session import get_db
from app.core.app_settings import get_github_token_status
from app.core.scheduler import get_next_run_time
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
    next_runs = {job.id: get_next_run_time(job.id) for job in jobs}
    return templates.TemplateResponse(request, "jobs.html", {
        "jobs": jobs,
        "next_runs": next_runs,
    })


@router.get("/jobs/new", response_class=HTMLResponse)
def job_new_page(request: Request, db: Session = Depends(get_db)):
    """新建任务页面。"""
    storages = db.query(StorageTarget).all()
    return templates.TemplateResponse(request, "job_form.html", {
        "job": None,
        "job_config": {},
        "storages": storages,
    })


@router.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
def job_edit_page(request: Request, job_id: int, db: Session = Depends(get_db)):
    """编辑任务页面。"""
    job = db.query(BackupJob).get(job_id)
    if not job:
        return HTMLResponse("任务不存在", status_code=404)
    storages = db.query(StorageTarget).all()
    try:
        job_config = json.loads(job.config) if job.config else {}
    except (TypeError, json.JSONDecodeError):
        job_config = {}
    return templates.TemplateResponse(request, "job_form.html", {
        "job": job,
        "job_config": job_config,
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
    run = db.get(ExecutionRecord, run_id)
    if not run:
        return HTMLResponse("执行记录不存在", status_code=404)
    return templates.TemplateResponse(request, "run_detail.html", {"run": run})


@router.get("/storages", response_class=HTMLResponse)
def storages_page(request: Request, db: Session = Depends(get_db)):
    """存储目标管理页面。"""
    storages_raw = db.query(StorageTarget).order_by(StorageTarget.created_at.desc()).all()
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
            "config": sanitize_storage_config(config),
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        })
    return templates.TemplateResponse(request, "storages.html", {"storages": storages})


@router.get("/storages/new", response_class=HTMLResponse)
def storage_new_page(request: Request):
    return templates.TemplateResponse(request, "storage_form.html", {
        "storage": None,
        "storage_config": {},
    })


@router.get("/storages/{storage_id}/edit", response_class=HTMLResponse)
def storage_edit_page(
    request: Request,
    storage_id: int,
    db: Session = Depends(get_db),
):
    storage = db.get(StorageTarget, storage_id)
    if storage is None:
        return HTMLResponse("存储目标不存在", status_code=404)
    try:
        config = json.loads(decrypt(storage.config)) if storage.config else {}
    except Exception:
        config = {}
    return templates.TemplateResponse(request, "storage_form.html", {
        "storage": storage,
        "storage_config": sanitize_storage_config(config),
    })


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    """应用设置页面。"""
    job = db.query(BackupJob).order_by(BackupJob.created_at.asc()).first()
    repository_url = ""
    if job and job.config:
        try:
            repository_url = json.loads(job.config).get("repository_url", "")
        except (TypeError, json.JSONDecodeError):
            pass
    return templates.TemplateResponse(request, "settings.html", {
        "github_status": get_github_token_status(db),
        "repository_url": repository_url,
    })
