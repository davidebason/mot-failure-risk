"""Why the rarest full models score below the small models: some refitted further, and with a
stronger penalty.

In the second model's fold of 2025, the 86 entries that get a full model there and a small model
in the first score a Brier skill of 0.0196 as full models against 0.0228 as small models. Two
causes are tested on some of them, each fit starting from the weights the run saved, in 64-bit
floats, CHUNK iterations at a time for at most --chunks chunks, the test year scored after each:

- (a) the fits stopped too early. Their fits took a median of 2 iterations: each fold starts from
  the previous fold's weights, and at scikit-learn's default tolerance, in 32-bit floats, a fit
  stops almost at once. Tested at the run's penalty, --penalty 1.
- (b) too many weights for too few cases. Most weights are an entry of the previous slot, alone
  or by band of the gap, and most of those are set on few rows. Tested with the penalty k times
  the run's, --penalty k, that is C = 1/k, which shrinks a weight whose column carries fewer
  than about k expected ones and leaves the columns with many alone.

The figures above, fold by fold, come from the results the runs saved, on our computer;
the tests take three steps, each its own process, so that their memory peaks never add up: in one
process, the 64-bit training matrix and the test matrix exceed the virtual machine's 32 GB.

    python evidence/22_tight_refit.py moved --encoding pooled
    python evidence/22_tight_refit.py build 2025 --encoding pooled
    python evidence/22_tight_refit.py fit 2025 2475 2546 --encoding pooled
    python evidence/22_tight_refit.py fit 2025 2475 2546 --encoding pooled \\
        --penalty 10 100 1000 10000 --chunks 2
    python evidence/22_tight_refit.py score 2025 2475 2546 --encoding pooled

- moved: for each fold, the entries with a full model in the second model and a small model in
  the first, their Brier skill as each, and their full fits' median iterations, with the first
  model's beside them.
- build: both matrices of the fold in 32-bit floats, as the run built them, saved under
  data/measure/tight_<year>/, about 13 GB, with each row's class and labels.
- fit: the training matrix widened to 64-bit floats, 16 GB; for each entry and penalty, the saved
  weights, then CHUNK iterations at a time, the weights saved as w_<entry>_p<penalty>_<iterations>
  and the training objective printed after each.
- score: each set of weights saved so far, on the test year, as the run scored, into
  tight_<year>_fine.csv beside the run's results; the saved weights must give the run's bands.
  Prints each entry's Brier skill as the first model's small model, and as a full model after
  each chunk at each penalty, when the base rates and the small models' sums of the year are
  found.
"""

import argparse
import csv
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from motrisk import folds, full_models, rescore, small_models

CHUNK = 100
CHUNKS = 3
# Tight enough that a chunk ends by its iterations, unless the fit has truly converged.
TOL = 1e-8
MEASURE = Path("data/measure")


def place(test_year: int) -> Path:
    return MEASURE / f"tight_{test_year}"


def weights_path(test_year: int, entry: int, penalty: int, done: int) -> Path:
    return place(test_year) / f"w_{entry}_p{penalty}_{done}.npz"


def weight_files(test_year: int, entry: int) -> list[tuple[int, int, Path]]:
    """Each set of weights saved for the entry, as (penalty, iterations, path), in that order."""
    found = []
    for path in place(test_year).glob(f"w_{entry}_p*_*.npz"):
        _, _, penalty, done = path.stem.split("_")
        found.append((int(penalty[1:]), int(done), path))
    return sorted(found)


def build(test_year: int, encoding: str, memory: str) -> None:
    started = time.perf_counter()
    con = small_models.connect(memory_limit=memory)
    d = small_models.fold_inputs(con, test_year, encoding=encoding)
    cols = full_models.prepare(con, test_year, encoding)
    if cols["d"] != d:
        raise SystemExit(f"the matrix has {cols['d']} columns, the fold {d} inputs")
    saved = np.load(folds.TRAIN_DIRS[encoding] / f"full_model_{test_year}_coefs.npz")
    pairs = list(zip(saved["pair_makes"].tolist(), saved["pair_models"].tolist(), strict=True))
    if int(saved["d"]) != d or pairs != [tuple(p) for p in cols["pairs"]]:
        raise SystemExit("the saved weights do not line up with the fold's inputs")
    entry_classes = np.array(
        con.execute("SELECT entry, test_class_id FROM entry_classes").fetchall(), dtype=np.int64
    )
    out = place(test_year)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "entry_classes.npy", entry_classes)
    for name, years in (("test", [test_year]), ("train", folds.training_years(test_year))):
        x, classes, label_rows, label_entries = full_models.design(con, years, False, cols)
        np.savez(
            out / f"{name}.npz",
            data=x.data,
            indices=x.indices,
            indptr=x.indptr,
            shape=np.array(x.shape),
            classes=classes,
            label_rows=label_rows,
            label_entries=label_entries,
        )
        full_models.say(started, f"{name}: {x.shape[0]:,} rows, {x.nnz:,} values, saved")
        del x, classes, label_rows, label_entries
    con.close()


def load(test_year: int, name: str, dtype) -> tuple:
    """A saved matrix in the precision asked for, with each row's class and labels."""
    f = np.load(place(test_year) / f"{name}.npz")
    data = f["data"].astype(dtype)
    x = sp.csr_matrix((data, f["indices"], f["indptr"]), shape=tuple(f["shape"]), copy=False)
    if x.indices.dtype != np.int32 or x.indptr.dtype != np.int32:
        raise SystemExit("SciPy widened the matrix's offsets")
    return x, f["classes"], f["label_rows"], f["label_entries"]


def classes_of(test_year: int, entry: int) -> np.ndarray:
    pairs = np.load(place(test_year) / "entry_classes.npy")
    return pairs[pairs[:, 0] == entry, 1]


def loss(x, y, weight, w, b, penalty: int) -> float:
    """The training objective scikit-learn minimises with C = 1/penalty: the weighted mean log loss
    plus penalty times the L2 term divided by the rows' total weight."""
    z = x @ w + b
    total = weight.sum()
    log_loss = (weight * (np.logaddexp(0.0, z) - y * z)).sum() / total
    return float(log_loss + penalty * (w @ w) / (2 * total))


def fit(test_year: int, entries: list[int], encoding: str, penalties: list[int], chunks: int):
    started = time.perf_counter()
    x, classes, label_rows, label_entries = load(test_year, "train", np.float64)
    full_models.say(started, f"training matrix in 64 bits: {x.shape[0]:,} rows, {x.nnz:,} values")
    saved = np.load(folds.TRAIN_DIRS[encoding] / f"full_model_{test_year}_coefs.npz")
    at = {e: i for i, e in enumerate(saved["entries"].tolist())}
    for e in entries:
        if e not in at:
            raise SystemExit(f"entry {e} has no full model in this fold")
        weight = np.isin(classes, classes_of(test_year, e)).astype(np.float64)
        y = full_models.labels(label_rows, label_entries, x.shape[0], e)
        for penalty in penalties:
            w = saved["coef"][at[e]].astype(np.float64)
            b = float(saved["intercept"][at[e]])
            done = 0
            # Every penalty starts from the same saved weights, kept once.
            if penalty == 1:
                np.savez(weights_path(test_year, e, penalty, done), w=w, b=b)
            full_models.say(
                started,
                f"entry {e}, penalty {penalty}, saved weights: "
                f"objective {loss(x, y, weight, w, b, penalty):.10f}",
            )
            for _ in range(chunks):
                model = LogisticRegression(
                    C=1.0 / penalty, tol=TOL, max_iter=CHUNK, warm_start=True
                )
                model.coef_, model.intercept_ = w[None, :].copy(), np.array([b])
                t0 = time.perf_counter()
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ConvergenceWarning)
                    model.fit(x, y, sample_weight=weight)
                step = int(model.n_iter_[0])
                change = float(np.abs(model.coef_[0] - w).max())
                w, b, done = model.coef_[0].copy(), float(model.intercept_[0]), done + step
                np.savez(weights_path(test_year, e, penalty, done), w=w, b=b)
                full_models.say(
                    started,
                    f"entry {e}, penalty {penalty}, {done} iterations: "
                    f"objective {loss(x, y, weight, w, b, penalty):.10f}; "
                    f"{step} in {time.perf_counter() - t0:.0f} s, "
                    f"largest weight change {change:.4f}",
                )
                if step < CHUNK:
                    full_models.say(started, f"entry {e}, penalty {penalty}: converged")
                    break


def skill(rows: pd.DataFrame, reference: pd.DataFrame) -> float:
    """The Brier skill of the cells in rows, sums per fine band, pooled over their entries:
    1 - sum (p - y)^2 / the same with each entry at its base rate, its share of ones in the
    training rows, which reference holds by entry."""
    e = rows.groupby("entry")[["rows", "ones", "sum_p2", "sum_p_ones"]].sum()
    rate = reference.loc[e.index, "train_ones"] / reference.loc[e.index, "train_rows"]
    bs = (e["sum_p2"] - 2 * e["sum_p_ones"] + e["ones"]).sum()
    base = (e["rows"] * rate * rate - 2 * rate * e["ones"] + e["ones"]).sum()
    return float(1 - bs / base)


def squares(rows: pd.DataFrame, entries) -> pd.Series:
    """Each entry's sum of (p - y)^2, from sums per fine band."""
    e = rows[rows["entry"].isin(entries)].groupby("entry")[["ones", "sum_p2", "sum_p_ones"]].sum()
    return e["sum_p2"] - 2 * e["sum_p_ones"] + e["ones"]


def moved(encoding: str) -> None:
    first, second = folds.TRAIN_DIRS["pairs"], folds.TRAIN_DIRS[encoding]
    for year in folds.TEST_YEARS:
        tier = {
            d: pd.read_csv(d / f"small_model_{year}_scores.csv").set_index("entry")["tier"]
            for d in (first, second)
        }
        group = tier[second].index[(tier[second] == "full") & (tier[first] == "small")]
        reference = pd.read_csv(first / f"small_model_{year}_reference.csv").set_index("entry")
        as_small = pd.read_csv(first / f"small_model_{year}_fine.csv")
        as_full = pd.read_csv(second / f"full_model_{year}_fine.csv")
        fits = pd.read_csv(second / f"full_model_{year}_scores.csv").set_index("entry")["n_iter"]
        first_fits = pd.read_csv(first / f"full_model_{year}_scores.csv")["n_iter"]
        print(
            f"{year}: {len(group)} entries full in the second model and small in the first, "
            f"skill {skill(as_small[as_small['entry'].isin(group)], reference):.4f} as small, "
            f"{skill(as_full[as_full['entry'].isin(group)], reference):.4f} as full; "
            f"their full fits' median iterations {fits[group].median():g}, "
            f"{(fits[group] <= 5).sum()} with 5 or fewer; the first model's {len(first_fits)} "
            f"full fits' {first_fits.median():g}, {(first_fits <= 5).sum()} with 5 or fewer"
        )
        # Each entry's sum of (p - y)^2 as full less as small: where the full models lose it.
        lost = (squares(as_full, group) - squares(as_small, group)).sort_values(ascending=False)
        if lost.sum() > 0:
            top = ", ".join(f"{e} {v / lost.sum():.0%}" for e, v in lost.head(3).items())
            print(f"  the most of it lost by entry {top}")


def score(test_year: int, entries: list[int], encoding: str) -> None:
    started = time.perf_counter()
    x, classes, label_rows, label_entries = load(test_year, "test", np.float32)
    bands = rescore.run_bands(folds.TRAIN_DIRS[encoding] / f"full_model_{test_year}_bands.csv")
    out = []
    for e in entries:
        mask = np.isin(classes, classes_of(test_year, e))
        y = full_models.labels(label_rows, label_entries, x.shape[0], e)[mask]
        files = weight_files(test_year, e)
        if not files or files[0][:2] != (1, 0):
            raise SystemExit(f"entry {e}: the saved weights are missing")
        for penalty, done, path in files:
            f = np.load(path)
            # As the run scored: 32-bit inputs and weights, the logistic in 64 bits.
            z = x @ f["w"].astype(np.float32) + np.float32(f["b"])
            p = 1.0 / (1.0 + np.exp(-z[mask].astype(np.float64)))
            t = rescore.fine_tally(p, np.ones(len(p), dtype=np.int64), y)
            if (penalty, done) == (1, 0) and rescore.moved(e, t, *bands[e]):
                raise SystemExit(f"entry {e}: the saved weights do not give the run's bands")
            out += [
                [test_year, e, penalty, done, int(band), *(t[k][band].item() for k in rescore.SUMS)]
                for band in np.flatnonzero(t["rows"])
            ]
        full_models.say(started, f"entry {e}: {len(files)} sets of weights scored")

    path = folds.TRAIN_DIRS[encoding] / f"tight_{test_year}_fine.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["test_year", "entry", "penalty", "iterations", "fine_band", *rescore.SUMS])
        writer.writerows(out)
    full_models.say(started, f"wrote {path}; the saved weights give the run's bands")

    reference = folds.TRAIN_DIRS["pairs"] / f"small_model_{test_year}_reference.csv"
    small = folds.TRAIN_DIRS["pairs"] / f"small_model_{test_year}_fine.csv"
    if reference.exists() and small.exists():
        r = pd.read_csv(reference).set_index("entry")
        s = pd.read_csv(small)
        tight = pd.read_csv(path)
        for e in entries:
            first = skill(s[s["entry"] == e], r)
            print(f"entry {e}: skill as the first model's small model {first:+.4f}")
            mine = tight[tight["entry"] == e]
            start = skill(mine[mine["iterations"] == 0], r)
            for penalty, g in mine[mine["iterations"] > 0].groupby("penalty"):
                steps = ", ".join(
                    f"{n} iterations {skill(h, r):+.4f}" for n, h in g.groupby("iterations")
                )
                print(f"  full, penalty {penalty}: saved weights {start:+.4f}, {steps}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refit some full entries in 64-bit floats.")
    parser.add_argument("step", choices=["moved", "build", "fit", "score"])
    parser.add_argument("test_year", type=int, nargs="?")
    parser.add_argument("entries", type=int, nargs="*")
    parser.add_argument("--encoding", choices=folds.ENCODINGS, default="pooled")
    parser.add_argument("--memory", default="4GB", help="build: DuckDB's memory limit")
    parser.add_argument(
        "--penalty", type=int, nargs="+", default=[1], help="fit: multiples of the run's penalty"
    )
    parser.add_argument("--chunks", type=int, default=CHUNKS, help="fit: chunks at most")
    a = parser.parse_args()
    if a.step != "moved" and a.test_year is None:
        parser.error(f"{a.step} needs the test year")
    if a.step == "moved":
        moved(a.encoding)
    elif a.step == "build":
        build(a.test_year, a.encoding, a.memory)
    elif a.step == "fit":
        fit(a.test_year, a.entries, a.encoding, a.penalty, a.chunks)
    else:
        score(a.test_year, a.entries, a.encoding)


if __name__ == "__main__":
    main()
