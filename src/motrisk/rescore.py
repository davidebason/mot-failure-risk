"""The test years scored again from the weights each run kept, for the Brier score.

The runs kept each entry's rows and ones per band of probability 0.01 wide (folds.tally), which
is all that precision, recall and the money saved need. The Brier score needs three sums more:
of p, of p squared, and of p over the cells that hold the entry. Its split into reliability and
resolution also needs bands finer than 0.01 below 0.01, where 99% of the cells lie. Nothing is
fitted again: each model's probabilities are recomputed from its saved weights on the test
year's rows, and the bands they fall in are checked against those the run wrote.

The fine bands, FINE_BANDS of them: band 0 holds p under 1e-6; bands 1 to 40 split 1e-6 to 0.01
into ten bands a decade; bands 41 to 139 are the run's bands 1 to 99, 0.01 wide. The fine bands
under 0.01 add up to the run's band 0, so the run's bands follow from the fine ones exactly.

Run from the repository's root, after the run of the fold:

    python src/motrisk/rescore.py small 2025                     # small and base-rate entries
    python src/motrisk/rescore.py small 2025 --shuffled
    python src/motrisk/rescore.py full 2025                      # both kinds of the fold
    python src/motrisk/rescore.py full 2025 --encoding pooled    # the second model

Writes beside the run's files, in folds.TRAIN_DIRS[encoding]: small_<kind>_<year>_fine.csv and
full_<kind>_<year>_fine.csv, each entry's rows, ones and sums per fine band; and
small_<kind>_<year>_reference.csv, every entry's tier and its rows and ones in the training
years, from which its base rate follows.
"""

import argparse
import csv
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from motrisk import folds, full_models, small_models

LOG_FLOOR = 1e-6
PER_DECADE = 10
# The first fine band 0.01 wide, the run's band 1.
FIRST_LINEAR = 1 + 4 * PER_DECADE
FINE_BANDS = FIRST_LINEAR + folds.BANDS - 1
SUMS = ["rows", "ones", "sum_p", "sum_p2", "sum_p_ones"]
# The full models' inputs are standardised again with means and deviations that DuckDB sums in
# parallel, so their last bits can differ from the run's, and a cell lying on a band's edge can
# change band. At most this share of an entry's rows may do so.
MAX_MOVED = 1e-6


def fine_band(p) -> np.ndarray:
    """Each probability's fine band. A probability in the run's band b >= 1 is in fine band
    FIRST_LINEAR - 1 + b, computed as folds.tally computes b, so the two always agree."""
    p = np.asarray(p, dtype=np.float64)
    coarse = np.minimum((p * folds.BANDS).astype(np.int64), folds.BANDS - 1)
    low = np.zeros(p.shape, dtype=np.int64)
    up = p >= LOG_FLOOR
    low[up] = 1 + np.floor(PER_DECADE * np.log10(p[up] / LOG_FLOOR)).astype(np.int64)
    low = np.minimum(low, FIRST_LINEAR - 1)
    return np.where(coarse >= 1, FIRST_LINEAR - 1 + coarse, low)


def coarse_of(fine) -> np.ndarray:
    """The run's band of each fine band."""
    fine = np.asarray(fine)
    return np.where(fine >= FIRST_LINEAR, fine - (FIRST_LINEAR - 1), 0)


def fine_tally(p, rows, ones) -> dict[str, np.ndarray]:
    """Per fine band: rows, ones, and the sums of p, of p squared and of p over the ones.

    p, rows and ones are arrays of the same length, as for folds.tally: a probability, the rows
    that carry it and how many of them hold the entry.
    """
    p = np.asarray(p, dtype=np.float64)
    rows = np.asarray(rows, dtype=np.float64)
    ones = np.asarray(ones, dtype=np.float64)
    band = fine_band(p)

    def add(weights) -> np.ndarray:
        return np.bincount(band, weights=weights, minlength=FINE_BANDS)

    return {
        "rows": np.rint(add(rows)).astype(np.int64),
        "ones": np.rint(add(ones)).astype(np.int64),
        "sum_p": add(p * rows),
        "sum_p2": add(p * p * rows),
        "sum_p_ones": add(p * ones),
    }


def moved(entry, t: dict, run_rows: np.ndarray, run_ones: np.ndarray) -> int:
    """The rows in another 0.01 band than in the run. Stops unless the entry's rows and ones are
    the run's, and unless at most MAX_MOVED of its rows changed band."""
    coarse = coarse_of(np.arange(FINE_BANDS))
    rows = np.bincount(coarse, weights=t["rows"], minlength=folds.BANDS)
    ones = np.bincount(coarse, weights=t["ones"], minlength=folds.BANDS)
    if rows.sum() != run_rows.sum() or ones.sum() != run_ones.sum():
        raise SystemExit(f"entry {entry}: the rows or ones scored are not the run's")
    out = int(np.abs(rows - run_rows).sum() + np.abs(ones - run_ones).sum()) // 2
    if out > MAX_MOVED * run_rows.sum():
        raise SystemExit(f"entry {entry}: {out:,} rows changed band since the run")
    return out


def run_bands(path, entry_col="entry") -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """The run's rows and ones per 0.01 band of every entry in a bands file."""
    out = {}
    for e, g in pd.read_csv(path).groupby(entry_col):
        rows = np.zeros(folds.BANDS, dtype=np.int64)
        ones = np.zeros(folds.BANDS, dtype=np.int64)
        rows[g["band"].to_numpy()] = g["rows"].to_numpy()
        ones[g["band"].to_numpy()] = g["ones"].to_numpy()
        out[int(e)] = (rows, ones)
    return out


def fine_rows(kind: str, test_year: int, entry: int, t: dict) -> list[list]:
    return [
        [kind, test_year, entry, b, *(t[k][b].item() for k in SUMS)]
        for b in np.flatnonzero(t["rows"])
    ]


def write(path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="") as f:
        out = csv.writer(f, lineterminator="\n")
        out.writerow(header)
        out.writerows(rows)


def small_model(weights: pd.Series) -> LogisticRegression:
    """A small model rebuilt from its saved weights, predicting as the fitted one did."""
    model = LogisticRegression()
    model.classes_ = np.array([False, True])
    model.coef_ = weights[small_models.SMALL_WEIGHTS].to_numpy(dtype=np.float64)[None, :]
    model.intercept_ = np.array([float(weights["intercept"])])
    model.n_features_in_ = folds.SMALL_INPUTS
    return model


def small(con, test_year: int, shuffled: bool, encoding: str = "pairs") -> None:
    """Score again every small and base-rate entry of a fold, and write every entry's training
    rows and ones, from the same counts the fit read (small_models.fit_fold)."""
    started = time.perf_counter()
    kind = small_models.kind(shuffled)
    stem = folds.TRAIN_DIRS[encoding] / f"small_{kind}_{test_year}"
    tiers = pd.read_csv(f"{stem}_scores.csv").set_index("entry")["tier"]
    weights = pd.read_csv(f"{stem}_coefs.csv").set_index("entry")
    bands = run_bands(f"{stem}_bands.csv")
    train = small_models.cells(con, folds.training_years(test_year), shuffled)
    test = small_models.cells(con, [test_year], False)
    at_train, at_test = small_models.by_entry(train), small_models.by_entry(test)

    fine, reference, total_moved = [], [], 0
    for e, tier in tiers.items():
        s = at_train.get(e, slice(0, 0))
        n, y = train["n"][s], train["y"][s]
        train_rows, train_ones = int(n.sum()), int(n[y].sum())
        reference.append([kind, test_year, e, tier, train_rows, train_ones])
        if tier == "full":
            continue
        st = at_test.get(e, slice(0, 0))
        tu, tg, tdays, ty, tn = (test[k][st] for k in ("u", "g", "days_between", "y", "n"))
        if tier == "small":
            p = small_model(weights.loc[e]).predict_proba(small_models.small_inputs(tu, tg, tdays))
            p = p[:, 1]
        else:
            p = np.full(len(tn), train_ones / train_rows if train_ones else 0.0)
        t = fine_tally(p, tn, np.where(ty, tn, 0))
        empty = np.zeros(folds.BANDS, dtype=np.int64)
        total_moved += moved(e, t, *bands.get(e, (empty, empty)))
        fine += fine_rows(kind, test_year, e, t)

    write(f"{stem}_fine.csv", ["kind", "test_year", "entry", "fine_band", *SUMS], fine)
    write(
        f"{stem}_reference.csv",
        ["kind", "test_year", "entry", "tier", "train_rows", "train_ones"],
        reference,
    )
    print(
        f"small {kind} {test_year}, {encoding}: {len(reference):,} entries, "
        f"{total_moved:,} rows in another band than the run's, "
        f"{time.perf_counter() - started:.0f} s",
        flush=True,
    )


def full(test_year: int, encoding: str = "pairs", memory: str = "3GB") -> None:
    """Score again every full entry of a fold, plain and shuffled, on one test matrix: the test
    year's inputs are the same for both kinds, only the training labels were shuffled."""
    started = time.perf_counter()
    out_dir = folds.TRAIN_DIRS[encoding]
    con = small_models.connect(memory_limit=memory)
    d = small_models.fold_inputs(con, test_year, encoding=encoding)
    cols = full_models.prepare(con, test_year, encoding)
    if cols["d"] != d:
        raise SystemExit(f"the matrix has {cols['d']} columns, the fold {d} inputs")
    entry_classes: dict[int, list[int]] = {}
    for e, c in con.execute("SELECT entry, test_class_id FROM entry_classes").fetchall():
        entry_classes.setdefault(e, []).append(c)
    x, classes, label_rows, label_entries = full_models.design(con, [test_year], False, cols)
    con.close()
    full_models.say(started, f"{encoding} {test_year}: test matrix, {x.shape[0]:,} rows")

    for kind in ("model", "shuffled"):
        stem = out_dir / f"full_{kind}_{test_year}"
        f = np.load(f"{stem}_coefs.npz", allow_pickle=False)
        pairs = list(zip(f["pair_makes"].tolist(), f["pair_models"].tolist(), strict=True))
        if (
            int(f["d"]) != d
            or int(f["first_pair"]) != cols["first_pair"]
            or int(f["first_number"]) != cols["first_number"]
            or pairs != [tuple(p) for p in cols["pairs"]]
        ):
            raise SystemExit(f"{stem}_coefs.npz: the saved weights do not line up with the inputs")
        bands = run_bands(f"{stem}_bands.csv")
        if set(bands) - set(f["entries"].tolist()):
            raise SystemExit(f"{stem}: an entry of the run's bands has no saved weights")
        fine, total_moved = [], 0
        for e, w, b in zip(f["entries"].tolist(), f["coef"], f["intercept"].tolist(), strict=True):
            # As full_models.fit_one scores: 32-bit inputs and weights, the logistic in 64 bits.
            mask = np.isin(classes, entry_classes[e])
            z = x @ w.astype(x.dtype) + x.dtype.type(b)
            p = 1.0 / (1.0 + np.exp(-z[mask].astype(np.float64)))
            y = full_models.labels(label_rows, label_entries, x.shape[0], e)[mask]
            t = fine_tally(p, np.ones(len(p), dtype=np.int64), y)
            empty = np.zeros(folds.BANDS, dtype=np.int64)
            total_moved += moved(e, t, *bands.get(e, (empty, empty)))
            fine += fine_rows(kind, test_year, e, t)
        write(f"{stem}_fine.csv", ["kind", "test_year", "entry", "fine_band", *SUMS], fine)
        full_models.say(
            started,
            f"full {kind} {test_year}: {len(f['entries'])} entries, "
            f"{total_moved:,} rows in another band than the run's",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a fold again for the Brier score.")
    parser.add_argument("tier", choices=["small", "full"])
    parser.add_argument("test_year", type=int)
    parser.add_argument("--shuffled", action="store_true", help="small: the shuffled-label check")
    parser.add_argument(
        "--encoding", choices=folds.ENCODINGS, default="pairs", help="which model to score"
    )
    parser.add_argument("--memory", default="3GB", help="full: DuckDB's memory limit")
    a = parser.parse_args()
    if a.tier == "small":
        small(small_models.connect(), a.test_year, a.shuffled, a.encoding)
    else:
        full(a.test_year, a.encoding, a.memory)


if __name__ == "__main__":
    main()
