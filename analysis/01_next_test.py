"""Q1_NEXT_TEST: how well the models predict each slot's problems, against the two baselines.

For every test year, 2020 to 2025, and tau = 0.1, 0.25 and 0.5, this writes to
data/processed/evaluate/:

- scores.csv: the model, Repeat and Most popular, pooled over every entry and per tier, with
  whether the model beats each baseline (a higher precision and a higher recall), and the share
  of money each saves at tau = t/m;
- shuffled.csv: the models retrained on shuffled labels, pooled, against Most popular, which
  they must not beat;
- groups.csv: the model's counts per group of the defects, precision read only from 100 flags
  and recall only from 100 problems;
- calibration.csv: the calibration curve pooled over every entry, per band of probability;
- calibration_check.csv: the precision promised and delivered at each tau, whether the year is
  off, and, when it is, from 2021, the scores after an isotonic map fitted on the previous year;
- brier.csv: the Brier score of the model, the shuffled models and the base rate, pooled and per
  tier, the skill of each against the base rate, and, pooled, the score's terms.

It reads the training run's results in data/processed/train/, with the fine bands that
src/motrisk/rescore.py adds to them, the baselines' counts and the entry dictionary, and stops
unless: every fold holds each entry once, with the same full entries in its two files; the bands
at tau = 0.5 give each entry the counts the run wrote; the model and both baselines score the
same problems; the tiers and the groups add up to the pooled counts; the fine bands hold each
entry's rows and ones as the run's bands do; and the base-rate entries score as the base rate.
Run from the repository's root:

    python analysis/01_next_test.py
    python analysis/01_next_test.py --encoding pooled    # the second model

The second model, with make and model pooled (folds.pair_columns), is read from
data/processed/train_pooled/ and written to data/processed/evaluate_pooled/, beside the first.
"""

import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd

from motrisk import baselines, evaluate, folds

DICTIONARY = Path("data/processed/entry_dictionary.csv")
OUT_DIRS = {
    "pairs": Path("data/processed/evaluate"),
    "pooled": Path("data/processed/evaluate_pooled"),
}
KINDS = ("model", "shuffled")
SOURCES = ("model", "repeat", "most_popular")
TIERS = ("full", "small", "base_rate")
# Our prediction for 2025, written down before any score was computed, for each model:
# tau: (precision low, high), (recall low, high).
PREDICTIONS = {
    "pairs": {0.5: ((0.42, 0.58), (0.010, 0.020)), 0.1: ((0.18, 0.32), (0.13, 0.25))},
    "pooled": {0.5: ((0.44, 0.52), (0.022, 0.026)), 0.1: ((0.185, 0.21), (0.265, 0.295))},
}


def entries() -> set[int]:
    with open(baselines.ENTRIES, newline="") as f:
        return {int(r["entry"]) for r in csv.DictReader(f)}


def read_fold(kind: str, year: int, train: Path) -> tuple[pd.DataFrame, ...]:
    """A fold's cells, its fine bands, and every entry's tier and the counts at tau = 0.5 the run
    wrote."""
    small = [pd.read_csv(train / f"small_{kind}_{year}_{s}.csv") for s in ("scores", "bands")]
    full = [pd.read_csv(train / f"full_{kind}_{year}_{s}.csv") for s in ("scores", "bands")]
    cells = evaluate.fold_cells(small[0], small[1], full[0], full[1])
    written = pd.concat([small[0][small[0]["tier"] != "full"], full[0]]).set_index("entry")
    written = written[["tier", "tp", "fp", "fn"]].astype({"tp": int, "fp": int, "fn": int})
    written = written.replace({"tier": {"none": "base_rate"}})
    fine = evaluate.fine_cells(
        pd.read_csv(train / f"small_{kind}_{year}_fine.csv"),
        pd.read_csv(train / f"full_{kind}_{year}_fine.csv"),
        written["tier"],
    )
    return cells, fine, written


def check_fold(kind, year, cells, fine, written, baseline, every) -> None:
    """Checks (a) to (c) and (e): every entry once, the bands give the run's counts, the same
    problems, and the fine bands hold the rows and ones of the run's bands."""
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
    run = cells.groupby("entry")[["rows", "ones"]].sum()
    scored = fine.groupby("entry")[["rows", "ones"]].sum()
    entries = run.index.union(scored.index)
    if not run.reindex(entries, fill_value=0).equals(scored.reindex(entries, fill_value=0)):
        raise SystemExit(f"{kind} {year}: the fine bands do not hold the run's rows and ones")


def add(counts: pd.DataFrame, part: pd.Series, what: str) -> None:
    """Check (d): a breakdown adds up to the pooled counts."""
    for k in ("tp", "fp", "fn"):
        if int(part[k]) != int(counts[k].sum()):
            raise SystemExit(f"{what} do not add up to the pooled {k}")


def main(encoding: str = "pairs") -> None:
    train, out = folds.TRAIN_DIRS[encoding], OUT_DIRS[encoding]
    every = entries()
    groups = pd.read_csv(DICTIONARY, usecols=["entry", "group_id", "group_path"])
    paths = groups.drop_duplicates("group_id").set_index("group_id")["group_path"]
    base = pd.read_csv(baselines.OUT)
    scores, shuffled, by_group, curves, checks, briers = [], [], [], [], [], []
    previous = None

    for year in folds.TEST_YEARS:
        b_year = base[base["test_year"] == year].set_index("entry")
        cells, fine, tier = {}, {}, None
        for kind in KINDS:
            cells[kind], fine[kind], written = read_fold(kind, year, train)
            check_fold(kind, year, cells[kind], fine[kind], written, b_year, every)
            if kind == "model":
                tier = written["tier"]
        briers += brier_rows(year, fine, pd.read_csv(train / f"small_model_{year}_reference.csv"))

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
                        "saved": evaluate.saved(s, tau),
                        "beats_repeat": evaluate.beats(s, b_score["repeat", scope]),
                        "beats_most_popular": evaluate.beats(s, b_score["most_popular", scope]),
                    }
                )
                for name in ("repeat", "most_popular"):
                    b = b_score[name, scope]
                    scores.append(
                        {
                            **row,
                            "source": name,
                            **b.drop("promised"),
                            "saved": evaluate.saved(b, tau),
                        }
                    )

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

    out.mkdir(parents=True, exist_ok=True)
    tables = {
        "scores": pd.DataFrame(scores),
        "shuffled": pd.DataFrame(shuffled),
        "groups": pd.concat(by_group),
        "calibration": pd.concat(curves),
        "calibration_check": pd.DataFrame(checks),
        "brier": pd.DataFrame(briers),
    }
    first = {"groups": ["test_year", "tau"], "calibration": ["test_year"]}
    for name, t in tables.items():
        lead = first.get(name, [])
        t = t[lead + [c for c in t.columns if c not in lead]]
        t.to_csv(out / f"{name}.csv", index=False, lineterminator="\n")
    summary(tables, PREDICTIONS[encoding])


def in_scope(c: pd.DataFrame, scope: str) -> pd.DataFrame:
    return c if scope == "pooled" else c[c["tier"] == scope]


def brier_rows(year: int, fine: dict[str, pd.DataFrame], reference: pd.DataFrame) -> list[dict]:
    """The Brier score of the model, the shuffled models and the base rate, pooled and per tier,
    with each one's skill against the base rate on the same entries, and, pooled, its terms.
    Check (f): the base-rate entries score as the base rate."""
    totals = fine["model"].groupby(["entry", "tier"], as_index=False)[["rows", "ones"]].sum()
    sources = {**fine, "base_rate": evaluate.reference_cells(reference, totals)}
    out = []
    for scope in ("pooled", *TIERS):
        reference_bs = evaluate.brier(in_scope(sources["base_rate"], scope))
        for source, c in sources.items():
            p = in_scope(c, scope)
            bs = evaluate.brier(p)
            if scope == "base_rate" and not np.isclose(bs, reference_bs, rtol=1e-9):
                raise SystemExit(
                    f"{year} {source}: the base-rate entries do not score as the base rate"
                )
            row = {
                "test_year": year,
                "source": source,
                "scope": scope,
                "rows": int(p["rows"].sum()),
                "ones": int(p["ones"].sum()),
                "brier": bs,
                "skill": 1 - bs / reference_bs,
            }
            if scope == "pooled":
                row.update(evaluate.decomposition(c))
            out.append(row)
    return out


def pct(x) -> str:
    return "   -   " if pd.isna(x) else f"{100 * x:6.2f}%"


def summary(t: dict[str, pd.DataFrame], prediction: dict) -> None:
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
    print("money saved at tau = t/m: model, Repeat, Most popular")
    for year in folds.TEST_YEARS:
        print(
            f"{year}: "
            + "  ".join(
                f"tau {tau}: " + " ".join(pct(s.loc[year, tau, src]["saved"]) for src in SOURCES)
                for tau in evaluate.TAUS
            )
        )
    b = t["brier"].set_index(["test_year", "scope", "source"])
    print("Brier skill against the base rate, pooled: model, shuffled; the model's terms")
    for year in folds.TEST_YEARS:
        m, sh = b.loc[year, "pooled", "model"], b.loc[year, "pooled", "shuffled"]
        print(
            f"{year}: model {m['skill']:+.4f}  shuffled {sh['skill']:+.4f}"
            f"  BS {m['brier']:.3e}, reliability {m['reliability']:.2e}, "
            f"resolution {m['resolution']:.2e}, uncertainty {m['uncertainty']:.2e}"
        )
    print("2025 beside the prediction written down before any score was computed:")
    for tau, ((p_lo, p_hi), (r_lo, r_hi)) in prediction.items():
        m = s.loc[2025, tau, "model"]
        print(
            f"  tau {tau}: precision {pct(m['precision'])}, predicted {pct(p_lo)} to {pct(p_hi)}; "
            f"recall {pct(m['recall'])}, predicted {pct(r_lo)} to {pct(r_hi)}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Q1_NEXT_TEST, scored against both baselines.")
    parser.add_argument(
        "--encoding", choices=folds.ENCODINGS, default="pairs", help="which model to score"
    )
    main(parser.parse_args().encoding)
