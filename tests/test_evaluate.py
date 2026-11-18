"""The evaluation: counts at tau, the scores, beating a baseline, calibration and the map.

The bands are invented, in the form the training run writes them: each entry's rows and ones per
band of probability 0.01 wide.
"""

import numpy as np
import pandas as pd
import pytest

from motrisk import evaluate, rescore


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


def test_money_saved():
    """Two problems found, three checks for nothing, five left to the test, at tau 0.25: the
    checks cost 5 t = 1.25 m and save 2 m, out of 7 m."""
    s = pd.Series({"tp": 2, "fp": 3, "fn": 5})
    assert evaluate.saved(s, 0.25) == pytest.approx(0.75 / 7)
    recall, precision = 2 / 7, 2 / 5
    assert evaluate.saved(s, 0.25) == pytest.approx(recall * (1 - 0.25 / precision))
    assert evaluate.saved(s, 0.5) < 0
    assert evaluate.saved(pd.Series({"tp": 0, "fp": 0, "fn": 4}), 0.25) == 0
    assert np.isnan(evaluate.saved(pd.Series({"tp": 0, "fp": 3, "fn": 0}), 0.25))


def sums(p, y, entry=1) -> pd.DataFrame:
    """Cells one row each, through rescore.fine_tally, as rescore writes them."""
    t = rescore.fine_tally(np.asarray(p, dtype=float), np.ones(len(p)), np.asarray(y))
    b = np.flatnonzero(t["rows"])
    return pd.DataFrame({"entry": entry, "fine_band": b, **{k: t[k][b] for k in rescore.SUMS}})


# Ten vehicles, two with the problem: the example of 2026-11-17.
Y = [1, 1, 0, 0, 0, 0, 0, 0, 0, 0]


@pytest.mark.parametrize(
    "p, expected",
    [
        # A, the base rate: honest, separates nothing.
        ([0.2] * 10, (0.16, 0.0, 0.0)),
        # B: 0.5 to four vehicles, two of which have it, 0 to six that do not.
        ([0.5] * 4 + [0.0] * 6, (0.10, 0.0, 0.06)),
        # C: the same four at 0.9, so it separates as B does and overstates.
        ([0.9] * 4 + [0.0] * 6, (0.164, 0.064, 0.06)),
    ],
)
def test_brier_and_its_terms(p, expected):
    d = evaluate.decomposition(sums(p, Y))
    bs, reliability, resolution = expected
    assert d["brier"] == pytest.approx(bs)
    assert d["reliability"] == pytest.approx(reliability)
    assert d["resolution"] == pytest.approx(resolution)
    assert d["uncertainty"] == pytest.approx(0.16)
    assert d["within_variance"] == pytest.approx(0.0)


def test_the_terms_add_up_with_spread_inside_the_bands():
    """Probabilities spread inside each band: the within-band terms close the sum."""
    rng = np.random.default_rng(1)
    p = rng.random(5_000) ** 3
    y = (rng.random(5_000) < p).astype(int)
    d = evaluate.decomposition(sums(p, y))
    assert d["brier"] == pytest.approx(np.mean((p - y) ** 2))
    assert d["within_variance"] > 0


def test_the_base_rate_reference():
    """Each entry's test rows at its share of ones in the training rows; 0 with none there."""
    reference = pd.DataFrame({"entry": [1, 2], "train_rows": [100, 50], "train_ones": [10, 0]})
    totals = pd.DataFrame({"entry": [1, 2], "rows": [20, 30], "ones": [3, 1], "tier": "small"})
    r = evaluate.reference_cells(reference, totals).set_index("entry")
    assert r.loc[1, "sum_p"] == pytest.approx(2.0)
    assert r.loc[1, "sum_p_ones"] == pytest.approx(0.3)
    assert r.loc[2, "sum_p"] == 0
    # 17 rows at 0.1 without the entry, 3 with it; 29 rows at 0 without, 1 with.
    expected = (17 * 0.01 + 3 * 0.81 + 1) / 50
    assert evaluate.brier(r.reset_index()) == pytest.approx(expected)
    with pytest.raises(SystemExit, match="no base rate"):
        evaluate.reference_cells(reference[reference["entry"] == 1], totals)
