"""存储上传器抽象基类。

所有上传器必须实现 BaseStorage 接口，负责将本地文件送达存储目标。
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path


class BaseStorage(ABC):
    """存储上传器抽象基类。

    每种存储类型实现一个上传器，负责把本地文件送到对应的存储目标。
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def upload(self, local_path: Path, remote_key: str, config: dict) -> str:
        """上传本地文件到存储目标。

        Args:
            local_path: 本地文件路径
            remote_key: 远端存储的文件名/key
            config: 存储目标的连接配置（已解密）

        Returns:
            远端文件的完整路径或标识

        Raises:
            Exception: 上传失败时抛出异常
        """
        ...

    @abstractmethod
    def delete(self, remote_key: str, config: dict) -> bool:
        """删除远端文件。

        Args:
            remote_key: 远端文件的 key/path
            config: 存储目标的连接配置（已解密）

        Returns:
            是否删除成功
        """
        ...

    @abstractmethod
    def list_files(self, prefix: str, config: dict) -> list[str]:
        """列出指定前缀下的文件。

        Args:
            prefix: 文件前缀/路径
            config: 存储目标的连接配置（已解密）

        Returns:
            文件 key 列表
        """
        ...

    @property
    @abstractmethod
    def storage_type(self) -> str:
        """返回存储类型标识，与 StorageType 枚举值对应。"""
        ...
