"""备份执行错误信息的脱敏测试。"""

import subprocess
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.runner as runner_module
import app.db.session as session_module
from app.config import settings
from app.core.runner import _exception_summary
from app.db.models import BackupJob, JobType
from app.db.session import Base


def test_git_error_includes_stderr_and_redacts_tokens():
    error = subprocess.CalledProcessError(
        1,
        ["git", "clone"],
        stderr=(
            "fatal: unable to access "
            "'https://oauth2:glpat-secret-token@gitlab.example.com/repo.git/'"
        ),
    )

    message = _exception_summary(error)

    assert "fatal: unable to access" in message
    assert "glpat-secret-token" not in message
    assert "https://***@gitlab.example.com" in message


def test_runner_returns_record_id_after_database_session_closes(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'runner.db'}",
        connect_args={"check_same_thread": False},
    )
    test_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    db = test_session()
    job = BackupJob(
        name="runner-test",
        job_type=JobType.GIT,
        cron_expression="0 2 * * *",
        enabled=False,
        config="{}",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    db.close()

    class FakeExecutor:
        def execute(self, job_config: dict, work_dir: Path) -> Path:
            artifact = work_dir / "backup.tar.gz"
            artifact.write_bytes(b"backup")
            return artifact

    monkeypatch.setattr(session_module, "SessionLocal", test_session)
    monkeypatch.setattr(runner_module, "get_executor", lambda _: FakeExecutor())
    monkeypatch.setattr(settings, "TEMP_DIR", tmp_path)

    assert runner_module.run_backup_job(job_id, "manual") == 1
