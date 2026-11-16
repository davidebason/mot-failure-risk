"""Q1_NEXT_TEST: how well the models predict each slot's problems, against the two baselines.

For every test year, 2020 to 2025, and tau = 0.1, 0.25 and 0.5, this writes to
data/processed/evaluate/:

- scores.csv: the model, Repeat and Most popular, pooled over every entry and per tier, with
  whether the model beats each baseline (a higher precision and a higher recall);
- shuffled.csv: the models retrained on shuffled labels, pooled, against Most popular, which
  they must not beat;
- groups.csv: the model's counts per group of the defects, precision read only from 100 flags
  and recall only from 100 problems;
- calibration.csv: the calibration curve pooled over every entry, per band of probability;
- calibration_check.csv: the precision promised and delivered at each tau, whether the year is
  off, and, when it is, from 2021, the scores after an isotonic map fitted on the previous year.

It reads the training run's results in data/processed/train/, the baselines' counts and the entry
dictionary, and stops unless: every fold holds each entry once, with the same full entries in its
two files; the bands at tau = 0.5 give each entry the counts the run wrote; the model and both
baselines score the same problems; and the tiers and the groups add up to the pooled counts.
Run from the repository's root:

    python analysis/01_next_test.py
"""

import csv
from pathlib import Path

import pandas as pd

from motrisk import baselines, evaluate, folds

TRAIN = Path("data/processed/train")
DICTIONARY = Path("data/processed/entry_dictionary.csv")
OUT = Path("data/processed/evaluate")
KINDS = ("model", "shuffled")
TIERS = ("full", "small", "base_rate")
# Our prediction for 2025, written down before any score was computed:
# tau: (precision low, high), (recall low, high).
PREDICTION = {0.5: ((0.42, 0.58), (0.010, 0.020)), 0.1: ((0.18, 0.32), (0.13, 0.25))}


def entries() -> set[int]:
    with open(baselines.ENTRIES, newline="") as f:
        return {int(r["entry"]) for r in csv.DictReader(f)}


def read_fold(kind: str, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A fold's cells, and every entry's tier and the counts at tau = 0.5 the run wrote."""
    small = [pd.read_csv(TRAIN / f"small_{kind}_{year}_{s}.csv") for s in ("scores", "bands")]
    full = [pd.read_csv(TRAIN / f"full_{kind}_{year}_{s}.csv") for s in ("scores", "bands")]
    cells = evaluate.fold_cells(small[0], small[1], full[0], full[1])
    written = pd.concat([small[0][small[0]["tier"] != "full"], full[0]]).set_index("entry")
    written = written[["tier", "tp", "fp", "fn"]].astype({"tp": int, "fp": int, "fn": int})
    return cells, written.replace({"tier": {"none": "base_rate"}})


def check_fold(kind, year, cells, written, baseline, every) -> None:
    """Checks (a) to (c): every entry once, the bands give the run's counts, the same problems."""
    if set(written.index) != every or len(written) != len(every):
        raise SystemExit(f"{kind} {year}: the fold does not hold each entry once")
    at_half = evaluate.counts_at(cells, folds.TAU).set_index("entry")[["tp", "fp", "fn"]]
    at_half = at_half.reindex(written.index, fill_value=0)
    if not at_half.equals(written[["tp", "fp", "fn"]]):
        raise SystemExit(f"{kind} {year}: the bands at 0.5 do not give the run's counts")
    ones = at_half["tp"] + at_half["fn"]
    for name, b in baseline.groupby("baseline"):
        theirs = (b["tp"] + b["fn"]).reindex(ones.index, fill_value=0)
        if not theirs.equals(ones):
            raise SystemExit(f"{kind} {year}: the model and {name} score different problems")


def add(counts: pd.DataFrame, part: pd.Series, what: str) -> None:
    """Check (d): a breakdown adds up to the pooled counts."""
    for k in ("tp", "fp", "fn"):
        if int(part[k]) != int(counts[k].sum()):
            raise SystemExit(f"{what} do not add up to the pooled {k}")


def main() -> None:
    every = entries()
    groups = pd.read_csv(DICTIONARY, usecols=["entry", "group_id", "group_path"])
    paths = groups.drop_duplicates("group_id").set_index("group_id")["group_path"]
    base = pd.read_csv(baselines.OUT)
    scores, shuffled, by_group, curves, checks = [], [], [], [], []
    previous = None

    for year in folds.TEST_YEARS:
        b_year = base[base["test_year"] == year].set_index("entry")
        cells, tier = {}, None
        for kind in KINDS:
            cells[kind], written = read_fold(kind, year)
            check_fold(kind, year, cells[kind], written, b_year, every)
            if kind == "model":
                tier = written["tier"]

        b_score = {}
        for name, b in b_year.groupby("baseline"):
            b = b.assign(tier=tier.reindex(b.index).values)
            b_score[name, "pooled"] = evaluate.score(b)
            for t in TIERS:
                b_score[name, t] = evaluate.score(b[b["tier"] == t])

        for tau in evaluate.TAUS:
            counts = evaluate.counts_at(cells["model"], tau)
            pooled = evaluate.score(counts)
            parts = sum(
                evaluate.score(counts[counts["tier"] == t])[["tp", "fp", "fn"]] for t in TIERS
            )
            add(counts, parts, f"{year} {tau}: the tiers")
            for scope in ("pooled", *TIERS):
                s = pooled if scope == "pooled" else evaluate.score(counts[counts["tier"] == scope])
                row = {"test_year": year, "tau": tau, "scope": scope}
                scores.append(
                    {
                        **row,
                        "source": "model",
                        **s.drop("promised"),
                        "beats_repeat": evaluate.beats(s, b_score["repeat", scope]),
                        "beats_most_popular": evaluate.beats(s, b_score["most_popular", scope]),
                    }
                )
                for name in ("repeat", "most_popular"):
                    scores.append({**row, "source": name, **b_score[name, scope].drop("promised")})

            g = evaluate.by_group(counts, groups)
            add(counts, g[["tp", "fp", "fn"]].sum(), f"{year} {tau}: the groups")
            g.insert(1, "group_path", g["group_id"].map(paths))
            by_group.append(g.assign(test_year=year, tau=tau))

            sh = evaluate.score(evaluate.counts_at(cells["shuffled"], tau))
            mp = b_score["most_popular", "pooled"]
            shuffled.append(
                {
                    "test_year": year,
                    "tau": tau,
                    **sh.drop("promised"),
                    **{f"most_popular_{k}": v for k, v in mp.drop("promised").items()},
                    "passes": not evaluate.beats(sh, mp),
                }
            )

            check = {
                "test_year": year,
                "tau": tau,
                "promised": pooled["promised"],
                "delivered": pooled["precision"],
            }
            if pd.notna(pooled["precision"]):
                check["allowed_gap"] = evaluate.allowed_gap(pooled["promised"])
                check["off"] = evaluate.is_off(pooled["precision"], pooled["promised"])
                if check["off"] and previous is not None:
                    mapping = evaluate.isotonic_map(previous)
                    after = evaluate.score(
                        evaluate.counts_at(evaluate.remap(cells["model"], mapping), tau)
                    )
                    check.update({f"after_{k}": v for k, v in after.items()})
            checks.append(check)

        curves.append(evaluate.curve(cells["model"]).assign(test_year=year))
        previous = cells["model"]

    OUT.mkdir(parents=True, exist_ok=True)
    tables = {
        "scores": pd.DataFrame(scores),
        "shuffled": pd.DataFrame(shuffled),
        "groups": pd.concat(by_group),
        "calibration": pd.concat(curves),
        "calibration_check": pd.DataFrame(checks),
    }
    first = {"groups": ["test_year", "tau"], "calibration": ["test_year"]}
    for name, t in tables.items():
        lead = first.get(name, [])
        t = t[lead + [c for c in t.columns if c not in lead]]
        t.to_csv(OUT / f"{name}.csv", index=False, lineterminator="\n")
    summary(tables)


def pct(x) -> str:
    return "   -   " if pd.isna(x) else f"{100 * x:6.2f}%"


def summary(t: dict[str, pd.DataFrame]) -> None:
    """The pooled scores, the shuffled check and calibration per year, then 2025 beside the
    prediction."""
    s = t["scores"][t["scores"]["scope"] == "pooled"].set_index(["test_year", "tau", "source"])
    sh = t["shuffled"].set_index(["test_year", "tau"])
    ch = t["calibration_check"].set_index(["test_year", "tau"])
    print("pooled, precision / recall; beats Repeat, Most popular; shuffled passes; off")
    for year in folds.TEST_YEARS:
        for tau in evaluate.TAUS:
            m = s.loc[year, tau, "model"]
            r = s.loc[year, tau, "repeat"]
            p = s.loc[year, tau, "most_popular"]
            print(
                f"{year} {tau:4}: model {pct(m['precision'])} {pct(m['recall'])}  "
                f"repeat {pct(r['precision'])} {pct(r['recall'])}  "
                f"most popular {pct(p['precision'])} {pct(p['recall'])}  "
                f"{'Y' if m['beats_repeat'] else 'n'}{'Y' if m['beats_most_popular'] else 'n'}  "
                f"shuffled {'passes' if sh.loc[year, tau]['passes'] else 'FAILS'}  "
                f"off {ch.loc[year, tau].get('off', '-')}"
            )
    print("2025 beside the prediction written down before any score was computed:")
    for tau, ((p_lo, p_hi), (r_lo, r_hi)) in PREDICTION.items():
        m = s.loc[2025, tau, "model"]
        print(
            f"  tau {tau}: precision {pct(m['precision'])}, predicted {pct(p_lo)} to {pct(p_hi)}; "
            f"recall {pct(m['recall'])}, predicted {pct(r_lo)} to {pct(r_hi)}"
        )


if __name__ == "__main__":
    main()
