"""执行编排模块。

串联执行器与上传器，完成一次完整的备份执行流程：
1. 创建执行记录（状态=运行中）
2. 选取执行器执行备份，产出本地文件
3. 选取上传器上传产物到存储目标
4. 执行保留策略清理旧备份
5. 更新执行记录状态
"""

import json
import logging
import re
import shutil
import subprocess
import tempfile
import threading
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.core.app_settings import get_github_token
from app.core.crypto import decrypt
from app.db.models import BackupJob, ExecutionRecord, RunStatus, TriggerSource, StorageTarget
from app.executors.registry import get_executor
from app.storages.registry import get_storage

logger = logging.getLogger("backup-hub.runner")
_job_locks: dict[int, threading.Lock] = {}
_job_locks_guard = threading.Lock()


def _redact_sensitive_text(value: str) -> str:
    value = re.sub(r"(?i)(https?://)[^/@\s]+@", r"\1***@", value)
    return re.sub(
        r"(?i)(github_pat_|gh[pousr]_|glpat-)[A-Za-z0-9_-]+",
        r"\1***",
        value,
    )


def _exception_summary(error: Exception) -> str:
    message = str(error)
    if isinstance(error, subprocess.CalledProcessError):
        command_output = (error.stderr or error.stdout or "").strip()
        if command_output:
            message = f"{message}\n{command_output[-4000:]}"
    return _redact_sensitive_text(message)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_job_lock(job_id: int) -> threading.Lock:
    with _job_locks_guard:
        return _job_locks.setdefault(job_id, threading.Lock())


def run_backup_job(job_id: int, trigger_source: str = "scheduled"):
    """执行一次备份任务（在线程池中运行）。

    Args:
        job_id: 任务 ID
        trigger_source: 触发来源（"scheduled" 或 "manual"）
    """
    from app.db.session import SessionLocal

    job_lock = _get_job_lock(job_id)
    if not job_lock.acquire(blocking=False):
        logger.warning(f"任务 {job_id} 已在当前进程执行，跳过本次触发。")
        return None

    db = SessionLocal()
    record = None
    record_id = None
    work_dir = None
    keep_local_artifact = False
    log_buffer = []

    try:
        # 获取任务
        job = db.get(BackupJob, job_id)
        if not job:
            logger.error(f"任务 {job_id} 不存在。")
            return

        # 并发保护：检查是否有正在运行的执行记录
        running = db.query(ExecutionRecord).filter(
            ExecutionRecord.job_id == job_id,
            ExecutionRecord.status == RunStatus.RUNNING,
        ).first()
        if running:
            logger.warning(f"任务 {job.name} 已有执行中的记录（#{running.id}），跳过本次触发。")
            return

        # 1. 创建执行记录
        record = ExecutionRecord(
            job_id=job_id,
            status=RunStatus.RUNNING,
            trigger_source=TriggerSource(trigger_source),
            started_at=_utcnow(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        record_id = record.id

        log_buffer.append(f"=== 备份任务开始：{job.name} ===")
        log_buffer.append(f"触发方式：{trigger_source}")
        log_buffer.append(f"开始时间：{record.started_at}")

        # 2. 解析任务配置
        job_config = json.loads(job.config) if job.config else {}
        if job_config.get("repository_url"):
            job_config["_github_token"] = get_github_token(db)

        # 3. 执行备份
        log_buffer.append(f"任务类型：{job.job_type}")
        log_buffer.append("正在执行备份...")

        executor = get_executor(job.job_type.value)
        work_dir = Path(tempfile.mkdtemp(dir=settings.TEMP_DIR))

        artifact_path = executor.execute(job_config, work_dir)
        artifact_size = artifact_path.stat().st_size
        log_buffer.append(f"备份完成，产物：{artifact_path.name}（{artifact_size} 字节）")

        # 4. 上传到存储目标
        remote_path = ""
        if job.storage_target:
            storage_target = db.get(StorageTarget, job.storage_target_id)
            if storage_target:
                storage_config = json.loads(decrypt(storage_target.config))
                storage = get_storage(storage_target.storage_type.value)
                remote_key = f"{job.name}/{artifact_path.name}"
                log_buffer.append(f"正在上传到 {storage_target.name}...")
                remote_path = storage.upload(artifact_path, remote_key, storage_config)
                log_buffer.append(f"上传完成：{remote_path}")
            else:
                log_buffer.append("警告：关联的存储目标不存在，跳过上传。")
        else:
            remote_path = str(artifact_path)
            keep_local_artifact = True
            log_buffer.append(f"未配置存储目标，产物保留在本地：{remote_path}")

        # 5. 保留策略清理
        if job.storage_target and remote_path:
            _cleanup_old_backups(db, job, log_buffer)

        # 6. 更新执行记录
        finished_at = _utcnow()
        duration = int((finished_at - record.started_at).total_seconds())

        record.status = RunStatus.SUCCESS
        record.finished_at = finished_at
        record.duration_seconds = duration
        record.artifact_size = artifact_size
        record.remote_path = remote_path
        record.log = "\n".join(log_buffer)

        db.commit()
        logger.info(f"任务 {job.name} 执行成功，耗时 {duration} 秒。")

    except Exception as e:
        error_summary = _exception_summary(e)
        error_msg = (
            f"{type(e).__name__}: {error_summary}\n"
            f"{_redact_sensitive_text(traceback.format_exc())}"
        )
        logger.error(f"任务执行失败：{error_msg}")

        if record:
            record.status = RunStatus.FAILED
            record.finished_at = _utcnow()
            record.duration_seconds = int((record.finished_at - record.started_at).total_seconds())
            record.error_message = error_summary
            record.log = "\n".join(log_buffer + ["", f"错误：{error_msg}"])
            db.commit()

    finally:
        if work_dir is not None and not keep_local_artifact:
            shutil.rmtree(work_dir, ignore_errors=True)
        db.close()
        job_lock.release()

    return record_id


def _cleanup_old_backups(db: Session, job: BackupJob, log_buffer: list):
    """清理超出保留期的旧备份。

    严格遵循"先确认新备份成功，再清理旧备份"的顺序。
    """
    if not job.retention_days or job.retention_days <= 0:
        return

    cutoff = _utcnow() - timedelta(days=job.retention_days)

    # 查找过期的成功执行记录
    expired_records = db.query(ExecutionRecord).filter(
        ExecutionRecord.job_id == job.id,
        ExecutionRecord.status == RunStatus.SUCCESS,
        ExecutionRecord.finished_at < cutoff,
        ExecutionRecord.remote_path.isnot(None),
        ExecutionRecord.remote_path != "",
    ).all()

    if not expired_records:
        log_buffer.append("无需清理的过期备份。")
        return

    # 获取存储上传器
    storage_target = db.get(StorageTarget, job.storage_target_id)
    if not storage_target:
        return

    try:
        storage_config = json.loads(decrypt(storage_target.config))
        storage = get_storage(storage_target.storage_type.value)
    except Exception as e:
        log_buffer.append(f"清理失败：无法初始化存储上传器：{e}")
        return

    cleaned = 0
    for record in expired_records:
        try:
            if storage.delete(record.remote_path, storage_config):
                cleaned += 1
        except Exception as e:
            log_buffer.append(f"清理失败：{record.remote_path}，错误：{e}")

    log_buffer.append(f"已清理 {cleaned} 个过期备份（保留 {job.retention_days} 天）。")
