"""Три способа расчёта дают ожидаемые числа и корректно ведут себя на пустых данных."""
from app.services.kpi.calculators import ratio, norm_to_fact, score_to_max


def test_ratio_plain():
    r = ratio(numerator=8, denominator=10, invert=False, cap_at_100=True)
    assert r.value == 80.0
    assert r.has_data is True


def test_ratio_inverted_for_bugs():
    r = ratio(numerator=3, denominator=15, invert=True, cap_at_100=True)
    assert r.value == 80.0


def test_ratio_zero_numerator_gives_full_when_inverted():
    r = ratio(numerator=0, denominator=15, invert=True, cap_at_100=True)
    assert r.value == 100.0


def test_ratio_no_denominator_is_no_data():
    r = ratio(numerator=0, denominator=0, invert=False, cap_at_100=True)
    assert r.has_data is False
    assert r.value is None


def test_norm_to_fact_capped():
    assert norm_to_fact(norm=80.0, facts=[75.0]).value == 100.0
    assert round(norm_to_fact(norm=70.0, facts=[100.0]).value, 1) == 70.0
    assert norm_to_fact(norm=70.0, facts=[]).has_data is False


def test_score_to_max():
    r = score_to_max(scores=[[5, 4, 3], [4, 4, 4]], score_max=5.0)
    assert round(r.value, 1) == 80.0
    assert score_to_max(scores=[], score_max=5.0).has_data is False
