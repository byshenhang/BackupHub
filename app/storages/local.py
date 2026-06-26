"""本地目录上传器。

将备份产物复制到指定的本地目录。
"""

import shutil
from pathlib import Path

from app.storages.base import BaseStorage


class LocalStorage(BaseStorage):
    """本地目录存储上传器。

    将文件复制到配置的本地目录中。
    """

    @property
    def storage_type(self) -> str:
        return "local"

    def upload(self, local_path: Path, remote_key: str, config: dict) -> str:
        target_dir = Path(config.get("path", ""))
        if not target_dir:
            raise ValueError("本地存储路径未配置。")

        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / remote_key

        self.logger.info(f"上传到本地目录：{target_path}")
        shutil.copy2(local_path, target_path)

        self.logger.info(f"上传完成：{target_path}（{target_path.stat().st_size} 字节）")
        return str(target_path)

    def delete(self, remote_key: str, config: dict) -> bool:
        target_path = Path(remote_key)
        if target_path.exists():
            target_path.unlink()
            self.logger.info(f"已删除：{target_path}")
            return True
        return False

    def list_files(self, prefix: str, config: dict) -> list[str]:
        target_dir = Path(config.get("path", ""))
        if not target_dir.exists():
            return []
        return [
            str(f) for f in target_dir.iterdir()
            if f.is_file() and f.name.startswith(prefix)
        ]
