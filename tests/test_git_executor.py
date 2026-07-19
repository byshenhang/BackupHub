"""Git 执行器的单仓库备份测试。"""

import base64
import subprocess
import tarfile
from pathlib import Path

from app.config import settings
from app.executors.git import GitExecutor


def test_repository_name_supports_https_and_ssh():
    executor = GitExecutor()

    assert executor._repository_name(
        "https://github.com/byshenhang/super-agent-kernel.git"
    ) == "super-agent-kernel"
    assert executor._repository_name(
        "git@github.com:byshenhang/super-agent-kernel.git"
    ) == "super-agent-kernel"


def test_http_token_is_passed_without_modifying_remote_url():
    env = GitExecutor._prepare_http_token_env(
        "https://github.com/byshenhang/super-agent-kernel.git",
        "test-token",
        {},
    )

    encoded = env["GIT_CONFIG_VALUE_0"].split("basic ", 1)[1]
    assert base64.b64decode(encoded).decode() == "x-access-token:test-token"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"


def test_gitlab_token_is_not_embedded_in_clone_url(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, cwd=None, timeout=600, env=None):
        calls.append((args, env))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(GitExecutor, "_run_git", staticmethod(fake_run))

    GitExecutor()._mirror_repo(
        {
            "id": 7,
            "path_with_namespace": "group/project",
            "http_url_to_repo": "https://gitlab.example.com/group/project.git",
        },
        tmp_path,
        "glpat-secret-token",
        "https://gitlab.example.com",
        "token",
        None,
    )

    args, env = calls[0]
    assert "glpat-secret-token" not in " ".join(args)
    encoded = env["GIT_CONFIG_VALUE_0"].split("basic ", 1)[1]
    assert base64.b64decode(encoded).decode() == "oauth2:glpat-secret-token"


def test_single_repository_creates_mirror_archive(tmp_path, monkeypatch):
    repos_dir = tmp_path / "repos"
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.setattr(settings, "REPOS_DIR", repos_dir)
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")

    calls = []

    def fake_run(args, cwd=None, timeout=600, env=None):
        calls.append(args)
        if args[1:3] == ["clone", "--mirror"]:
            target = Path(args[-1])
            target.mkdir(parents=True)
            (target / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            (target / "objects").mkdir()
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(GitExecutor, "_run_git", staticmethod(fake_run))

    artifact = GitExecutor().execute(
        {
            "repository_url": "https://github.com/byshenhang/super-agent-kernel.git",
            "auth_type": "token",
        },
        work_dir,
    )

    assert artifact.name.startswith("super-agent-kernel_")
    assert artifact.name.endswith(".tar.gz")
    assert calls[0][1:3] == ["clone", "--mirror"]
    with tarfile.open(artifact, "r:gz") as archive:
        names = archive.getnames()
    assert "super-agent-kernel.git/HEAD" in names
    assert "super-agent-kernel.git/objects" in names
