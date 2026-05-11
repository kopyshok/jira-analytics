"""Тесты хелпера effective_estimate_hours."""
from app.services.allocation_estimates import effective_estimate_hours, has_override


class FakeBI:
    def __init__(self, a=None, d=None, q=None, o=None, r=0.5):
        self.estimate_analyst_hours = a
        self.estimate_dev_hours = d
        self.estimate_qa_hours = q
        self.estimate_opo_hours = o
        self.opo_analyst_ratio = r


class FakeAlloc:
    def __init__(self, oa=None, od=None, oq=None, oo=None, backlog=None):
        self.override_estimate_analyst_hours = oa
        self.override_estimate_dev_hours = od
        self.override_estimate_qa_hours = oq
        self.override_estimate_opo_hours = oo
        self.backlog_item = backlog


def test_inherit_when_all_overrides_null():
    bi = FakeBI(a=40, d=120, q=30, o=20)
    alloc = FakeAlloc(backlog=bi)
    eff = effective_estimate_hours(alloc)
    assert eff == {"analyst": 40.0, "dev": 120.0, "qa": 30.0, "opo": 20.0}


def test_override_when_any_non_null():
    bi = FakeBI(a=40, d=120, q=30, o=20)
    alloc = FakeAlloc(oa=25, od=80, oq=40, oo=20, backlog=bi)
    eff = effective_estimate_hours(alloc)
    assert eff == {"analyst": 25.0, "dev": 80.0, "qa": 40.0, "opo": 20.0}


def test_override_partial_null_treated_as_zero():
    bi = FakeBI(a=40, d=120, q=30, o=20)
    alloc = FakeAlloc(oa=25, od=None, oq=None, oo=None, backlog=bi)
    eff = effective_estimate_hours(alloc)
    assert eff == {"analyst": 25.0, "dev": 0.0, "qa": 0.0, "opo": 0.0}


def test_inherit_with_none_backlog_estimates():
    bi = FakeBI(a=None, d=None, q=None, o=None)
    alloc = FakeAlloc(backlog=bi)
    eff = effective_estimate_hours(alloc)
    assert eff == {"analyst": 0.0, "dev": 0.0, "qa": 0.0, "opo": 0.0}


def test_has_override_true_if_any():
    alloc = FakeAlloc(oa=10, od=None, oq=None, oo=None)
    assert has_override(alloc) is True


def test_has_override_false_if_all_null():
    alloc = FakeAlloc()
    assert has_override(alloc) is False
