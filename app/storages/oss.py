"""阿里云 OSS 上传器。

使用 oss2 SDK 将备份产物上传到阿里云对象存储。
"""

from pathlib import Path

from app.storages.base import BaseStorage


class OSSStorage(BaseStorage):
    """阿里云 OSS 存储上传器。"""

    @property
    def storage_type(self) -> str:
        return "oss"

    def upload(self, local_path: Path, remote_key: str, config: dict) -> str:
        """上传文件到 OSS。"""
        try:
            import oss2
        except ImportError:
            raise RuntimeError("oss2 未安装。请执行 pip install oss2。")

        access_key_id = config.get("access_key_id", "")
        access_key_secret = config.get("access_key_secret", "")
        endpoint = config.get("endpoint", "")
        bucket_name = config.get("bucket", "")
        prefix = config.get("prefix", "backup-hub/")

        if not all([access_key_id, access_key_secret, endpoint, bucket_name]):
            raise ValueError("OSS 配置不完整，需要 access_key_id、access_key_secret、endpoint、bucket。")

        auth = oss2.Auth(access_key_id, access_key_secret)
        bucket = oss2.Bucket(auth, endpoint, bucket_name)

        full_key = f"{prefix}{remote_key}"
        self.logger.info(f"上传到 OSS：{full_key}")

        with open(local_path, "rb") as f:
            bucket.put_object(full_key, f)

        self.logger.info(f"OSS 上传完成：{full_key}")
        return full_key

    def delete(self, remote_key: str, config: dict) -> bool:
        """删除 OSS 文件。"""
        try:
            import oss2
        except ImportError:
            raise RuntimeError("oss2 未安装。")

        auth = oss2.Auth(config.get("access_key_id", ""), config.get("access_key_secret", ""))
        bucket = oss2.Bucket(auth, config.get("endpoint", ""), config.get("bucket", ""))

        try:
            bucket.delete_object(remote_key)
            self.logger.info(f"已从 OSS 删除：{remote_key}")
            return True
        except Exception as e:
            self.logger.error(f"OSS 删除失败：{remote_key}，错误：{e}")
            return False

    def list_files(self, prefix: str, config: dict) -> list[str]:
        """列出 OSS 中指定前缀的文件。"""
        try:
            import oss2
        except ImportError:
            raise RuntimeError("oss2 未安装。")

        auth = oss2.Auth(config.get("access_key_id", ""), config.get("access_key_secret", ""))
        bucket = oss2.Bucket(auth, config.get("endpoint", ""), config.get("bucket", ""))

        full_prefix = f"{config.get('prefix', 'backup-hub/')}{prefix}"
        return [obj.key for obj in oss2.ObjectIterator(bucket, prefix=full_prefix)]

    def test_connection(self, config: dict) -> None:
        try:
            import oss2
        except ImportError:
            raise RuntimeError("oss2 未安装。")

        auth = oss2.Auth(
            config.get("access_key_id", ""),
            config.get("access_key_secret", ""),
        )
        bucket = oss2.Bucket(
            auth,
            config.get("endpoint", ""),
            config.get("bucket", ""),
        )
        bucket.get_bucket_info()
