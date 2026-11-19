"""The small and base-rate models, fitted on counts on our computer (DATA.md).

A small model's inputs come from three facts about a row: u, whether the previous slot recorded
the entry; g, whether it recorded any entry of the entry's group; and the days between the two
slots' first tests, in bands, each kind of vehicle with a curve of its own across them
(folds.py). Rows with the same three facts and the same label add the same term to the loss, so
the model is fitted on the count of rows of each combination, weighted by that count, which
gives the same weights as every row. The counts of a test year score it in the same way, since
the prediction depends on the three facts alone.

Run from the repository's root, one piece at a time, each writing its own files so that a piece
stopped halfway is simply run again:

    python src/motrisk/small_models.py count 2019          # the counts of one target year
    python src/motrisk/small_models.py count 2019 --shuffled
    python src/motrisk/small_models.py fit 2020            # the fold of one test year
    python src/motrisk/small_models.py fit 2020 --shuffled
    python src/motrisk/small_models.py fit 2020 --encoding pooled    # the second model's tiers
    python src/motrisk/small_models.py check-counts        # every row against counts, fold 2020

Counts go to data/counts/<kind>/<year>.parquet, the fits' results to data/processed/train/, or
data/processed/train_pooled/ for the second model. The small models themselves do not read make
and model; the encoding changes only d, and so which entries get the full model instead.
"""

import argparse
import csv
import tempfile
import time
from pathlib import Path

import duckdb
import numpy as np
from sklearn.linear_model import LogisticRegression

from motrisk import baselines, folds

COUNTS = Path("data/counts")
BASELINE_COUNTS = Path("data/processed/baseline_counts.csv")


def kind(shuffled: bool) -> str:
    return "shuffled" if shuffled else "model"


def connect(memory_limit: str = "4GB") -> duckdb.DuckDBPyConnection:
    """A connection with entry_classes and entry_groups, spilling to a temporary folder."""
    con = baselines.connect(memory_limit=memory_limit)
    con.execute(f"SET temp_directory = '{tempfile.mkdtemp(prefix='motrisk_')}'")
    folds.load_entry_groups(con)
    return con


def count_year(con, year: int, shuffled: bool, rows: Path | None = None) -> Path:
    """Write the counts of one target year: rows per entry, u, g, days and label.

    Only rows of the entry's classes count. Cells with g = 1 come from the groups of each row's
    previous slot; the ones with g = 0 from its label; the rows with g = 0 and no one are what is
    left of the entry's rows. Returns the file written.
    """
    rows = rows or folds.ROWS
    con.execute(f"CREATE OR REPLACE TEMP TABLE r AS {folds.rows_sql(year, shuffled, rows)}")
    con.execute(
        """CREATE OR REPLACE TEMP TABLE g1 AS
           SELECT eg.entry, list_contains(r.previous_entries, eg.entry) AS u,
                  r.days_between, list_contains(r.label_entries, eg.entry) AS y, count(*) AS n
           FROM (SELECT test_class_id, days_between, previous_entries, label_entries,
                        unnest(previous_group_ids) AS group_id FROM r) AS r
           JOIN entry_groups AS eg USING (group_id)
           JOIN entry_classes AS ec
             ON ec.entry = eg.entry AND ec.test_class_id = r.test_class_id
           GROUP BY ALL"""
    )
    con.execute(
        """CREATE OR REPLACE TEMP TABLE g0_ones AS
           SELECT u.entry, u.days_between, count(*) AS n
           FROM (SELECT test_class_id, days_between, previous_group_ids,
                        unnest(label_entries) AS entry FROM r) AS u
           JOIN entry_groups AS eg USING (entry)
           JOIN entry_classes AS ec
             ON ec.entry = u.entry AND ec.test_class_id = u.test_class_id
           WHERE NOT list_contains(u.previous_group_ids, eg.group_id)
           GROUP BY ALL"""
    )
    con.execute(
        """CREATE OR REPLACE TEMP TABLE entry_rows AS
           SELECT ec.entry, t.days_between, sum(t.n) AS n
           FROM (SELECT test_class_id, days_between, count(*) AS n FROM r GROUP BY ALL) AS t
           JOIN entry_classes AS ec USING (test_class_id)
           GROUP BY ALL"""
    )
    con.execute(
        """CREATE OR REPLACE TEMP TABLE g0_none AS
           SELECT a.entry, a.days_between,
                  a.n - coalesce(b.n, 0) - coalesce(c.n, 0) AS n
           FROM entry_rows AS a
           LEFT JOIN (SELECT entry, days_between, sum(n) AS n FROM g1 GROUP BY ALL) AS b
             USING (entry, days_between)
           LEFT JOIN g0_ones AS c USING (entry, days_between)"""
    )
    (negative,) = con.execute("SELECT count(*) FROM g0_none WHERE n < 0").fetchall()[0]
    if negative:
        raise SystemExit(f"{year}: {negative} cells with fewer rows than their parts")
    out = COUNTS / kind(shuffled) / f"{year}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"""COPY (
                SELECT entry, u, true AS g, days_between, y, n FROM g1
                UNION ALL
                SELECT entry, false, false, days_between, true, n FROM g0_ones
                UNION ALL
                SELECT entry, false, false, days_between, false, n FROM g0_none WHERE n > 0
                ORDER BY entry, u, g, days_between, y
            ) TO '{out}' (FORMAT parquet)"""
    )
    return out


def fold_inputs(con, test_year: int, rows: Path | None = None, encoding: str = "pairs") -> int:
    """d, the number of inputs of the fold's full model: one per entry, group, entry and band of
    the gap, class and fuel found in its training rows, one per make-and-model column of the
    encoding (folds.pair_columns), the three numbers, and one per band of the gap."""
    rows = rows or folds.ROWS
    files = [str(rows / f"{y}.parquet") for y in folds.training_years(test_year)]
    (classes, fuels) = con.execute(
        f"""SELECT count(DISTINCT test_class_id), count(DISTINCT fuel_type)
            FROM read_parquet({files})"""
    ).fetchall()[0]
    folds.pair_columns(con, test_year, encoding, rows)
    pairs = folds.n_pair_columns(con)
    (entries,) = con.execute("SELECT count(DISTINCT entry) FROM entry_classes").fetchall()[0]
    (groups,) = con.execute("SELECT count(DISTINCT group_id) FROM entry_groups").fetchall()[0]
    bands = len(folds.BANDS_KEPT)
    return entries + groups + entries * bands + classes + fuels + pairs + len(folds.NUMBERS) + bands


def cells(con, years: list[int], shuffled: bool):
    """The counts of these years added up: entry, u, g, days, y and n, as numpy arrays."""
    files = [str(COUNTS / kind(shuffled) / f"{y}.parquet") for y in years]
    t = con.execute(
        f"""SELECT CAST(entry AS SMALLINT) AS entry, u, g,
                   CAST(days_between AS SMALLINT) AS days_between, y, CAST(sum(n) AS BIGINT) AS n
            FROM read_parquet({files})
            GROUP BY entry, u, g, days_between, y ORDER BY entry"""
    ).fetchnumpy()
    return {k: np.asarray(v) for k, v in t.items()}


def by_entry(c: dict) -> dict[int, slice]:
    """Where each entry's cells sit in arrays sorted by entry."""
    entries, starts = np.unique(c["entry"], return_index=True)
    ends = list(starts[1:]) + [len(c["entry"])]
    return {int(e): slice(s, t) for e, s, t in zip(entries, starts, ends, strict=True)}


SMALL_WEIGHTS = [
    "w_u",
    "w_g",
    *(f"w_band{b}" for b in folds.BANDS_KEPT),
    *(f"w_u_band{b}" for b in folds.BANDS_KEPT),
    *(f"w_g_band{b}" for b in folds.BANDS_KEPT),
]


def small_inputs(u, g, days) -> np.ndarray:
    """The small model's 14 inputs: u, g, the bands of the gap, and the bands crossed with u and
    with g where u is 0, so that each of the three kinds of vehicle has its own curve."""
    u = np.asarray(u, dtype=np.float64)
    g = np.asarray(g, dtype=np.float64)
    band = folds.gap_band(days)
    b = np.column_stack([band == k for k in folds.BANDS_KEPT]).astype(np.float64)
    return np.column_stack([u, g, b, b * u[:, None], b * (g * (1 - u))[:, None]])


def fit_counts(u, g, days, y, n, tol: float = folds.SMALL_TOL) -> LogisticRegression:
    """The small model fitted on counts, weighted by them, run to a tight tolerance."""
    return LogisticRegression(C=1.0, tol=tol, max_iter=folds.MAX_ITER).fit(
        small_inputs(u, g, days), np.asarray(y).astype(int), sample_weight=n
    )


def expected_ones(test_year: int) -> dict[int, int]:
    """Each entry's true positives plus false negatives in the baselines' counts of a test year."""
    ones: dict[int, int] = {}
    with open(BASELINE_COUNTS, newline="") as f:
        for r in csv.DictReader(f):
            if r["baseline"] == "repeat" and int(r["test_year"]) == test_year:
                ones[int(r["entry"])] = int(r["tp"]) + int(r["fn"])
    return ones


def fit_fold(con, test_year: int, shuffled: bool, encoding: str = "pairs") -> None:
    """Fit and score every small and base-rate entry of one fold, and record every entry's tier.

    Checks, before writing: each entry's ones in the training years are those counted from the
    rows by baselines.label_ones, which a shuffle must keep; in the test year, every entry's true
    positives plus false negatives are the baselines'; the bands agree with the counts at p_crit.
    """
    started = time.perf_counter()
    years = folds.training_years(test_year)
    d = fold_inputs(con, test_year, encoding=encoding)
    train = cells(con, years, shuffled)
    test = cells(con, [test_year], False)
    at_train, at_test = by_entry(train), by_entry(test)

    ones_from_rows: dict[int, int] = {}
    for y in years:
        for e, n in baselines.label_ones(con, folds.ROWS / f"{y}.parquet").items():
            ones_from_rows[e] = ones_from_rows.get(e, 0) + n

    expected = expected_ones(test_year)
    scores, bands, coefs = [], [], []
    entries = [e for (e,) in con.execute("SELECT DISTINCT entry FROM entry_classes").fetchall()]
    for e in sorted(entries):
        s = at_train.get(e, slice(0, 0))
        y, n = train["y"][s], train["n"][s]
        ones = int(n[y].sum())
        if ones != ones_from_rows.get(e, 0):
            raise SystemExit(
                f"{test_year} entry {e}: {ones} ones counted, rows hold {ones_from_rows.get(e, 0)}"
            )
        t = folds.tier(ones, d)
        if t == "full":
            scores.append([kind(shuffled), test_year, e, t, "", "", "", ""])
            continue
        st = at_test.get(e, slice(0, 0))
        tu, tg, tdays, ty, tn = (test[k][st] for k in ("u", "g", "days_between", "y", "n"))
        iterations = ""
        if t == "small":
            model = fit_counts(train["u"][s], train["g"][s], train["days_between"][s], y, n)
            p = model.predict_proba(small_inputs(tu, tg, tdays))[:, 1]
            iterations = int(model.n_iter_[0])
            if iterations >= folds.MAX_ITER:
                raise SystemExit(f"{test_year} entry {e}: the fit did not converge")
            coefs.append(
                [
                    kind(shuffled),
                    test_year,
                    e,
                    float(model.intercept_[0]),
                    *map(float, model.coef_[0]),
                    iterations,
                ]
            )
        else:
            p = np.full(len(tn), ones / n.sum() if ones else 0.0)
        tp, fp, fn, band_rows, band_ones = folds.tally(p, tn, np.where(ty, tn, 0))
        folds.check_tally(e, tp, fp, fn, band_rows, band_ones, int(tn.sum()), int(tn[ty].sum()))
        if tp + fn != expected.get(e, 0):
            raise SystemExit(
                f"{test_year} entry {e}: {tp + fn} ones scored, the baselines {expected.get(e, 0)}"
            )
        scores.append([kind(shuffled), test_year, e, t, tp, fp, fn, iterations])
        bands += [
            [kind(shuffled), test_year, e, b, int(band_rows[b]), int(band_ones[b])]
            for b in np.flatnonzero(band_rows)
        ]

    out_dir = folds.TRAIN_DIRS[encoding]
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"small_{kind(shuffled)}_{test_year}"
    for suffix, header, rows in (
        ("scores", ["kind", "test_year", "entry", "tier", "tp", "fp", "fn", "n_iter"], scores),
        ("bands", ["kind", "test_year", "entry", "band", "rows", "ones"], bands),
        (
            "coefs",
            ["kind", "test_year", "entry", "intercept", *SMALL_WEIGHTS, "n_iter"],
            coefs,
        ),
    ):
        with open(f"{stem}_{suffix}.csv", "w", newline="") as f:
            out = csv.writer(f, lineterminator="\n")
            out.writerow(header)
            out.writerows(rows)
    tiers = {t: sum(1 for r in scores if r[3] == t) for t in ("full", "small", "base_rate", "none")}
    print(
        f"{kind(shuffled)} {test_year}: d {d:,}, tiers {tiers}, "
        f"{time.perf_counter() - started:.0f} s",
        flush=True,
    )


def shuffle_check(con, year: int, rows: Path | None = None) -> tuple[float, float]:
    """How often the shuffle leaves a row its own label, against how often two rows drawn at
    random within a class share one, which is what a shuffle that breaks the pairing gives.

    Returns both shares; the count stops if the first is not close to the second.
    """
    rows = rows or folds.ROWS
    source = f"read_parquet('{rows / f'{year}.parquet'}')"
    (same,) = con.execute(
        f"""SELECT avg(CASE WHEN s.label_entries = o.label_entries THEN 1.0 ELSE 0 END)
            FROM ({folds.rows_sql(year, True, rows)}) AS s
            JOIN {source} AS o USING (vehicle_id, target_start)"""
    ).fetchall()[0]
    (chance,) = con.execute(
        f"""SELECT sum(n * n * 1.0 / k) / sum(n)
            FROM (SELECT test_class_id, label_entries, count(*) AS n FROM {source} GROUP BY ALL)
            JOIN (SELECT test_class_id, count(*) AS k FROM {source} GROUP BY ALL)
              USING (test_class_id)"""
    ).fetchall()[0]
    return float(same), float(chance)


def every_row(con, entry: int, year: int, rows: Path | None = None):
    """One entry's small-model inputs and label on every row of its classes in one target year."""
    rows = rows or folds.ROWS
    t = con.execute(
        f"""SELECT list_contains(r.previous_entries, ?) AS u,
                   list_contains(r.previous_group_ids, (SELECT group_id FROM entry_groups
                                                        WHERE entry = ?)) AS g,
                   CAST(round(r.weeks_between * 7) AS INTEGER) AS days_between,
                   list_contains(r.label_entries, ?) AS y
            FROM read_parquet('{rows / f"{year}.parquet"}') AS r
            WHERE r.test_class_id IN (SELECT test_class_id FROM entry_classes WHERE entry = ?)""",
        [entry, entry, entry, entry],
    ).fetchnumpy()
    return {k: np.asarray(v) for k, v in t.items()}


def check_counts(con, test_year: int = 2020) -> None:
    """Test 5: on the first fold, the small model fitted on counts and on every row agree.

    Three of the fold's small-model entries, chosen to cover the cases: the one whose rows most
    often have g = 1 without u, one listed only for motorcycles, and the one with the fewest
    ones. Both fits run the solver to the same tight tolerance, so only the counting can differ.
    Stops unless the weights agree to six decimals.
    """
    (year,) = folds.training_years(test_year)
    d = fold_inputs(con, test_year)
    c = cells(con, [year], False)
    at = by_entry(c)
    small = {}
    for e, s in at.items():
        ones = int(c["n"][s][c["y"][s]].sum())
        if folds.tier(ones, d) == "small":
            n = c["n"][s]
            g_only = int(n[c["g"][s] & ~c["u"][s]].sum())
            small[e] = (ones, g_only / n.sum())
    motorcycle = {
        e
        for (e,) in con.execute(
            """SELECT entry FROM entry_classes
               GROUP BY entry HAVING list_sort(list(test_class_id)) = [1, 2]"""
        ).fetchall()
    }
    chosen = {
        "most often g without u": max(small, key=lambda e: small[e][1]),
        "listed only for motorcycles": max(
            (e for e in small if e in motorcycle), key=lambda e: small[e][0]
        ),
        "fewest ones": min(small, key=lambda e: small[e][0]),
    }
    for why, e in chosen.items():
        r = every_row(con, e, year)
        a = fit_counts(r["u"], r["g"], r["days_between"], r["y"], np.ones(len(r["y"])))
        s = at[e]
        b = fit_counts(c["u"][s], c["g"][s], c["days_between"][s], c["y"][s], c["n"][s])
        wa = np.r_[a.intercept_, a.coef_[0]]
        wb = np.r_[b.intercept_, b.coef_[0]]
        print(f"entry {e} ({why}), {len(r['y']):,} rows, {small[e][0]:,} ones")
        print(f"  every row: {np.round(wa, 6)}")
        print(f"  counts:    {np.round(wb, 6)}")
        if np.abs(wa - wb).max() >= 1e-6:
            raise SystemExit(f"entry {e}: the weights differ by {np.abs(wa - wb).max():.2e}")
    print("the weights agree to six decimals")


def main() -> None:
    parser = argparse.ArgumentParser(description="The small and base-rate models, on counts.")
    parser.add_argument("step", choices=["count", "fit", "check-counts"])
    parser.add_argument(
        "year", type=int, nargs="?", help="target year to count, or test year to fit"
    )
    parser.add_argument("--shuffled", action="store_true", help="the shuffled-label check")
    parser.add_argument(
        "--encoding", choices=folds.ENCODINGS, default="pairs", help="make and model's columns"
    )
    a = parser.parse_args()
    con = connect()
    started = time.perf_counter()
    if a.step == "count":
        out = count_year(con, a.year, a.shuffled)
        (cells_written,) = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchall()[0]
        took = time.perf_counter() - started
        print(f"{kind(a.shuffled)} {a.year}: {cells_written:,} cells, {took:.0f} s")
        if a.shuffled:
            same, chance = shuffle_check(con, a.year)
            print(
                f"  rows left their own label: {same:.4f}; by chance within a class: {chance:.4f}"
            )
            if same > chance + 0.01:
                raise SystemExit("the shuffle does not break the pairing")
    elif a.step == "fit":
        fit_fold(con, a.year, a.shuffled, a.encoding)
    else:
        check_counts(con)


if __name__ == "__main__":
    main()
