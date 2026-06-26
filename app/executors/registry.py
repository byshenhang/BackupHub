"""执行器注册表。

通过字典映射任务类型到对应的执行器类，新增执行器只需在此注册。
"""

from app.executors.base import BaseExecutor
from app.executors.git import GitExecutor

# 执行器注册表：type_string -> executor_class
_EXECUTOR_REGISTRY: dict[str, type[BaseExecutor]] = {
    "git": GitExecutor,
}


def get_executor(job_type: str) -> BaseExecutor:
    """根据任务类型获取对应的执行器实例。

    Args:
        job_type: 任务类型字符串（如 "git"、"file"、"database"）

    Returns:
        对应的执行器实例

    Raises:
        ValueError: 不支持的任务类型
    """
    executor_class = _EXECUTOR_REGISTRY.get(job_type)
    if executor_class is None:
        raise ValueError(f"不支持的任务类型：{job_type}，可用类型：{list(_EXECUTOR_REGISTRY.keys())}")
    return executor_class()


def register_executor(type_name: str, executor_class: type[BaseExecutor]):
    """注册新的执行器类型。

    Args:
        type_name: 类型标识字符串
        executor_class: 执行器类
    """
    _EXECUTOR_REGISTRY[type_name] = executor_class
