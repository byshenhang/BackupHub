"""应用设置 API。"""

import subprocess
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import require_auth
from app.core.app_settings import (
    GITHUB_TOKEN_KEY,
    delete_secret,
    get_github_token,
    get_github_token_status,
    set_secret,
)
from app.db.session import get_db
from app.executors.git import GitExecutor


router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(require_auth)],
)


class GitHubTokenUpdate(BaseModel):
    token: str = Field(min_length=20, max_length=500)


class GitHubRepositoryTest(BaseModel):
    repository_url: str = Field(min_length=10, max_length=500)


@router.get("/github-token")
def github_token_status(db: Session = Depends(get_db)):
    return get_github_token_status(db)


@router.put("/github-token")
def update_github_token(
    data: GitHubTokenUpdate,
    db: Session = Depends(get_db),
):
    set_secret(db, GITHUB_TOKEN_KEY, data.token)
    return {
        "message": "GitHub Token 已加密更新。",
        **get_github_token_status(db),
    }


@router.delete("/github-token")
def remove_github_token(db: Session = Depends(get_db)):
    delete_secret(db, GITHUB_TOKEN_KEY)
    return {
        "message": "数据库 Token 已删除。",
        **get_github_token_status(db),
    }


@router.post("/github-token/test")
def test_github_token(
    data: GitHubRepositoryTest,
    db: Session = Depends(get_db),
):
    repository_url = data.repository_url.strip()
    parsed = urlparse(repository_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="仓库 URL 必须使用 HTTP(S)。")

    token = get_github_token(db)
    if not token:
        raise HTTPException(status_code=400, detail="尚未配置 GitHub Token。")

    try:
        refs_count = GitExecutor.test_repository_access(repository_url, token)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="GitHub 连接超时。")
    except (subprocess.CalledProcessError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="仓库访问失败，请检查 Token 权限和仓库 URL。",
        )

    return {
        "ok": True,
        "refs_count": refs_count,
        "message": f"仓库访问成功，共读取 {refs_count} 个远端引用。",
    }
