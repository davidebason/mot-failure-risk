"""Scoring again for the Brier score: the fine bands, their sums, and the small models rebuilt."""

import numpy as np
import pandas as pd
import pytest

from motrisk import folds, rescore, small_models


@pytest.mark.parametrize(
    "p, band",
    [
        (0.0, 0),
        (9e-7, 0),
        # 10 log10(2) = 3.01, so the fourth band of the first decade.
        (2e-6, 4),
        # 10 log10(50) = 16.99.
        (5e-5, 17),
        (0.0099, 40),
        (0.01, 41),
        (0.015, 41),
        (0.5, 90),
        (1.0, 139),
    ],
)
def test_fine_band(p, band):
    assert rescore.fine_band(np.array([p]))[0] == band


def test_fine_bands_add_up_to_the_runs_bands():
    """Every probability's fine band falls in the band folds.tally gives it, the edges included."""
    rng = np.random.default_rng(0)
    p = np.concatenate([rng.random(10_000), rng.random(10_000) * 0.02, np.arange(101) / 100])
    run = np.minimum((p * folds.BANDS).astype(np.int64), folds.BANDS - 1)
    assert (rescore.coarse_of(rescore.fine_band(p)) == run).all()
    assert rescore.fine_band(p).max() < rescore.FINE_BANDS


def test_fine_tally_sums():
    """Cells carrying several rows add each row's p, p^2, and p for each one."""
    t = rescore.fine_tally(np.array([0.3, 0.3, 0.002]), np.array([4, 1, 10]), np.array([1, 0, 2]))
    b, low = rescore.fine_band(np.array([0.3]))[0], rescore.fine_band(np.array([0.002]))[0]
    assert (t["rows"][b], t["ones"][b]) == (5, 1)
    assert t["sum_p"][b] == pytest.approx(1.5)
    assert t["sum_p2"][b] == pytest.approx(5 * 0.09)
    assert t["sum_p_ones"][b] == pytest.approx(0.3)
    assert (t["rows"][low], t["ones"][low]) == (10, 2)
    assert t["sum_p_ones"][low] == pytest.approx(0.004)
    assert t["rows"].sum() == 15


def test_moved_counts_rows_that_changed_band():
    t = rescore.fine_tally(np.array([0.255] * 10 + [0.05] * 90), np.ones(100), np.zeros(100))
    run_rows = np.zeros(folds.BANDS, dtype=np.int64)
    run_rows[25], run_rows[5] = 10, 90
    zeros = np.zeros(folds.BANDS, dtype=np.int64)
    assert rescore.moved(1, t, run_rows, zeros) == 0
    run_rows[25], run_rows[24] = 9, 1
    with pytest.raises(SystemExit, match="changed band"):
        rescore.moved(1, t, run_rows, zeros)
    run_rows[24] = 2
    with pytest.raises(SystemExit, match="not the run's"):
        rescore.moved(1, t, run_rows, zeros)


def test_a_small_model_rebuilt_predicts_as_the_fitted_one():
    """The saved weights give the fitted model's probabilities to the last bit."""
    u = np.array([0, 0, 1, 1, 0, 1, 0, 0])
    g = np.array([0, 1, 1, 0, 1, 1, 0, 1])
    days = np.array([200, 365, 800, 400, 1200, 365, 365, 900])
    y = np.array([0, 0, 1, 1, 0, 1, 0, 1])
    n = np.array([500, 300, 40, 60, 200, 80, 900, 30])
    fitted = small_models.fit_counts(u, g, days, y, n)
    weights = pd.Series(
        [fitted.intercept_[0], *fitted.coef_[0]], index=["intercept", *small_models.SMALL_WEIGHTS]
    )
    x = small_models.small_inputs(u, g, days)
    rebuilt = rescore.small_model(weights).predict_proba(x)
    assert (rebuilt == fitted.predict_proba(x)).all()
