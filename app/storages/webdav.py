"""WebDAV 存储上传器 - 123网盘专用优化版

抛弃webdavclient3库，直接用requests手动实现，完全适配123云盘的WebDAV特性。
"""

import requests
from pathlib import Path
from urllib.parse import urljoin

from app.storages.base import BaseStorage


class WebDAVStorage(BaseStorage):
    """WebDAV 存储上传器 - 123网盘专用优化版"""

    @property
    def storage_type(self) -> str:
        return "webdav"

    def _make_request(self, method: str, url: str, config: dict, **kwargs):
        """发起WebDAV请求，自动添加认证和超时。"""
        auth = (config.get("username", ""), config.get("password", ""))
        kwargs.setdefault("auth", auth)
        kwargs.setdefault("timeout", 300)  # 5分钟超时
        kwargs.setdefault("verify", config.get("verify_ssl", True))

        self.logger.debug(f"HTTP {method} {url}")
        response = requests.request(method, url, **kwargs)
        self.logger.debug(f"响应状态码: {response.status_code}")

        return response

    def _mkdir(self, base_url: str, path: str, config: dict):
        """创建目录，MKCOL方法。"""
        if not path or path == "/":
            return

        # 确保路径格式正确
        if not path.startswith("/"):
            path = "/" + path
        path = path.rstrip("/")

        full_url = urljoin(base_url, path.lstrip("/"))
        self.logger.debug(f"创建目录: {full_url} (path={path})")

        try:
            response = self._make_request("MKCOL", full_url, config)
            if 200 <= response.status_code < 300:
                self.logger.debug(f"目录创建成功: {path}")
            elif response.status_code == 405:  # Method Not Allowed - 目录已存在
                self.logger.debug(f"目录已存在: {path}")
            elif response.status_code == 409:  # Conflict - 父目录不存在
                # 递归创建父目录
                parent_path = str(Path(path).parent).replace("\\", "/")
                if parent_path != "/":
                    self._mkdir(base_url, parent_path, config)
                    # 重试创建当前目录
                    response = self._make_request("MKCOL", full_url, config)
                    if 200 <= response.status_code < 300 or response.status_code == 405:
                        self.logger.debug(f"目录创建成功（递归后）: {path}")
            else:
                self.logger.debug(f"目录创建响应: {response.status_code} {response.text}")
        except Exception as e:
            self.logger.debug(f"创建目录忽略错误: {e}")

    def upload(self, local_path: Path, remote_key: str, config: dict) -> str:
        """上传文件到 WebDAV - 123网盘专用优化。"""
        base_url = config.get("url", "").rstrip("/") + "/"
        remote_dir = config.get("remote_path", "/backup-hub/")

        self.logger.info(f"=== WebDAV 上传开始 ===")
        self.logger.info(f"WebDAV 基础 URL: {base_url}")
        self.logger.info(f"配置的远程目录: {remote_dir}")
        self.logger.info(f"本地文件: {local_path}")
        self.logger.info(f"文件大小: {local_path.stat().st_size} 字节")

        # 第一步：测试连接，列出根目录
        self.logger.info("\n1️⃣ 测试连接 - 列出根目录")
        try:
            root_url = base_url
            response = self._make_request("PROPFIND", root_url, config, headers={
                "Depth": "1"
            })
            self.logger.info(f"根目录请求状态码: {response.status_code}")
            if 200 <= response.status_code < 300:
                self.logger.info("✅ 连接成功")
            else:
                self.logger.warning(f"⚠️  连接可能有问题，状态码: {response.status_code}")
        except Exception as e:
            self.logger.error(f"❌ 连接失败: {e}")
            raise

        # 第二步：确保远程目录存在
        self.logger.info(f"\n2️⃣ 确保目录存在: {remote_dir}")
        self._mkdir(base_url, remote_dir, config)

        # 第三步：处理文件名（只取文件名，不要目录）
        filename = Path(remote_key).name
        self.logger.info(f"上传文件名: {filename}")

        # 第四步：构建完整远程路径
        # 注意：123网盘的路径处理非常特殊，要特别小心
        # 我们直接把文件上传到 remote_dir 目录下，不要任何子目录
        remote_path = f"{remote_dir.rstrip('/')}/{filename}"
        # 清理路径，确保没有双斜杠
        while "//" in remote_path:
            remote_path = remote_path.replace("//", "/")

        full_upload_url = urljoin(base_url, remote_path.lstrip("/"))
        self.logger.info(f"完整上传URL: {full_upload_url}")
        self.logger.info(f"远程文件路径: {remote_path}")

        # 第五步：上传文件
        self.logger.info("\n3️⃣ 开始上传文件")
        try:
            file_size = local_path.stat().st_size
            self.logger.info(f"准备流式上传，大小: {file_size} 字节")

            # 123网盘专用：添加必要的请求头
            headers = {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(file_size),
            }

            with open(local_path, "rb") as file_content:
                response = self._make_request(
                    "PUT",
                    full_upload_url,
                    config,
                    data=file_content,
                    headers=headers
                )

            if 200 <= response.status_code < 300:
                self.logger.info("✅ 文件上传请求成功")
            else:
                self.logger.error(f"❌ 上传失败，状态码: {response.status_code}")
                self.logger.error(f"响应内容: {response.text[:500]}")
                raise Exception(f"上传失败: {response.status_code}")

        except Exception as e:
            self.logger.error(f"❌ 上传过程出错: {e}", exc_info=True)
            raise

        # 第六步：验证文件是否真的上传成功
        self.logger.info("\n4️⃣ 验证上传结果")
        upload_success = False

        # 验证方法1：列出目录看文件是否存在
        try:
            self.logger.info(f"列出目录: {remote_dir}")
            list_url = urljoin(base_url, remote_dir.lstrip("/"))
            response = self._make_request("PROPFIND", list_url, config, headers={
                "Depth": "1"
            })

            if 200 <= response.status_code < 300:
                # 简单检查文件名是否在响应内容中
                if filename in response.text:
                    upload_success = True
                    self.logger.info(f"✅ 验证成功！在目录中找到文件: {filename}")
                else:
                    self.logger.warning(f"⚠️  目录中没找到文件，响应内容: {response.text[:1000]}")
        except Exception as e:
            self.logger.warning(f"⚠️  列出目录验证失败: {e}")

        # 验证方法2：尝试GET文件
        if not upload_success:
            try:
                self.logger.info(f"尝试访问文件: {remote_path}")
                get_url = urljoin(base_url, remote_path.lstrip("/"))
                response = self._make_request("GET", get_url, config, stream=True)
                try:
                    if response.status_code == 200:
                        upload_success = True
                        self.logger.info("✅ 验证成功！可以访问文件")
                finally:
                    response.close()
            except Exception as e:
                self.logger.warning(f"⚠️  GET验证失败: {e}")

        if upload_success:
            self.logger.info(f"\n🎉 恭喜！文件上传到123网盘成功！")
            self.logger.info(f"📁 远程路径: {remote_path}")
        else:
            self.logger.warning(f"\n⚠️  上传请求成功，但验证失败。可能是123网盘延迟，稍等几分钟再看。")

        self.logger.info(f"\n=== WebDAV 上传结束 ===")
        return remote_path

    def delete(self, remote_key: str, config: dict) -> bool:
        """删除 WebDAV 文件。"""
        base_url = config.get("url", "").rstrip("/") + "/"
        remote_path = remote_key

        self.logger.info(f"尝试删除文件: {remote_path}")

        try:
            full_url = urljoin(base_url, remote_path.lstrip("/"))
            response = self._make_request("DELETE", full_url, config)

            if 200 <= response.status_code < 300:
                self.logger.info(f"✅ 删除成功: {remote_path}")
                return True
            elif response.status_code == 404:
                self.logger.info(f"文件已不存在: {remote_path}")
                return True
            else:
                self.logger.warning(f"⚠️  删除响应码: {response.status_code}")
                return False
        except Exception as e:
            self.logger.error(f"❌ 删除失败: {e}")
            return False

    def list_files(self, prefix: str, config: dict) -> list[str]:
        """列出 WebDAV 中指定路径下的文件。"""
        base_url = config.get("url", "").rstrip("/") + "/"
        remote_dir = config.get("remote_path", "/backup-hub/")

        try:
            list_url = urljoin(base_url, remote_dir.lstrip("/"))
            response = self._make_request("PROPFIND", list_url, config, headers={
                "Depth": "1"
            })

            files = []
            if 200 <= response.status_code < 300:
                # 简单解析XML，找到文件名
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                ns = {"d": "DAV:"}

                for response_elem in root.findall(".//d:response", ns):
                    href = response_elem.find(".//d:href", ns)
                    if href is not None:
                        name = Path(href.text).name
                        if name.startswith(prefix):
                            files.append(name)

            self.logger.info(f"找到 {len(files)} 个文件: {files}")
            return files
        except Exception as e:
            self.logger.error(f"列出文件失败: {e}")
            return []

    def test_connection(self, config: dict) -> None:
        base_url = str(config.get("url", "")).strip().rstrip("/") + "/"
        if base_url == "/":
            raise ValueError("WebDAV URL 未配置。")
        response = self._make_request(
            "PROPFIND",
            base_url,
            config,
            headers={"Depth": "0"},
            timeout=30,
        )
        try:
            if not 200 <= response.status_code < 300:
                raise RuntimeError(f"WebDAV 返回状态码 {response.status_code}。")
        finally:
            response.close()
