"""备份执行器抽象基类。

所有执行器必须实现 BaseExecutor 接口，产出一个待上传的本地文件路径。
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseExecutor(ABC):
    """备份执行器抽象基类。

    每种备份类型实现一个执行器，负责具体的备份动作。
    执行器产出一个本地文件路径，由上传器负责送达存储目标。
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def execute(self, job_config: dict[str, Any], work_dir: Path) -> Path:
        """执行备份，返回产物文件路径。

        Args:
            job_config: 任务的类型专属配置（从 JSON 解析）
            work_dir: 工作目录，执行器应在此目录下生成产物

        Returns:
            备份产物的本地文件路径

        Raises:
            Exception: 备份执行失败时抛出异常
        """
        ...

    @property
    @abstractmethod
    def executor_type(self) -> str:
        """返回执行器类型标识，与 JobType 枚举值对应。"""
        ...
