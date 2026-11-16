"""How the gap between two slots bears on a problem, by kind of vehicle, and what each form gives.

Over the training rows of the fold of 2025, target years 2019 to 2024, this prints: the share of
rows in each band of the gap; the share of rows holding an entry, pooled over every entry, in each
band, for vehicles whose previous slot recorded the entry, recorded only something of its group,
or neither; and, for entries 2546 and 4810, the share observed among vehicles that had the entry
before against what four forms of the gap predict, each fitted on the entry's counts to a tight
tolerance, and the last also to scikit-learn's default one. Reads the counts small_models.py
writes to data/counts/ and the training table in data/training_rows/. Run from the repository's
root:

    python evidence/18_gap_by_kind.py
"""

import numpy as np
from sklearn.linear_model import LogisticRegression

from motrisk import folds, small_models

BANDS = ["under 300 days", "300 to 430", "431 to 730", "731 to 1,095", "over 1,095"]
TRAINING = folds.training_years(2025)


def main() -> None:
    con = small_models.connect()
    files = [str(folds.ROWS / f"{y}.parquet") for y in TRAINING]
    days = con.execute(
        f"SELECT CAST(round(weeks_between * 7) AS INTEGER) AS d FROM read_parquet({files})"
    ).fetchnumpy()["d"]
    share = np.bincount(folds.gap_band(days), minlength=5) / len(days)
    print(f"training rows of the fold of 2025: {len(days):,}")
    for name, s in zip(BANDS, share, strict=True):
        print(f"  {name:15s} {100 * s:6.2f}%")

    c = small_models.cells(con, TRAINING, False)
    band = folds.gap_band(c["days_between"])
    kinds = {
        "the entry before": c["u"],
        "its group only": c["g"] & ~c["u"],
        "neither": ~c["g"],
    }
    print("share of rows holding the entry, pooled over every entry, by band:")
    for name, mask in kinds.items():
        shares = [
            c["n"][mask & (band == b) & c["y"]].sum() / c["n"][mask & (band == b)].sum()
            for b in range(5)
        ]
        print(f"  {name:17s}", "  ".join(f"{100 * s:7.3f}%" for s in shares))

    at = small_models.by_entry(c)
    for e in (2546, 4810):
        s = at[e]
        u, g, d, y, n = (c[k][s] for k in ("u", "g", "days_between", "y", "n"))
        b = folds.gap_band(d)
        b4 = np.column_stack([b == k for k in folds.BANDS_KEPT]).astype(float)
        z = (d - days.mean()) / days.std()
        zc = (np.minimum(d, 730) - days.mean()) / days.std()
        uf, gf = u.astype(float), g.astype(float)
        forms = {
            "straight line": np.column_stack([uf, gf, z]),
            "straight line capped at 2 years": np.column_stack([uf, gf, zc]),
            "bands, one curve for all": np.column_stack([uf, gf, b4]),
            "bands, a curve per kind": small_models.small_inputs(u, g, d),
        }
        print(f"entry {e}, vehicles that had it before, by band:")
        observed = [n[u & (b == k) & y].sum() / n[u & (b == k)].sum() for k in range(5)]
        print(f"  {'observed':40s}", "  ".join(f"{100 * v:5.1f}%" for v in observed))
        fits = [(name, x, folds.SMALL_TOL) for name, x in forms.items()]
        fits.append(
            ("bands, a curve per kind, default tolerance", forms["bands, a curve per kind"], 1e-4)
        )
        for name, x, tol in fits:
            m = LogisticRegression(C=1.0, tol=tol, max_iter=folds.MAX_ITER)
            p = m.fit(x, y.astype(int), sample_weight=n).predict_proba(x)[:, 1]
            pred = [(p * n)[u & (b == k)].sum() / n[u & (b == k)].sum() for k in range(5)]
            print(f"  {name:40s}", "  ".join(f"{100 * v:5.1f}%" for v in pred))


if __name__ == "__main__":
    main()
