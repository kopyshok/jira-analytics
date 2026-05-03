"""PERT-расчёт вероятностного CPM.

Формулы:
  t_e = (t_o + 4·t_m + t_p) / 6      — ожидание
  σ   = (t_p - t_o) / 6              — стандартное отклонение
  σ²  = ((t_p - t_o) / 6)²           — дисперсия

Сумма независимых нормальных = нормальное (CLT для пути).
P-квантиль: mean + z(p) · sigma_path, где z(p) — обратная нормальная.
"""

from __future__ import annotations

import math
from typing import List, Tuple


def compute_pert_phase_duration(
    t_o: float, t_m: float, t_p: float
) -> Tuple[float, float]:
    """Возвращает (ожидание, sigma) для одной фазы по trio оценок."""
    t_e = (t_o + 4 * t_m + t_p) / 6.0
    sigma = (t_p - t_o) / 6.0
    return t_e, sigma


def aggregate_path_pert(
    phases: List[Tuple[float, float, float]],
) -> Tuple[float, float]:
    """Сумма по пути: mean = Σt_e, sigma = sqrt(Σσ²)."""
    means = []
    variances = []
    for t_o, t_m, t_p in phases:
        t_e, sigma = compute_pert_phase_duration(t_o, t_m, t_p)
        means.append(t_e)
        variances.append(sigma * sigma)
    total_mean = sum(means)
    total_sigma = math.sqrt(sum(variances))
    return total_mean, total_sigma


_Z = {
    0.5: 0.0,
    0.7: 0.5244,
    0.8: 0.8416,
    0.85: 1.0364,
    0.9: 1.2816,
    0.95: 1.6449,
    0.99: 2.3263,
}


def p_quantile_finish(mean: float, sigma: float, p: float) -> float:
    """Возвращает P-квантиль времени завершения (mean + z(p)·sigma)."""
    z = _Z.get(round(p, 2))
    if z is None:
        keys = sorted(_Z.keys())
        for i, k in enumerate(keys):
            if k >= p:
                if i == 0:
                    z = _Z[k]
                else:
                    k_prev = keys[i - 1]
                    z = _Z[k_prev] + (_Z[k] - _Z[k_prev]) * (p - k_prev) / (k - k_prev)
                break
        else:
            z = _Z[keys[-1]]
    return mean + z * sigma
