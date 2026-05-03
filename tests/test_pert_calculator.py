"""Тесты вероятностного CPM (PERT)."""

import math
from app.services.pert_calculator import (
    compute_pert_phase_duration,
    aggregate_path_pert,
    p_quantile_finish,
)


def test_pert_phase_duration_classic_formula():
    """t_e = (t_o + 4·t_m + t_p) / 6, σ = (t_p - t_o) / 6."""
    t_e, sigma = compute_pert_phase_duration(t_o=2.0, t_m=3.0, t_p=8.0)
    assert math.isclose(t_e, (2 + 12 + 8) / 6)
    assert math.isclose(sigma, (8 - 2) / 6)


def test_aggregate_path_pert_sums_means_and_variances():
    """Длительность пути = sum(t_e), variance = sum(σ²)."""
    phases = [(2.0, 3.0, 8.0), (1.0, 2.0, 4.0)]
    mean, sigma = aggregate_path_pert(phases)
    assert math.isclose(mean, ((2 + 12 + 8) / 6) + ((1 + 8 + 4) / 6))
    expected_var = ((8 - 2) / 6) ** 2 + ((4 - 1) / 6) ** 2
    assert math.isclose(sigma, math.sqrt(expected_var))


def test_p_quantile_finish_p50_equals_mean_p90_greater():
    """P50 = mean (для нормального приближения), P90 > mean."""
    p50 = p_quantile_finish(mean=10.0, sigma=2.0, p=0.5)
    p90 = p_quantile_finish(mean=10.0, sigma=2.0, p=0.9)
    assert math.isclose(p50, 10.0)
    assert p90 > 10.0
    assert math.isclose(p90, 10.0 + 2.0 * 1.2816, abs_tol=0.01)
