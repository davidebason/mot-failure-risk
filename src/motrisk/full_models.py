"""The full models, one logistic regression per entry with every input, on the virtual machine.

Run from the repository's root, for the fold of one test year:

    python src/motrisk/full_models.py 2025                     # every full entry of the fold
    python src/motrisk/full_models.py 2025 --shuffled          # the shuffled-label check
    python src/motrisk/full_models.py 2025 --entries 1 --workers 1    # measure one fit

The inputs of a fold (DATA.md, "The models"): one column per entry of the previous slot, per group,
per entry and band of the gap, per class, per fuel and per make-and-model pair found in the fold's
training rows, then mileage, age and engine size, each standardised with the mean and deviation of
the fold's training rows, and one column per band of the gap. About a year is the reference band,
with no column. A pair, fuel or class not found in the training rows has no column, so a test row
carrying one has none set. The columns are held as a sparse matrix of 32-bit floats, built in
place year by year, since the six-year fold sets about 1.6 billion values.

An entry's model is trained on the rows of its classes, the other rows given a weight of 0, which
leaves the fit as if they were not there, without copying the matrix. The entries are fitted in
parallel by processes forked from the one that built the matrices, so they share them. Each
process scores its entry on the test year with folds.tally; the checks are those of the small
models: ones in the training years as counted from the rows, true positives plus false negatives
as the baselines', the bands agreeing with the counts at tau.
"""

import argparse
import csv
import multiprocessing
import resource
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from sklearn.linear_model import LogisticRegression

from motrisk import baselines, folds, small_models

OUT = Path("data/processed/train")
N_ENTRIES = 4821

# Set in the parent before the workers are forked, and only read by them.
SHARED: dict = {}


def peak_gb() -> float:
    """The largest resident memory of this process and of its finished children, in GB."""
    own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return max(own, children) / 1e6


def say(started: float, message: str) -> None:
    print(
        f"[{time.perf_counter() - started:7.0f} s, peak {peak_gb():5.1f} GB] {message}", flush=True
    )


def prepare(con, test_year: int) -> dict:
    """The fold's columns, in this order: entries, groups, entries by band, classes, fuels, pairs,
    the three numbers, the bands; the maps to them, and the numbers' scaling."""
    years = folds.training_years(test_year)
    files = [str(folds.ROWS / f"{y}.parquet") for y in years]
    groups = [
        g
        for (g,) in con.execute("SELECT DISTINCT group_id FROM entry_groups ORDER BY 1").fetchall()
    ]
    entry_band = N_ENTRIES + len(groups)
    base = entry_band + N_ENTRIES * len(folds.BANDS_KEPT)
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE class_col AS
            SELECT test_class_id, {base} + row_number() OVER (ORDER BY test_class_id) - 1 AS col
            FROM (SELECT DISTINCT test_class_id FROM read_parquet({files}))"""
    )
    (n_classes,) = con.execute("SELECT count(*) FROM class_col").fetchall()[0]
    base += n_classes
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE fuel_col AS
            SELECT fuel_type, {base} + row_number() OVER (ORDER BY fuel_type) - 1 AS col
            FROM (SELECT DISTINCT fuel_type FROM read_parquet({files}))"""
    )
    (n_fuels,) = con.execute("SELECT count(*) FROM fuel_col").fetchall()[0]
    base += n_fuels
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE pair_col AS
            SELECT make, model, {base} + row_number() OVER (ORDER BY make, model) - 1 AS col
            FROM (SELECT DISTINCT make, model FROM read_parquet({files}))"""
    )
    (n_pairs,) = con.execute("SELECT count(*) FROM pair_col").fetchall()[0]
    base += n_pairs
    numbers = ", ".join(f"avg({c}), stddev_pop({c})" for c in folds.NUMBERS)
    scaling = np.array(
        con.execute(f"SELECT {numbers} FROM read_parquet({files})").fetchall()[0]
    ).reshape(len(folds.NUMBERS), 2)
    group_col = np.full(max(groups) + 1, -1, dtype=np.int32)
    group_col[groups] = N_ENTRIES + np.arange(len(groups), dtype=np.int32)
    first_band = base + len(folds.NUMBERS)
    return {
        "group_col": group_col,
        "entry_band": entry_band,
        "first_number": base,
        "first_band": first_band,
        "d": first_band + len(folds.BANDS_KEPT),
        "scaling": scaling,
    }


# For each band of the gap, its place among the kept bands; -1 for the reference, about a year.
KEPT = np.full(len(folds.BAND_EDGES) + 1, -1, dtype=np.int64)
KEPT[list(folds.BANDS_KEPT)] = np.arange(len(folds.BANDS_KEPT))


def year_arrays(con, year: int, shuffled: bool, cols: dict) -> dict:
    """One target year's rows as numpy arrays: list offsets and values, columns, numbers, labels,
    and each row's band of the gap among the kept bands, -1 for about a year."""
    rel = con.sql(
        f"""SELECT r.test_class_id, c.col AS class_col, f.col AS fuel_col, p.col AS pair_col,
                   r.test_mileage, r.age_years, r.cylinder_capacity, r.days_between,
                   r.previous_entries, r.previous_group_ids, r.label_entries
            FROM ({folds.rows_sql(year, shuffled)}) AS r
            LEFT JOIN class_col AS c USING (test_class_id)
            LEFT JOIN fuel_col AS f USING (fuel_type)
            LEFT JOIN pair_col AS p USING (make, model)"""
    )
    # to_arrow_table() is DuckDB 2.0's name; earlier versions call it arrow().
    t = rel.to_arrow_table() if hasattr(rel, "to_arrow_table") else rel.arrow()
    out = {}
    for name in ("previous_entries", "previous_group_ids", "label_entries"):
        arr = t.column(name).combine_chunks()
        out[name] = (
            np.asarray(arr.offsets, dtype=np.int64),
            np.asarray(arr.values, dtype=np.int32),
        )
    for name in ("test_class_id", "class_col", "fuel_col", "pair_col"):
        out[name] = t.column(name).to_numpy(zero_copy_only=False)
    raw = np.column_stack(
        [t.column(c).to_numpy(zero_copy_only=False).astype(np.float64) for c in folds.NUMBERS]
    )
    out["numbers"] = ((raw - cols["scaling"][:, 0]) / cols["scaling"][:, 1]).astype(np.float32)
    out["band"] = KEPT[folds.gap_band(t.column("days_between").to_numpy(zero_copy_only=False))]
    return out


def within(offsets: np.ndarray) -> np.ndarray:
    """For every value of a list column, its place within its own row's list."""
    lengths = np.diff(offsets)
    return np.arange(offsets[-1] - offsets[0]) - np.repeat(offsets[:-1] - offsets[0], lengths)


def sizes(con, year: int) -> tuple[int, int]:
    """One target year's rows, and the values its rows set in the matrix."""
    low, high = folds.BAND_EDGES[0], folds.BAND_EDGES[1]
    off = f"CASE WHEN r.days_between >= {low} AND r.days_between < {high} THEN 0 ELSE 1 END"
    rows, previous, groups, crossed, pairs, banded = con.execute(
        f"""SELECT count(*), sum(len(r.previous_entries)), sum(len(r.previous_group_ids)),
                   sum(len(r.previous_entries) * {off}), count(p.col), sum({off})
            FROM ({folds.rows_sql(year, False)}) AS r
            LEFT JOIN pair_col AS p USING (make, model)"""
    ).fetchall()[0]
    fixed = 2 + len(folds.NUMBERS)
    return rows, previous + groups + crossed + pairs + banded + fixed * rows


def design(con, years: list[int], shuffled: bool, cols: dict):
    """The inputs of these years' rows as one CSR matrix, with each row's class and its labels.

    The arrays are allocated once at their final size and filled one year at a time, so that only
    one year's rows are ever held besides the matrix. Offsets and column numbers are 32-bit, which
    holds up to 2,147,483,647 values; SciPy would otherwise widen both to 64-bit. Each row's
    columns are in increasing order. Returns the matrix, the class of each row, and for every
    label value its row and its entry.
    """
    counted = [sizes(con, y) for y in years]
    n = sum(rows for rows, _ in counted)
    nnz = sum(values for _, values in counted)
    if nnz >= 2**31:
        raise SystemExit(f"{nnz:,} values do not fit 32-bit offsets")
    indptr = np.zeros(n + 1, dtype=np.int32)
    data = np.ones(nnz, dtype=np.float32)
    indices = np.empty(nnz, dtype=np.int32)
    classes = np.empty(n, dtype=np.int8)
    label_rows, label_entries = [], []
    n_numbers, n_kept = len(folds.NUMBERS), len(folds.BANDS_KEPT)

    first = 0
    for y in years:
        p = year_arrays(con, y, shuffled, cols)
        m = len(p["test_class_id"])
        for name in ("class_col", "fuel_col"):
            if np.isnan(p[name].astype(np.float64)).any():
                raise SystemExit(f"{y}: a {name[:-4]} not found in the training rows")
        h = ~np.isnan(p["pair_col"].astype(np.float64))
        band = p["band"]
        off = band >= 0
        po, pv = p["previous_entries"]
        go, gv = p["previous_group_ids"]
        lp, lg = np.diff(po), np.diff(go)
        lc = lp * off
        indptr[first + 1 : first + m + 1] = indptr[first] + np.cumsum(
            lp + lg + lc + 2 + h + n_numbers + off
        )
        start = indptr[first : first + m].astype(np.int64)
        place_in_list = within(po)
        indices[np.repeat(start, lp) + place_in_list] = pv
        indices[np.repeat(start + lp, lg) + within(go)] = cols["group_col"][gv]
        # Each entry of the previous slot crossed with the row's band, when it is not about a year.
        crossed = np.repeat(off, lp)
        row_of = np.repeat(np.arange(m), lp)[crossed]
        indices[start[row_of] + lp[row_of] + lg[row_of] + place_in_list[crossed]] = (
            cols["entry_band"] + pv[crossed].astype(np.int64) * n_kept + band[row_of]
        )
        after = start + lp + lg + lc
        indices[after] = p["class_col"].astype(np.int32)
        indices[after + 1] = p["fuel_col"].astype(np.int32)
        indices[after[h] + 2] = p["pair_col"][h].astype(np.int32)
        for k in range(n_numbers):
            place = after + 2 + h + k
            indices[place] = cols["first_number"] + k
            data[place] = p["numbers"][:, k]
        last = (after + 2 + h + n_numbers)[off]
        indices[last] = cols["first_band"] + band[off]
        classes[first : first + m] = p["test_class_id"]
        lo, lv = p["label_entries"]
        label_rows.append(first + np.repeat(np.arange(m, dtype=np.int32), np.diff(lo)))
        label_entries.append(lv.copy())
        first += m
        del p, po, pv, go, gv
    if first != n or indptr[-1] != nnz:
        raise SystemExit("the matrix was not filled as sized")

    x = sp.csr_matrix((data, indices, indptr), shape=(n, cols["d"]), copy=False)
    if x.indices.dtype != np.int32 or x.indptr.dtype != np.int32:
        raise SystemExit("SciPy widened the matrix's offsets")
    return x, classes, np.concatenate(label_rows), np.concatenate(label_entries)


def labels(label_rows, label_entries, n: int, entry: int) -> np.ndarray:
    y = np.zeros(n, dtype=bool)
    y[label_rows[label_entries == entry]] = True
    return y


def fit_one(entry: int):
    """Fit one entry's model on the shared training matrix and score it on the test year."""
    s = SHARED
    started = time.perf_counter()
    listed = s["entry_classes"][entry]
    weight = np.isin(s["train_classes"], listed).astype(np.float32)
    y = labels(s["train_label_rows"], s["train_label_entries"], s["x_train"].shape[0], entry)
    model = LogisticRegression(C=1.0).fit(s["x_train"], y, sample_weight=weight)
    mask = np.isin(s["test_classes"], listed)
    z = s["x_test"] @ model.coef_[0].astype(np.float32) + np.float32(model.intercept_[0])
    p = 1.0 / (1.0 + np.exp(-z[mask].astype(np.float64)))
    y_test = labels(s["test_label_rows"], s["test_label_entries"], s["x_test"].shape[0], entry)[
        mask
    ]
    tp, fp, fn, band_rows, band_ones = folds.tally(p, np.ones(len(p), dtype=np.int64), y_test)
    folds.check_tally(entry, tp, fp, fn, band_rows, band_ones, len(p), int(y_test.sum()))
    return {
        "entry": entry,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "band_rows": band_rows,
        "band_ones": band_ones,
        "n_iter": int(model.n_iter_[0]),
        "coef": model.coef_[0].astype(np.float32),
        "intercept": float(model.intercept_[0]),
        "seconds": time.perf_counter() - started,
    }


def run(
    test_year: int,
    shuffled: bool,
    entries_max: int | None,
    workers: int,
    memory: str,
) -> None:
    started = time.perf_counter()
    kind = small_models.kind(shuffled)
    con = small_models.connect(memory_limit=memory)
    cols = prepare(con, test_year)
    d = small_models.fold_inputs(con, test_year)
    if cols["d"] != d:
        raise SystemExit(f"the matrix has {cols['d']} columns, the fold {d} inputs")
    say(started, f"{kind} {test_year}: d {d:,}")

    years = folds.training_years(test_year)
    ones_from_rows: dict[int, int] = {}
    for y in years:
        for e, k in baselines.label_ones(con, folds.ROWS / f"{y}.parquet").items():
            ones_from_rows[e] = ones_from_rows.get(e, 0) + k
    full = sorted(e for e, k in ones_from_rows.items() if folds.tier(k, d) == "full")
    chosen = full[:entries_max] if entries_max else full
    entry_classes: dict[int, list[int]] = {}
    for e, c in con.execute("SELECT entry, test_class_id FROM entry_classes").fetchall():
        entry_classes.setdefault(e, []).append(c)
    expected = small_models.expected_ones(test_year)
    say(started, f"{len(full)} full entries, fitting {len(chosen)} with {workers} workers")

    x_train, train_classes, train_label_rows, train_label_entries = design(
        con, years, shuffled, cols
    )
    say(started, f"training matrix: {x_train.shape[0]:,} rows, {x_train.nnz:,} values")
    x_test, test_classes, test_label_rows, test_label_entries = design(
        con, [test_year], False, cols
    )
    say(started, f"test matrix: {x_test.shape[0]:,} rows, {x_test.nnz:,} values")
    con.close()

    for e in chosen:
        ones = int(
            np.isin(
                train_classes[train_label_rows[train_label_entries == e]], entry_classes[e]
            ).sum()
        )
        if ones != ones_from_rows[e]:
            raise SystemExit(
                f"entry {e}: {ones} ones in the matrix's labels, {ones_from_rows[e]} in the rows"
            )

    SHARED.update(
        x_train=x_train,
        train_classes=train_classes,
        train_label_rows=train_label_rows,
        train_label_entries=train_label_entries,
        x_test=x_test,
        test_classes=test_classes,
        test_label_rows=test_label_rows,
        test_label_entries=test_label_entries,
        entry_classes=entry_classes,
    )
    results = []
    with multiprocessing.get_context("fork").Pool(workers) as pool:
        for r in pool.imap_unordered(fit_one, chosen):
            scored, should = r["tp"] + r["fn"], expected.get(r["entry"], 0)
            if scored != should:
                raise SystemExit(
                    f"entry {r['entry']}: {scored} ones scored, the baselines {should}"
                )
            results.append(r)
            say(started, f"entry {r['entry']}: {r['n_iter']} iterations, {r['seconds']:.0f} s")

    if entries_max:
        say(started, "measurement only: nothing written")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    stem = OUT / f"full_{kind}_{test_year}"
    results.sort(key=lambda r: r["entry"])
    with open(f"{stem}_scores.csv", "w", newline="") as f:
        out = csv.writer(f, lineterminator="\n")
        out.writerow(["kind", "test_year", "entry", "tier", "tp", "fp", "fn", "n_iter"])
        out.writerows(
            [kind, test_year, r["entry"], "full", r["tp"], r["fp"], r["fn"], r["n_iter"]]
            for r in results
        )
    with open(f"{stem}_bands.csv", "w", newline="") as f:
        out = csv.writer(f, lineterminator="\n")
        out.writerow(["kind", "test_year", "entry", "band", "rows", "ones"])
        for r in results:
            out.writerows(
                [kind, test_year, r["entry"], b, int(r["band_rows"][b]), int(r["band_ones"][b])]
                for b in np.flatnonzero(r["band_rows"])
            )
    np.savez_compressed(
        f"{stem}_coefs.npz",
        entries=np.array([r["entry"] for r in results]),
        coef=np.vstack([r["coef"] for r in results]) if results else np.empty((0, d)),
        intercept=np.array([r["intercept"] for r in results]),
    )
    say(started, f"wrote {stem}_*")


def main() -> None:
    parser = argparse.ArgumentParser(description="The full models of one fold.")
    parser.add_argument("test_year", type=int)
    parser.add_argument("--shuffled", action="store_true", help="the shuffled-label check")
    parser.add_argument("--entries", type=int, help="fit only the first this many full entries")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--memory", default="6GB", help="DuckDB's memory limit")
    a = parser.parse_args()
    run(a.test_year, a.shuffled, a.entries, a.workers, a.memory)


if __name__ == "__main__":
    main()
