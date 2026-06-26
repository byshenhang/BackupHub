"""WebDAV 存储上传器。

支持坚果云、Nextcloud 等提供 WebDAV 协议的存储服务。
依赖 webdavclient3 库。
"""

from pathlib import Path

from app.storages.base import BaseStorage


class WebDAVStorage(BaseStorage):
    """WebDAV 存储上传器。"""

    @property
    def storage_type(self) -> str:
        return "webdav"

    def _get_client(self, config: dict):
        """创建 WebDAV 客户端。"""
        try:
            from webdav3.client import Client
        except ImportError:
            raise RuntimeError("webdavclient3 未安装。请执行 pip install webdavclient3。")

        options = {
            "webdav_hostname": config.get("url", ""),
            "webdav_login": config.get("username", ""),
            "webdav_password": config.get("password", ""),
        }
        if not options["webdav_hostname"]:
            raise ValueError("WebDAV URL 未配置。")

        return Client(options)

    def upload(self, local_path: Path, remote_key: str, config: dict) -> str:
        """上传文件到 WebDAV。"""
        client = self._get_client(config)
        remote_dir = config.get("remote_path", "/backup-hub/")

        # 确保远端目录存在
        if not client.check(remote_dir):
            client.mkdir(remote_dir)

        remote_path = f"{remote_dir.rstrip('/')}/{remote_key}"

        # 确保子目录存在（remote_key 可能包含 /）
        parent_dir = str(Path(remote_path).parent).replace("\\", "/")
        if parent_dir and parent_dir != remote_dir.rstrip("/") and not client.check(parent_dir):
            try:
                client.mkdir(parent_dir)
            except Exception:
                pass

        self.logger.info(f"上传到 WebDAV：{remote_path}")
        client.upload_sync(remote_path=remote_path, local_path=str(local_path))

        self.logger.info(f"WebDAV 上传完成：{remote_path}")
        return remote_path

    def delete(self, remote_key: str, config: dict) -> bool:
        """删除 WebDAV 文件。"""
        client = self._get_client(config)
        try:
            if client.check(remote_key):
                client.clean(remote_key)
                self.logger.info(f"已从 WebDAV 删除：{remote_key}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"WebDAV 删除失败：{remote_key}，错误：{e}")
            return False

    def list_files(self, prefix: str, config: dict) -> list[str]:
        """列出 WebDAV 中指定路径下的文件。"""
        client = self._get_client(config)
        remote_dir = config.get("remote_path", "/backup-hub/")
        try:
            items = client.list(remote_dir, get_info=True)
            return [
                item["name"] for item in items
                if item.get("name", "").startswith(prefix)
            ]
        except Exception:
            return []
