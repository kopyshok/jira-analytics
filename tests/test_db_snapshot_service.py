"""Снимок БД: данные переносятся, секреты не уезжают."""
import gzip
import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.database import Base
from app.models.app_setting import AppSetting
from app.models.issue import Issue
from app.models.project import Project
from app.models.user import User, UserRole
from app.services import db_snapshot_service as snapshot


@pytest.fixture(autouse=True)
def _export_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(snapshot, "_job", snapshot.ExportJob())
    yield


def _seed(db_session):
    project = Project(id=str(uuid.uuid4()), jira_project_id="p1", key="PRJ", name="Project")
    db_session.add(project)
    db_session.flush()

    parent_id = str(uuid.uuid4())
    child_id = str(uuid.uuid4())
    # Ребёнок раньше родителя: снимок обязан переупорядочить их сам.
    db_session.add(Issue(id=child_id, jira_issue_id="2", key="P-2", summary="child", issue_type="Task", status="Open", project_id=project.id, parent_id=parent_id))
    db_session.add(Issue(id=parent_id, jira_issue_id="1", key="P-1", summary="parent", issue_type="Epic", status="Open", project_id=project.id))
    db_session.add(
        User(
            id=str(uuid.uuid4()),
            email="analyst@example.com",
            password_hash="prod-secret-hash",
            display_name="Analyst",
            role=UserRole.admin,
        )
    )
    db_session.add(AppSetting(id=str(uuid.uuid4()), key="jira_api_token", value="real-token"))
    db_session.add(AppSetting(id=str(uuid.uuid4()), key="jira_base_url", value="https://x"))
    db_session.commit()


def test_snapshot_copies_data_and_scrubs_secrets(db_session, engine, tmp_path):
    _seed(db_session)

    job = snapshot.build_snapshot(source=engine)

    assert job.state == "done", job.error
    assert job.per_table["issues"] == 2
    assert job.local_password

    restored = tmp_path / "restored.db"
    with gzip.open(job.file_path, "rb") as src, open(restored, "wb") as dst:
        shutil.copyfileobj(src, dst)

    target = create_engine(f"sqlite:///{restored}")
    with target.connect() as conn:
        keys = {row[0] for row in conn.execute(text("SELECT key FROM issues"))}
        assert keys == {"P-1", "P-2"}

        hashes = [row[0] for row in conn.execute(text("SELECT password_hash FROM users"))]
        assert hashes and "prod-secret-hash" not in hashes

        settings = dict(conn.execute(text("SELECT key, value FROM app_settings")).all())
        assert settings["jira_api_token"] is None
        assert settings["jira_base_url"] == "https://x"

        # Локальный alembic upgrade head должен видеть уже применённую версию.
        assert conn.execute(text("SELECT count(*) FROM alembic_version")).scalar() is not None
    target.dispose()

    assert Path(job.file_path).exists()


def test_second_export_replaces_previous_file(db_session, engine):
    _seed(db_session)

    first = snapshot.build_snapshot(source=engine)
    first_path = first.file_path
    assert first.state == "done", first.error

    second = snapshot.build_snapshot(source=engine)
    assert second.state == "done", second.error
    assert not Path(first_path).exists()
    assert Path(second.file_path).exists()


def test_skipped_tables_are_not_copied(db_session, engine):
    _seed(db_session)

    job = snapshot.build_snapshot(source=engine)

    assert job.state == "done", job.error
    assert set(job.per_table) & snapshot.SKIP_TABLES == set()
    assert set(job.per_table) <= {t.name for t in Base.metadata.sorted_tables}
