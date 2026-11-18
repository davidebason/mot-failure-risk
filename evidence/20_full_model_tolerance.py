"""How far scikit-learn's default tolerance leaves the full models from a tighter fit.

The full models were fitted at scikit-learn's default tolerance, 1e-4, each fold starting from the
previous fold's weights. The folds of 2020 and 2021 had been fitted first at 1e-5, plain and
shuffled, 23 full entries in all, and were kept to measure the gap. For each of those folds this
prints, over its full entries at p_crit = 0.5, the true positives, false positives and false
negatives, precision and recall, and the iterations, at both tolerances. Reads the scores in
data/processed/train/ and data/processed/train_tol1e-5/. Run from the repository's root:

    python evidence/20_full_model_tolerance.py
"""

from pathlib import Path

import pandas as pd

RUNS = {"default, 1e-4": Path("data/processed/train"), "1e-5": Path("data/processed/train_tol1e-5")}


def main() -> None:
    for kind in ("model", "shuffled"):
        for year in (2020, 2021):
            scores = {
                name: pd.read_csv(path / f"full_{kind}_{year}_scores.csv")
                for name, path in RUNS.items()
            }
            entries = [set(s["entry"]) for s in scores.values()]
            if entries[0] != entries[1]:
                raise SystemExit(f"{kind} {year}: the two runs have different full entries")
            print(f"{kind} {year}, {len(entries[0])} full entries:")
            for name, s in scores.items():
                tp, fp, fn = (int(s[k].sum()) for k in ("tp", "fp", "fn"))
                precision = f"{100 * tp / (tp + fp):6.2f}%" if tp + fp else "   -   "
                print(
                    f"  {name:14s} tp {tp:>9,} fp {fp:>9,} fn {fn:>11,}  "
                    f"precision {precision}  recall {100 * tp / (tp + fn):5.2f}%  "
                    f"iterations {int(s['n_iter'].sum()):,}"
                )


if __name__ == "__main__":
    main()
