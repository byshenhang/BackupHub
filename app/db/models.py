"""SQLAlchemy 数据模型定义。

四张核心表：BackupJob、StorageTarget、ExecutionRecord、AlertChannel
"""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, func
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class JobType(str, enum.Enum):
    """备份任务类型。"""
    GIT = "git"
    FILE = "file"
    DATABASE = "database"


class StorageType(str, enum.Enum):
    """存储目标类型。"""
    LOCAL = "local"
    OSS = "oss"
    COS = "cos"
    WEBDAV = "webdav"


class RunStatus(str, enum.Enum):
    """执行记录状态。"""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TriggerSource(str, enum.Enum):
    """触发来源。"""
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class BackupJob(Base):
    """备份任务表。"""
    __tablename__ = "backup_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="任务名称")
    job_type = Column(Enum(JobType), nullable=False, comment="任务类型")
    cron_expression = Column(String(100), nullable=False, comment="cron 调度表达式")
    enabled = Column(Boolean, default=True, comment="是否启用")
    config = Column(Text, default="{}", comment="类型专属配置（JSON）")
    storage_target_id = Column(Integer, ForeignKey("storage_targets.id"), nullable=True, comment="关联的存储目标")
    retention_days = Column(Integer, default=30, comment="保留天数")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系
    storage_target = relationship("StorageTarget", back_populates="jobs")
    runs = relationship("ExecutionRecord", back_populates="job", order_by="desc(ExecutionRecord.created_at)")


class StorageTarget(Base):
    """存储目标表。"""
    __tablename__ = "storage_targets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="存储目标名称")
    storage_type = Column(Enum(StorageType), nullable=False, comment="存储类型")
    config = Column(Text, default="{}", comment="加密的连接配置（JSON）")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系
    jobs = relationship("BackupJob", back_populates="storage_target")


class ExecutionRecord(Base):
    """执行记录表。"""
    __tablename__ = "execution_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("backup_jobs.id"), nullable=False, comment="关联任务")
    status = Column(Enum(RunStatus), default=RunStatus.RUNNING, comment="执行状态")
    started_at = Column(DateTime, default=func.now(), comment="开始时间")
    finished_at = Column(DateTime, nullable=True, comment="结束时间")
    duration_seconds = Column(Integer, nullable=True, comment="耗时（秒）")
    artifact_size = Column(BigInteger, nullable=True, comment="产物大小（字节）")
    remote_path = Column(String(500), nullable=True, comment="远端产物路径")
    log = Column(Text, default="", comment="执行日志")
    trigger_source = Column(Enum(TriggerSource), default=TriggerSource.SCHEDULED, comment="触发来源")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime, default=func.now(), comment="记录创建时间")

    # 关系
    job = relationship("BackupJob", back_populates="runs")


class AlertChannel(Base):
    """告警渠道表（后续版本使用）。"""
    __tablename__ = "alert_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="渠道名称")
    channel_type = Column(String(50), nullable=False, comment="渠道类型（wecom/dingtalk/email）")
    config = Column(Text, default="{}", comment="渠道配置（JSON，含 webhook 等）")
    enabled = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
