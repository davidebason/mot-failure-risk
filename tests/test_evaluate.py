"""The evaluation: counts at tau, the scores, beating a baseline, calibration and the map.

The bands are invented, in the form the training run writes them: each entry's rows and ones per
band of probability 0.01 wide.
"""

import numpy as np
import pandas as pd
import pytest

from motrisk import evaluate


def cells(bands: dict[int, dict[int, tuple[int, int]]], tier: str = "small") -> pd.DataFrame:
    """Cells through fold_cells, from {entry: {band: (rows, ones)}}, every entry in one tier."""
    small_scores = pd.DataFrame({"entry": list(bands), "tier": tier})
    small_bands = pd.DataFrame(
        [
            {"entry": e, "band": b, "rows": r, "ones": o}
            for e, by_band in bands.items()
            for b, (r, o) in by_band.items()
        ]
    )
    empty_scores = pd.DataFrame({"entry": pd.Series(dtype=int), "tier": pd.Series(dtype=str)})
    empty_bands = small_bands.iloc[0:0]
    return evaluate.fold_cells(small_scores, small_bands, empty_scores, empty_bands)


# One entry: bands 0.05, 0.12, 0.24, 0.25, 0.30 and 0.60, each with its rows and ones.
ONE = {1: {5: (100, 2), 12: (50, 5), 24: (10, 1), 25: (10, 3), 30: (20, 6), 60: (10, 7)}}


@pytest.mark.parametrize(
    "tau, expected",
    [
        # From 0.10: bands 12, 24, 25, 30 and 60.
        (0.1, (22, 78, 2)),
        # From 0.25: bands 25, 30 and 60; the band starting at 0.25 is flagged, 0.24 is not.
        (0.25, (16, 24, 8)),
        # From 0.50: band 60 only.
        (0.5, (7, 3, 17)),
    ],
)
def test_counts_at_each_tau(tau, expected):
    """Test 1: the counts at 0.1, 0.25 and 0.5 are those computed by hand."""
    c = evaluate.counts_at(cells(ONE), tau)
    assert tuple(int(c[k].iloc[0]) for k in ("tp", "fp", "fn")) == expected


def test_nothing_flagged():
    """Test 2: nothing flagged gives an empty precision and a recall of 0."""
    s = evaluate.score(evaluate.counts_at(cells({1: {5: (100, 2), 30: (20, 6)}}), 0.5))
    assert np.isnan(s["precision"])
    assert s["recall"] == 0
    assert np.isnan(s["promised"])


def test_beats():
    """Test 3: true only when both precision and recall are higher."""
    base = pd.Series({"precision": 0.2, "recall": 0.2})
    assert evaluate.beats(pd.Series({"precision": 0.3, "recall": 0.3}), base)
    assert not evaluate.beats(pd.Series({"precision": 0.3, "recall": 0.1}), base)
    assert not evaluate.beats(pd.Series({"precision": 0.1, "recall": 0.3}), base)
    assert not evaluate.beats(pd.Series({"precision": 0.2, "recall": 0.2}), base)
    assert not evaluate.beats(pd.Series({"precision": np.nan, "recall": 0.3}), base)


def test_promised_precision_from_midpoints():
    """Test 4: 1,000 cells in band 0.50 and 200 in band 0.70 promise 0.5383."""
    s = evaluate.score(evaluate.counts_at(cells({1: {50: (1000, 500), 70: (200, 150)}}), 0.5))
    assert s["promised"] == pytest.approx((1000 * 0.505 + 200 * 0.705) / 1200)
    assert round(s["promised"], 4) == 0.5383


def test_is_off_at_the_edges():
    """Test 5: at a promise of 53.8%, 48.5% is not off and 48.3% is; at 15%, the gap is 5 points."""
    assert not evaluate.is_off(0.485, 0.538)
    assert evaluate.is_off(0.483, 0.538)
    assert evaluate.allowed_gap(0.15) == pytest.approx(0.05)
    assert not evaluate.is_off(0.199, 0.15)
    assert evaluate.is_off(0.201, 0.15)


def test_groups():
    """Test 6: the groups add up to the pooled counts; precision is empty below 100 flags and
    recall below 100 problems."""
    counts = pd.DataFrame(
        {
            "entry": [1, 2, 3, 4],
            "tier": "small",
            "tp": [60, 0, 5, 10],
            "fp": [50, 0, 20, 5],
            "fn": [10, 30, 40, 200],
            "promised": 0.0,
        }
    )
    groups = pd.DataFrame({"entry": [1, 2, 3, 4], "group_id": [10, 10, 20, 30]})
    g = evaluate.by_group(counts, groups).set_index("group_id")
    pooled = evaluate.score(counts)
    for k in ("tp", "fp", "fn"):
        assert g[k].sum() == pooled[k]
    # Group 10: 100 problems and 110 flags, both read.
    assert g.loc[10, "precision"] == pytest.approx(60 / 110)
    assert g.loc[10, "recall"] == pytest.approx(60 / 100)
    # Group 20: 45 problems and 25 flags, neither read, the counts kept.
    assert np.isnan(g.loc[20, "precision"]) and np.isnan(g.loc[20, "recall"])
    assert (g.loc[20, "tp"], g.loc[20, "fp"], g.loc[20, "fn"]) == (5, 20, 40)
    # Group 30: 210 problems and 15 flags, recall read, precision not.
    assert np.isnan(g.loc[30, "precision"])
    assert g.loc[30, "recall"] == pytest.approx(10 / 210)


def test_isotonic_map():
    """Test 7: observed rates that already rise come back unchanged, and the map never decreases."""
    rising = cells({1: {10: (1000, 50), 30: (1000, 200)}, 2: {60: (1000, 700)}})
    m = evaluate.isotonic_map(rising)
    assert m.predict([0.105, 0.305, 0.605]) == pytest.approx([0.05, 0.2, 0.7])
    falling = cells({1: {10: (1000, 300), 30: (1000, 100), 60: (1000, 700)}})
    grid = np.linspace(0, 1, 101)
    assert np.all(np.diff(evaluate.isotonic_map(falling).predict(grid)) >= 0)


def test_map_ignores_the_current_year():
    """Test 8: the map is fitted on the previous year only, so changing the current year's ones
    leaves every mapped probability unchanged."""
    m = evaluate.isotonic_map(cells({1: {10: (1000, 50), 30: (1000, 200), 60: (1000, 700)}}))
    current = cells({1: {10: (500, 10), 40: (300, 100), 60: (100, 90)}})
    changed = current.assign(ones=current["rows"] - current["ones"])
    a, b = evaluate.remap(current, m), evaluate.remap(changed, m)
    assert a["p"].tolist() == b["p"].tolist()
    assert a["p"].tolist() == pytest.approx(m.predict(current["p"]).tolist())
