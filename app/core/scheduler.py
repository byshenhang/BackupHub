"""APScheduler 调度器集成模块。

管理备份任务的定时调度，支持动态添加、移除、更新任务。
调度信息持久化到数据库，服务重启后自动恢复。
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from app.core.runner import run_backup_job

logger = logging.getLogger("backup-hub.scheduler")

# 调度器实例（全局单例）
_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    """获取调度器实例（懒初始化）。"""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={
                "coalesce": True,  # 合并错过的执行
                "max_instances": 1,  # 同一任务最多一个实例
            },
        )
    return _scheduler


def start_scheduler():
    """启动调度器。"""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("调度器已启动。")


def shutdown_scheduler():
    """关闭调度器。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("调度器已关闭。")
        _scheduler = None


def load_jobs_from_db():
    """从数据库加载所有启用的任务到调度器。

    服务启动时调用，恢复所有任务的调度状态。
    """
    from app.db.session import SessionLocal
    from app.db.models import BackupJob

    db = SessionLocal()
    try:
        jobs = db.query(BackupJob).filter(BackupJob.enabled == True).all()
        for job in jobs:
            add_job_to_scheduler(job.id, job.cron_expression, job.name)
        logger.info(f"已从数据库加载 {len(jobs)} 个任务到调度器。")
    finally:
        db.close()


def add_job_to_scheduler(job_id: int, cron_expression: str, job_name: str):
    """添加任务到调度器。

    Args:
        job_id: 任务 ID
        cron_expression: cron 表达式
        job_name: 任务名称（用于日志）
    """
    scheduler = get_scheduler()
    job_id_str = f"backup_job_{job_id}"

    # 先移除已有的同名任务（避免重复）
    try:
        scheduler.remove_job(job_id_str)
    except Exception:
        pass

    try:
        trigger = CronTrigger.from_crontab(cron_expression)
        scheduler.add_job(
            run_backup_job,
            trigger=trigger,
            id=job_id_str,
            name=job_name,
            kwargs={"job_id": job_id, "trigger_source": "scheduled"},
            replace_existing=True,
        )
        logger.info(f"任务已添加到调度器：{job_name}（{cron_expression}）")
    except Exception as e:
        logger.error(f"添加任务到调度器失败：{job_name}，错误：{e}")


def remove_job_from_scheduler(job_id: int):
    """从调度器移除任务。"""
    scheduler = get_scheduler()
    job_id_str = f"backup_job_{job_id}"
    try:
        scheduler.remove_job(job_id_str)
        logger.info(f"任务已从调度器移除：ID={job_id}")
    except Exception:
        pass


def update_job_in_scheduler(job_id: int, cron_expression: str, job_name: str, enabled: bool):
    """更新调度器中的任务。

    如果任务已禁用则移除，否则更新调度配置。
    """
    if enabled:
        add_job_to_scheduler(job_id, cron_expression, job_name)
    else:
        remove_job_from_scheduler(job_id)


def get_next_run_time(job_id: int) -> datetime | None:
    """获取任务的下一次执行时间。"""
    scheduler = get_scheduler()
    job_id_str = f"backup_job_{job_id}"
    job = scheduler.get_job(job_id_str)
    if job and job.next_run_time:
        return job.next_run_time
    return None


def trigger_job_now(job_id: int):
    """手动立即触发任务执行。"""
    logger.info(f"手动触发任务：ID={job_id}")
    run_backup_job(job_id=job_id, trigger_source="manual")
