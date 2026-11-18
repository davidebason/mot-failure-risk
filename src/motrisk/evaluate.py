"""The evaluation: scores at any tau from the bands, against the baselines, and calibration.

Every model's results are kept as each entry's rows and ones in bands of probability 0.01 wide,
band b holding the probabilities from b/100 to (b + 1)/100 (folds.tally). At a cut-off tau that
is a multiple of 0.01, the cells flagged are exactly those of the bands from 100 tau, so the true
positives, false positives and false negatives follow exactly. The probability a band promises is
taken as its midpoint, (b + 0.5)/100, which is within 0.5 points of the cells' own mean, the
author's decision of 2026-11-16; the midpoint also flags exactly the bands from 100 tau, since
(b + 0.5)/100 >= tau when and only when b >= 100 tau.

- **Beating a baseline** means a higher precision and a higher recall at the same tau.
- **A test year is off** when, at a tau, the precision delivered differs from the precision
  promised, the mean probability of the cells flagged, by more than 5 points or 10% of the
  promised value, whichever is larger.
- **The step if off** is an isotonic map fitted on the previous test year's bands, pooled over
  every entry and weighted by rows, and applied to the year's bands.
- **The money saved**, at tau = t/m, is the share of what leaving every problem to the test costs
  that checking the flags saves: (m TP - t (TP + FP)) / (m (TP + FN)), which is
  recall (1 - tau / precision), the author's decision of 2026-11-17.
- **The Brier score** is the mean of (p - y)^2 over every cell, an entry on a test row of its
  classes, computed exactly from the sums the test years were scored again for (rescore.py); its
  **skill** is 1 - BS / BS of the base rate, each entry at its share of ones in the training rows,
  the author's decision of the same day. Reliability, resolution and uncertainty are taken over
  the fine bands pooled over every entry, with the two terms within the bands that make them add
  up to the score exactly (Stephenson, Coelho and Jolliffe, 2008).

This module computes and reads no file; analysis/01_next_test.py reads the run's files and
writes the results.
"""

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from motrisk import folds, rescore

TAUS = (0.1, 0.25, 0.5)
# Precision is read for a group only from this many flags, recall only from this many problems.
MIN_FLAGS = 100
MIN_PROBLEMS = 100
# A test year is off when delivered and promised precision differ by more than the larger of these.
OFF_POINTS = 0.05
OFF_SHARE = 0.10


def fold_cells(small_scores, small_bands, full_scores, full_bands) -> pd.DataFrame:
    """One fold's bands for every entry: entry, tier, band, p, rows, ones.

    The small file lists every entry with its tier and holds the bands of all but the full ones,
    which the full file holds. An entry with no ones in the training rows, tier none, is counted as
    the base rate, which DATA.md defines as 0 for it. p is the band's midpoint. Stops unless each
    entry is listed once and the full entries are the same in both files.
    """
    if small_scores["entry"].duplicated().any() or full_scores["entry"].duplicated().any():
        raise SystemExit("an entry is listed twice in a scores file")
    full = set(small_scores.loc[small_scores["tier"] == "full", "entry"])
    if full != set(full_scores["entry"]):
        raise SystemExit("the small and the full files disagree on the full entries")
    tiers = small_scores[["entry", "tier"]].replace({"tier": {"none": "base_rate"}})
    bands = pd.concat(
        [small_bands[~small_bands["entry"].isin(full)], full_bands[full_bands["entry"].isin(full)]]
    )
    cells = bands[["entry", "band", "rows", "ones"]].merge(tiers, on="entry", how="left")
    if cells["tier"].isna().any():
        raise SystemExit("a band belongs to no listed entry")
    cells["p"] = (cells["band"] + 0.5) / folds.BANDS
    return cells[["entry", "tier", "band", "p", "rows", "ones"]].reset_index(drop=True)


def counts_at(cells: pd.DataFrame, tau: float) -> pd.DataFrame:
    """Each entry's counts at tau: entry, tier, tp, fp, fn, and promised, the sum of p over the
    cells flagged, so that promised / (tp + fp) is the mean probability of the flags."""
    flagged = cells["p"] >= tau
    c = cells.assign(
        tp=np.where(flagged, cells["ones"], 0),
        fp=np.where(flagged, cells["rows"] - cells["ones"], 0),
        fn=np.where(flagged, 0, cells["ones"]),
        promised=np.where(flagged, cells["p"] * cells["rows"], 0.0),
    )
    return c.groupby(["entry", "tier"], as_index=False)[["tp", "fp", "fn", "promised"]].sum()


def score(counts: pd.DataFrame) -> pd.Series:
    """The counts added up, with precision, recall and promised precision.

    Precision is empty (NaN) when nothing is flagged, recall when there is no problem, and
    promised precision when nothing is flagged or the counts carry no promise, as a baseline's.
    """
    tp, fp, fn = (int(counts[k].sum()) for k in ("tp", "fp", "fn"))
    flags = tp + fp
    promised = counts["promised"].sum() / flags if "promised" in counts and flags else np.nan
    return pd.Series(
        {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": tp / flags if flags else np.nan,
            "recall": tp / (tp + fn) if tp + fn else np.nan,
            "promised": promised,
        }
    )


def beats(a: pd.Series, b: pd.Series) -> bool:
    """Whether a beats b: a higher precision and a higher recall. An empty one beats nothing."""
    return bool(a["precision"] > b["precision"] and a["recall"] > b["recall"])


def by_group(counts: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    """The counts of each group: group_id, problems, flags, tp, fp, fn, precision, recall.

    groups maps each entry to its group_id. Precision is read only from MIN_FLAGS flags and
    recall only from MIN_PROBLEMS problems; below them the cell is empty, the counts kept.
    """
    g = counts.merge(groups[["entry", "group_id"]], on="entry", how="left")
    if g["group_id"].isna().any():
        raise SystemExit("an entry has no group")
    out = g.groupby("group_id", as_index=False)[["tp", "fp", "fn"]].sum()
    out["problems"] = out["tp"] + out["fn"]
    out["flags"] = out["tp"] + out["fp"]
    out["precision"] = (out["tp"] / out["flags"]).where(out["flags"] >= MIN_FLAGS)
    out["recall"] = (out["tp"] / out["problems"]).where(out["problems"] >= MIN_PROBLEMS)
    return out[["group_id", "problems", "flags", "tp", "fp", "fn", "precision", "recall"]]


def allowed_gap(promised: float) -> float:
    """How far delivered precision may stray from promised: 5 points or 10% of it, the larger."""
    return max(OFF_POINTS, OFF_SHARE * promised)


def is_off(delivered: float, promised: float) -> bool:
    """Whether delivered precision strays from promised by more than the allowed gap."""
    return bool(abs(delivered - promised) > allowed_gap(promised))


def curve(cells: pd.DataFrame) -> pd.DataFrame:
    """The calibration curve pooled over every entry: band, p, rows, ones, observed."""
    c = cells.groupby(["band", "p"], as_index=False)[["rows", "ones"]].sum()
    c["observed"] = c["ones"] / c["rows"]
    return c


def isotonic_map(previous: pd.DataFrame) -> IsotonicRegression:
    """A map from probability to the rate observed, never decreasing, fitted on the previous test
    year's cells pooled over every entry and weighted by rows. Outside the probabilities it saw,
    it keeps the nearest value."""
    c = curve(previous)
    return IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(
        c["p"], c["observed"], sample_weight=c["rows"]
    )


def remap(cells: pd.DataFrame, mapping: IsotonicRegression) -> pd.DataFrame:
    """The same cells with each band's probability replaced by the map's, ready for counts_at."""
    return cells.assign(p=mapping.predict(cells["p"]))


def saved(s: pd.Series, tau: float) -> float:
    """The share of the cost of leaving every problem to the test that checking the flags saves,
    at tau = t/m: (TP - tau (TP + FP)) / (TP + FN). 0 when nothing is flagged; negative when the
    checks cost more than the problems they find; empty when there is no problem."""
    problems = s["tp"] + s["fn"]
    return (s["tp"] - tau * (s["tp"] + s["fp"])) / problems if problems else np.nan


def fine_cells(small_fine, full_fine, tiers: pd.Series) -> pd.DataFrame:
    """One fold's fine bands for every entry: entry, tier, fine_band and the sums.

    The small file holds every entry but the full ones, which the full file holds; tiers gives
    each entry's tier, as fold_cells reads it. Stops unless the full file holds exactly the full
    entries.
    """
    full = set(tiers.index[tiers == "full"])
    if set(full_fine["entry"]) != full or full & set(small_fine["entry"]):
        raise SystemExit("the fine bands do not hold the full entries in the full file only")
    c = pd.concat([small_fine, full_fine])[["entry", "fine_band", *rescore.SUMS]]
    return c.assign(tier=c["entry"].map(tiers)).reset_index(drop=True)


def reference_cells(reference: pd.DataFrame, totals: pd.DataFrame) -> pd.DataFrame:
    """The base rate's fine bands: every test row of an entry at the entry's share of ones in the
    training rows, 0 when it has none there. reference holds entry, train_rows and train_ones;
    totals each entry's test rows and ones, and tier."""
    r = reference.set_index("entry")
    rate = (r["train_ones"] / r["train_rows"]).where(r["train_ones"] > 0, 0.0)
    t = totals.set_index("entry")
    p = rate.reindex(t.index)
    if p.isna().any():
        raise SystemExit("an entry scored has no base rate")
    return pd.DataFrame(
        {
            "entry": t.index,
            "fine_band": rescore.fine_band(p.to_numpy()),
            "rows": t["rows"].to_numpy(),
            "ones": t["ones"].to_numpy(),
            "sum_p": (p * t["rows"]).to_numpy(),
            "sum_p2": (p * p * t["rows"]).to_numpy(),
            "sum_p_ones": (p * t["ones"]).to_numpy(),
            "tier": t["tier"].to_numpy(),
        }
    )


def brier(c: pd.DataFrame) -> float:
    """The Brier score of cells with the sums: (sum p^2 - 2 sum p over the ones + ones) / rows."""
    rows = c["rows"].sum()
    return (c["sum_p2"].sum() - 2 * c["sum_p_ones"].sum() + c["ones"].sum()) / rows


def decomposition(c: pd.DataFrame) -> dict[str, float]:
    """The Brier score split over the fine bands pooled over every entry, n_k cells in band k
    with mean probability p_k and rate o_k, o the rate over all N cells:

        reliability  sum n_k (p_k - o_k)^2 / N, how far the probabilities are from the rates;
        resolution   sum n_k (o_k - o)^2 / N, how far the bands' rates are from the overall rate;
        uncertainty  o (1 - o), the same for every model of the same cells;
        within_variance, within_covariance: of p, and of p with y, inside each band, which make
        BS = reliability - resolution + uncertainty + within_variance - 2 within_covariance.

    Stops unless the terms add up to the Brier score.
    """
    b = c.groupby("fine_band")[rescore.SUMS].sum()
    b = b[b["rows"] > 0]
    n, rate = b["rows"].sum(), b["ones"].sum() / b["rows"].sum()
    p_k, o_k = b["sum_p"] / b["rows"], b["ones"] / b["rows"]
    out = {
        "brier": brier(b),
        "reliability": (b["rows"] * (p_k - o_k) ** 2).sum() / n,
        "resolution": (b["rows"] * (o_k - rate) ** 2).sum() / n,
        "uncertainty": rate * (1 - rate),
        "within_variance": (b["sum_p2"] - b["sum_p"] ** 2 / b["rows"]).sum() / n,
        "within_covariance": (b["sum_p_ones"] - b["sum_p"] * b["ones"] / b["rows"]).sum() / n,
    }
    parts = (
        out["reliability"]
        - out["resolution"]
        + out["uncertainty"]
        + out["within_variance"]
        - 2 * out["within_covariance"]
    )
    if not np.isclose(parts, out["brier"], rtol=1e-9, atol=1e-15):
        raise SystemExit(f"the Brier score's terms add up to {parts}, not {out['brier']}")
    return out
