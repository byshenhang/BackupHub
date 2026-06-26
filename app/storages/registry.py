"""存储上传器注册表。

通过字典映射存储类型到对应的上传器类，新增上传器只需在此注册。
"""

from app.storages.base import BaseStorage
from app.storages.local import LocalStorage
from app.storages.oss import OSSStorage
from app.storages.webdav import WebDAVStorage

# 上传器注册表：type_string -> storage_class
_STORAGE_REGISTRY: dict[str, type[BaseStorage]] = {
    "local": LocalStorage,
    "oss": OSSStorage,
    "webdav": WebDAVStorage,
}


def get_storage(storage_type: str) -> BaseStorage:
    """根据存储类型获取对应的上传器实例。

    Args:
        storage_type: 存储类型字符串（如 "local"、"oss"、"webdav"）

    Returns:
        对应的上传器实例

    Raises:
        ValueError: 不支持的存储类型
    """
    storage_class = _STORAGE_REGISTRY.get(storage_type)
    if storage_class is None:
        raise ValueError(f"不支持的存储类型：{storage_type}，可用类型：{list(_STORAGE_REGISTRY.keys())}")
    return storage_class()


def register_storage(type_name: str, storage_class: type[BaseStorage]):
    """注册新的存储类型。

    Args:
        type_name: 类型标识字符串
        storage_class: 上传器类
    """
    _STORAGE_REGISTRY[type_name] = storage_class
