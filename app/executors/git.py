"""Git/GitLab 备份执行器。

支持单个 Git 仓库和 GitLab 全量项目两种来源，以及两种认证方式：
- token：GitLab API + HTTP token 认证克隆
- ssh：GitLab API + SSH key 认证克隆

仓库通过 mirror clone 或增量更新同步，最后打包为 tar.gz 文件。
"""

import base64
import hashlib
import os
import re
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
        repository_url = job_config.get("repository_url")
        if repository_url:
            return self._execute_single_repository(repository_url, job_config, work_dir)

        return self._execute_gitlab(job_config, work_dir)

    def _execute_single_repository(
        self,
        repository_url: str,
        job_config: dict[str, Any],
        work_dir: Path,
    ) -> Path:
        """镜像备份一个 GitHub 或其他 Git 仓库。"""
        auth_type = job_config.get("auth_type", "token")
        token = job_config.get("_github_token") or settings.GITHUB_TOKEN
        ssh_key = job_config.get("ssh_key", "")

        if auth_type == "ssh" and not ssh_key:
            raise ValueError("SSH 认证模式需要配置 SSH 私钥。")

        repo_name = self._repository_name(repository_url)
        repo_hash = hashlib.sha256(repository_url.encode("utf-8")).hexdigest()[:12]
        repos_dir = settings.REPOS_DIR / "single"
        repos_dir.mkdir(parents=True, exist_ok=True)
        repo_dir = repos_dir / f"{repo_name}-{repo_hash}.git"

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        if auth_type == "ssh":
            env = self._prepare_ssh_env(ssh_key, work_dir, env)
        elif token:
            env = self._prepare_http_token_env(repository_url, token, env)

        if repo_dir.exists():
            self.logger.info(f"增量更新单仓库：{repo_name}")
            self._run_git(["git", "remote", "update", "--prune"], cwd=repo_dir, env=env)
        else:
            self.logger.info(f"镜像克隆单仓库：{repo_name}")
            self._run_git(
                ["git", "clone", "--mirror", repository_url, str(repo_dir)],
                cwd=repos_dir,
                env=env,
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = work_dir / f"{repo_name}_{timestamp}.tar.gz"
        self.logger.info(f"正在打包压缩为 {archive_path.name}...")
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(repo_dir, arcname=f"{repo_name}.git")

        size_mb = archive_path.stat().st_size / (1024 * 1024)
        self.logger.info(f"打包完成，产物大小：{size_mb:.2f} MB")
        return archive_path

    def _execute_gitlab(self, job_config: dict[str, Any], work_dir: Path) -> Path:
        """通过 GitLab API 备份当前账号可访问的全部项目。"""
        gitlab_url = job_config.get("gitlab_url")
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
        env = None
        if auth_type == "ssh":
            env = self._prepare_ssh_env(ssh_key, work_dir, os.environ.copy())

        # 3. 镜像克隆或增量更新
        repos_dir = settings.REPOS_DIR
        repos_dir.mkdir(parents=True, exist_ok=True)

        for project in projects:
            self._mirror_repo(project, repos_dir, gitlab_token, gitlab_url, auth_type, env)

        # 4. 打包压缩
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"gitlab_backup_v{timestamp}.tar.gz"
        archive_path = work_dir / archive_name

        self.logger.info(f"正在打包压缩为 {archive_name}...")
        with tarfile.open(archive_path, "w:gz") as tar:
            for item in repos_dir.iterdir():
                if item.is_dir():
                    tar.add(item, arcname=item.name)

        size_mb = archive_path.stat().st_size / (1024 * 1024)
        self.logger.info(f"打包完成，产物大小：{size_mb:.2f} MB")
        return archive_path

    @staticmethod
    def _repository_name(repository_url: str) -> str:
        """从 HTTPS 或 SSH 仓库 URL 生成安全的文件名。"""
        parsed = urlparse(repository_url)
        path = parsed.path if parsed.scheme else repository_url.rsplit(":", 1)[-1]
        name = Path(path.rstrip("/")).name
        if name.endswith(".git"):
            name = name[:-4]
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
        if not safe_name:
            raise ValueError(f"无法从仓库 URL 识别仓库名称：{repository_url}")
        return safe_name

    @staticmethod
    def _prepare_http_token_env(
        repository_url: str,
        token: str,
        env: dict,
        username: str = "x-access-token",
    ) -> dict:
        """通过临时 Git 配置传递 HTTP Token，避免把 Token 写入 remote URL。"""
        parsed = urlparse(repository_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("HTTP Token 认证需要使用 http:// 或 https:// 仓库 URL。")

        index = int(env.get("GIT_CONFIG_COUNT", "0"))
        credentials = base64.b64encode(f"{username}:{token}".encode()).decode()
        env["GIT_CONFIG_COUNT"] = str(index + 1)
        env[f"GIT_CONFIG_KEY_{index}"] = (
            f"http.{parsed.scheme}://{parsed.hostname}/.extraheader"
        )
        env[f"GIT_CONFIG_VALUE_{index}"] = f"AUTHORIZATION: basic {credentials}"
        return env

    @classmethod
    def test_repository_access(cls, repository_url: str, token: str) -> int:
        """验证仓库读取权限并返回远端引用数量。"""
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        if token:
            env = cls._prepare_http_token_env(repository_url, token, env)
        result = cls._run_git(
            ["git", "ls-remote", repository_url],
            timeout=60,
            env=env,
        )
        return len([line for line in result.stdout.splitlines() if line.strip()])

    def _prepare_ssh_env(
        self,
        ssh_key: str,
        work_dir: Path,
        env: dict,
    ) -> dict:
        ssh_key_file = work_dir / "id_rsa"
        ssh_key_file.write_text(ssh_key, encoding="utf-8")
        ssh_key_file.chmod(0o600)
        env["GIT_SSH_COMMAND"] = (
            f'ssh -i "{ssh_key_file}" -o StrictHostKeyChecking=no '
            "-o UserKnownHostsFile=/dev/null"
        )
        self.logger.info("已配置 SSH key 认证。")
        return env

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

        repo_env = env
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
            repo_env = os.environ.copy()
            repo_env["GIT_TERMINAL_PROMPT"] = "0"
            repo_env = self._prepare_http_token_env(
                clone_url,
                token,
                repo_env,
                username="oauth2",
            )

        repo_dir = repos_dir / f"{project_id}.git"

        if repo_dir.exists():
            # 增量更新
            self.logger.info(f"增量更新：{project_name}")
            try:
                self._run_git(
                    ["git", "remote", "update", "--prune"],
                    cwd=repo_dir,
                    env=repo_env,
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
                    env=repo_env,
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
