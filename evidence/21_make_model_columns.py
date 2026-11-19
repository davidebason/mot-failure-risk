"""How many training rows each make and model has, and what pooling the rare ones changes.

The first model gives every make-and-model pair of a fold's training rows a column of its own. The
second pools them (folds.pair_columns): a pair keeps a column of its own with at least
folds.POOL_MIN_ROWS training rows, a make's rarer pairs share one column when they add up to as
many, and every other pair shares one last column. This prints:

- for the fold of 2025, trained on the target years 2019 to 2024: the pairs, the rows each has,
  and the share of the training rows in each kind of column of the second model;
- the first model's make-and-model weights in the fold of 2025 that are under 0.01 in absolute
  value, from its weights in data/processed/train/, which stay on our computer;
- for every fold and both encodings: d, the ones an entry needs for the full model, 10(d + 1),
  the entries that have them, and their share of the ones of the training rows, counted on rows
  of each entry's classes as the models count them.

Reads data/training_rows/. Run from the repository's root:

    python evidence/21_make_model_columns.py
"""

from pathlib import Path

import numpy as np

from motrisk import baselines, folds, small_models

WEIGHTS = Path("data/processed/train/full_model_2025_coefs.npz")


def rows_per_pair(con) -> None:
    files = [str(folds.ROWS / f"{y}.parquet") for y in folds.training_years(2025)]
    m = folds.POOL_MIN_ROWS
    per_pair = f"SELECT make, model, count(*) AS n FROM read_parquet({files}) GROUP BY ALL"
    pairs, rows, median, under_10, under_100, common, common_rows = con.execute(
        f"""WITH p AS ({per_pair})
            SELECT count(*), sum(n), median(n), count(*) FILTER (n < 10),
                   count(*) FILTER (n < 100), count(*) FILTER (n >= {m}),
                   sum(n) FILTER (n >= {m})
            FROM p"""
    ).fetchall()[0]
    print(f"fold of 2025: {rows:,} training rows, {pairs:,} make-and-model pairs")
    print(f"  rows per pair: median {median:g}; {under_10:,} under 10, {under_100:,} under 100")
    print(f"  pairs with at least {m:,} rows: {common:,}, {common_rows / rows:.2%} of the rows")

    folds.pair_columns(con, 2025, "pooled")
    for name, condition in (
        ("own column", f"pair_label_model NOT IN ('{folds.REST}', '{folds.OTHER[1]}')"),
        ("a make's shared column", f"pair_label_model = '{folds.REST}'"),
        ("the last column", f"pair_label_model = '{folds.OTHER[1]}'"),
    ):
        columns, share = con.execute(
            f"""WITH p AS ({per_pair})
                SELECT count(DISTINCT (o.pair_label_make, o.pair_label_model)),
                       sum(p.n) / {rows}
                FROM p JOIN pair_of AS o USING (make, model)
                WHERE {condition}"""
        ).fetchall()[0]
        print(f"  second model, {name}: {columns:,} columns, {share:.2%} of the rows")


def small_weights() -> None:
    f = np.load(WEIGHTS, allow_pickle=False)
    w = f["coef"][:, int(f["first_pair"]) : int(f["first_number"])]
    print(
        f"first model, fold of 2025: {w.shape[1]:,} make-and-model columns in {w.shape[0]} full "
        f"models; {(np.abs(w) < 0.01).mean():.1%} of their weights under 0.01 in absolute value"
    )


def tiers(con) -> None:
    for test_year in folds.TEST_YEARS:
        ones: dict[int, int] = {}
        for y in folds.training_years(test_year):
            for e, k in baselines.label_ones(con, folds.ROWS / f"{y}.parquet").items():
                ones[e] = ones.get(e, 0) + k
        total = sum(ones.values())
        for encoding in folds.ENCODINGS:
            d = small_models.fold_inputs(con, test_year, encoding=encoding)
            full = [k for k in ones.values() if folds.tier(k, d) == "full"]
            print(
                f"fold of {test_year}, {encoding:6s}: d {d:>7,}, full from {10 * (d + 1):>9,} "
                f"ones: {len(full):>3} entries, {sum(full) / total:.1%} of the training ones"
            )


def main() -> None:
    con = small_models.connect()
    rows_per_pair(con)
    small_weights()
    tiers(con)


if __name__ == "__main__":
    main()
