"""Tests for build_pipeline mode → stages router."""
import pytest

from app.services.sync_pipeline import (
    CalendarStage,
    IssuesFullStage,
    IssuesIncrementalStage,
    IssuesRefreshByKeysStage,
    MappingStage,
    ProjectsStage,
    WorklogsDeltaStage,
    WorklogsFullStage,
    build_pipeline,
)


class _Stub:
    def __init__(self, *a, **k):
        pass


def test_quick_mode_has_only_worklogs_delta():
    stages = build_pipeline(
        mode="quick",
        services={"sync": _Stub(), "calendar": _Stub(), "mapping": _Stub()},
    )
    assert [type(s) for s in stages] == [WorklogsDeltaStage]


def test_normal_mode_has_full_chain():
    stages = build_pipeline(
        mode="normal",
        services={"sync": _Stub(), "calendar": _Stub(), "mapping": _Stub()},
    )
    assert [type(s) for s in stages] == [
        CalendarStage,
        ProjectsStage,
        IssuesIncrementalStage,
        WorklogsDeltaStage,
        MappingStage,
    ]


def test_full_mode_uses_full_variants():
    stages = build_pipeline(
        mode="full",
        services={"sync": _Stub(), "calendar": _Stub(), "mapping": _Stub()},
    )
    types = [type(s) for s in stages]
    assert IssuesFullStage in types
    assert WorklogsFullStage in types


def test_team_mode_includes_refresh_by_keys():
    stages = build_pipeline(
        mode="team",
        services={"sync": _Stub(), "calendar": _Stub(), "mapping": _Stub()},
        team="QA",
    )
    assert [type(s) for s in stages] == [
        WorklogsDeltaStage,
        IssuesRefreshByKeysStage,
        MappingStage,
    ]


def test_team_mode_without_team_raises():
    with pytest.raises(ValueError, match="team"):
        build_pipeline(
            mode="team",
            services={"sync": _Stub(), "calendar": _Stub(), "mapping": _Stub()},
        )


def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="Unknown"):
        build_pipeline(
            mode="unknown",
            services={"sync": _Stub(), "calendar": _Stub(), "mapping": _Stub()},
        )
