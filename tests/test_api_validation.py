"""任务和存储 API 边界测试。"""

import pytest
from fastapi import HTTPException

from app.api.jobs import _normalize_job_config, _safe_job_config, _validate_cron
from app.api.storages import _merge_storage_config, sanitize_storage_config
from app.db.models import JobType


def test_single_repository_config_is_normalized():
    config = _normalize_job_config(
        JobType.GIT,
        {"repository_url": "https://github.com/owner/repo.git"},
    )

    assert config["source_mode"] == "single"
    assert config["repository_url"] == "https://github.com/owner/repo.git"


def test_invalid_cron_is_rejected():
    with pytest.raises(HTTPException):
        _validate_cron("not a cron")


def test_job_secrets_are_not_returned():
    safe = _safe_job_config({
        "repository_url": "https://github.com/owner/repo.git",
        "gitlab_token": "secret",
        "ssh_key": "private-key",
    })

    assert "gitlab_token" not in safe
    assert "ssh_key" not in safe


def test_storage_secrets_are_masked_and_blank_updates_are_ignored():
    existing = {"url": "https://dav.example", "password": "secret"}
    merged = _merge_storage_config(existing, {"password": "", "url": "https://new"})
    safe = sanitize_storage_config(merged)

    assert merged["password"] == "secret"
    assert "password" not in safe
    assert safe["password_configured"] is True
