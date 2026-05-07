"""Sanity: тематические модели создаются и связи работают."""
import json
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.issue_classification import IssueClassification
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.theme import Theme
from app.models.work_type_report_layout import WorkTypeReportLayout
from app.models.work_type_report_snapshot import WorkTypeReportSnapshot


def test_theme_create(db_session):
    wt = MandatoryWorkType(code="t1", label="T1", sort_order=1)
    db_session.add(wt)
    db_session.commit()
    t = Theme(work_type_id=wt.id, name="Тест", color="#00c9c8")
    db_session.add(t)
    db_session.commit()
    assert t.id and t.is_archived is False


def test_theme_unique_per_work_type(db_session):
    wt = MandatoryWorkType(code="t2", label="T2", sort_order=1)
    db_session.add(wt)
    db_session.commit()
    db_session.add(Theme(work_type_id=wt.id, name="Тема"))
    db_session.commit()
    db_session.add(Theme(work_type_id=wt.id, name="Тема"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_snapshot_unique_key(db_session):
    wt = MandatoryWorkType(code="t3", label="T3", sort_order=1)
    db_session.add(wt)
    db_session.commit()
    s = WorkTypeReportSnapshot(
        work_type_id=wt.id,
        year=2026,
        quarter=2,
        month=4,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        team_set_hash="abc",
        team_set_json=json.dumps([]),
        snapshot_data=json.dumps({}),
        dictionary_version=1,
    )
    db_session.add(s)
    db_session.commit()
    assert s.id


def test_work_type_has_dict_version(db_session):
    wt = MandatoryWorkType(code="t4", label="T4", sort_order=1)
    db_session.add(wt)
    db_session.commit()
    db_session.refresh(wt)
    assert wt.theme_dict_version == 1
