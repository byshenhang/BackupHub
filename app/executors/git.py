"""Git/GitLab 备份执行器。

支持两种认证方式：
- token：GitLab API + HTTP token 认证克隆
- ssh：GitLab API + SSH key 认证克隆

通过 GitLab API 拉取项目列表，对每个仓库执行镜像克隆或增量更新，
最后打包压缩为 tar.gz 文件。
"""

import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.executors.base import BaseExecutor


class GitExecutor(BaseExecutor):
    """Git 备份执行器。

    认证方式由 job_config["auth_type"] 决定：
    - "token"（默认）：使用 GitLab Token，HTTP 克隆
    - "ssh"：使用 SSH 私钥，SSH 克隆
    """

    @property
    def executor_type(self) -> str:
        return "git"

    def execute(self, job_config: dict[str, Any], work_dir: Path) -> Path:
        gitlab_url = job_config.get("gitlab_url") or settings.GITLAB_URL
        gitlab_token = job_config.get("gitlab_token") or settings.GITLAB_TOKEN
        auth_type = job_config.get("auth_type", "token")

        if not gitlab_url:
            raise ValueError("GitLab URL 未配置。")

        # Token 用于 API 调用（两种模式都需要）
        if not gitlab_token:
            raise ValueError("GitLab Token 未配置（API 调用需要）。")

        # SSH 模式需要密钥
        ssh_key = job_config.get("ssh_key", "")
        if auth_type == "ssh" and not ssh_key:
            raise ValueError("SSH 认证模式需要配置 SSH 私钥。")

        # 1. 拉取项目列表（始终通过 API + Token）
        self.logger.info("正在从 GitLab 拉取项目列表...")
        projects = self._list_projects(gitlab_url, gitlab_token)
        self.logger.info(f"共发现 {len(projects)} 个项目。")

        # 2. 准备 SSH 环境（如果需要）
        ssh_key_file = None
        env = None
        if auth_type == "ssh":
            ssh_key_file = work_dir / "id_rsa"
            ssh_key_file.write_text(ssh_key, encoding="utf-8")
            ssh_key_file.chmod(0o600)
            env = os.environ.copy()
            env["GIT_SSH_COMMAND"] = f'ssh -i "{ssh_key_file}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
            self.logger.info("已配置 SSH key 认证。")

        # 3. 镜像克隆或增量更新
        repos_dir = settings.REPOS_DIR
        repos_dir.mkdir(parents=True, exist_ok=True)

        for project in projects:
            self._mirror_repo(project, repos_dir, gitlab_token, gitlab_url, auth_type, env)

        # 4. 打包压缩
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"gitlab_backup_{timestamp}.tar.gz"
        archive_path = work_dir / archive_name

        self.logger.info(f"正在打包压缩为 {archive_name}...")
        with tarfile.open(archive_path, "w:gz") as tar:
            for item in repos_dir.iterdir():
                if item.is_dir():
                    tar.add(item, arcname=item.name)

        size_mb = archive_path.stat().st_size / (1024 * 1024)
        self.logger.info(f"打包完成，产物大小：{size_mb:.2f} MB")
        return archive_path

    def _list_projects(self, gitlab_url: str, token: str) -> list[dict]:
        """通过 GitLab API 分页拉取所有项目。"""
        projects = []
        page = 1
        per_page = 100

        with httpx.Client(timeout=30.0) as client:
            while True:
                resp = client.get(
                    f"{gitlab_url}/api/v4/projects",
                    headers={"PRIVATE-TOKEN": token},
                    params={"per_page": per_page, "page": page, "simple": "true"},
                )
                resp.raise_for_status()
                batch = resp.json()
                if not batch:
                    break
                projects.extend(batch)
                page += 1
                self.logger.debug(f"已拉取 {len(projects)} 个项目...")

        return projects

    def _mirror_repo(self, project: dict, repos_dir: Path, token: str, gitlab_url: str, auth_type: str, env: dict | None):
        """镜像克隆或增量更新单个仓库。"""
        project_id = project["id"]
        project_name = project.get("path_with_namespace", str(project_id))

        if auth_type == "ssh":
            # SSH 模式：使用 git@host:group/repo.git 格式
            clone_url = project.get("ssh_url_to_repo", "")
            if not clone_url:
                self.logger.warning(f"项目 {project_name} 无 SSH 克隆地址，跳过。")
                return
        else:
            # Token 模式：使用 HTTP URL + token 注入
            clone_url = project.get("http_url_to_repo", "")
            if not clone_url:
                self.logger.warning(f"项目 {project_name} 无 HTTP 克隆地址，跳过。")
                return
            # 注入 token
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(clone_url)
            clone_url = urlunparse(parsed._replace(
                netloc=f"oauth2:{token}@{parsed.hostname}" +
                       (f":{parsed.port}" if parsed.port else "")
            ))

        repo_dir = repos_dir / f"{project_id}.git"

        if repo_dir.exists():
            # 增量更新
            self.logger.info(f"增量更新：{project_name}")
            try:
                self._run_git(
                    ["git", "remote", "update", "--prune"],
                    cwd=repo_dir,
                    env=env,
                )
            except subprocess.CalledProcessError as e:
                self.logger.error(f"增量更新失败：{project_name}，错误：{e.stderr}")
        else:
            # 首次镜像克隆
            self.logger.info(f"镜像克隆：{project_name}（{auth_type}）")
            try:
                self._run_git(
                    ["git", "clone", "--mirror", clone_url, str(repo_dir)],
                    cwd=repos_dir,
                    env=env,
                )
            except subprocess.CalledProcessError as e:
                self.logger.error(f"镜像克隆失败：{project_name}，错误：{e.stderr}")

    @staticmethod
    def _run_git(args: list[str], cwd: Path | None = None, timeout: int = 600, env: dict | None = None):
        """执行 git 命令。"""
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, args, result.stdout, result.stderr
            )
        return result
