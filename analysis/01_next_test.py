"""Q1_NEXT_TEST: how well the models predict each slot's problems, against the two baselines.

For every test year, 2020 to 2025, and p_crit = 0.1, 0.25 and 0.5, this writes to
data/processed/evaluate/:

- scores.csv: the model, Repeat and Most popular, pooled over every entry and per tier, with
  whether the model beats each baseline (a higher precision and a higher recall), and the share
  of money each saves at p_crit = t/m;
- shuffled.csv: the models retrained on shuffled labels, pooled, against Most popular, which
  they must not beat;
- groups.csv: the model's counts per group of the defects, precision read only from 100 flags
  and recall only from 100 problems, and the money saved only where both are read;
- calibration.csv: the calibration curve pooled over every entry, per band of probability;
- calibration_check.csv: the precision promised and delivered at each p_crit, whether the year is
  off, and, when it is, from 2021, the scores and the money saved after an isotonic map fitted on
  the previous year;
- brier.csv: the Brier score of the model, the shuffled models and the base rate, pooled and per
  tier, the skill of each against the base rate, and, pooled, the score's terms.

It reads the training run's results in data/processed/train/, with the fine bands that
src/motrisk/rescore.py adds to them, the baselines' counts and the entry dictionary, and stops
unless: every fold holds each entry once, with the same full entries in its two files; the bands
at p_crit = 0.5 give each entry the counts the run wrote; the model and both baselines score the
same problems; the tiers and the groups add up to the pooled counts; the fine bands hold each
entry's rows and ones as the run's bands do; and the base-rate entries score as the base rate.
Run from the repository's root:

    python analysis/01_next_test.py
    python analysis/01_next_test.py --encoding pooled    # the second model

The second model, with make and model pooled (folds.pair_columns), is read from
data/processed/train_pooled/ and written to data/processed/evaluate_pooled/, beside the first.
Scored after the first, it is then compared with it under the rule fixed before either was
scored, in compare.csv.
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
# The memo's example of a cut-off set per problem: Brakes > Rigid brake pipes, Tyres > Tread depth.
EXAMPLE_GROUPS = (20033, 20233)
TIERS = ("full", "small", "base_rate")
# Our prediction for 2025, written down before any score was computed, for each model:
# p_crit: (precision low, high), (recall low, high).
PREDICTIONS = {
    "pairs": {0.5: ((0.42, 0.58), (0.010, 0.020)), 0.1: ((0.18, 0.32), (0.13, 0.25))},
    "pooled": {0.5: ((0.44, 0.52), (0.022, 0.026)), 0.1: ((0.185, 0.21), (0.265, 0.295))},
}
# Our prediction of 2026-11-18, written down before any Brier score or the second model's money
# saved was computed: the Brier skill in 2025, (low, high), and the money saved in 2025 at each
# p_crit.
PREDICTED_SKILL = {"pairs": (0.045, 0.08), "pooled": (0.045, 0.088)}
PREDICTED_SAVED = {"pooled": {0.1: (0.122, 0.155), 0.25: (0.025, 0.035), 0.5: (-0.003, 0.001)}}
# The rule, fixed on 2026-11-18 before either was computed: the second model is better than the
# first only if, in every test year, its Brier skill is higher, its money saved is higher at each
# of RULE_P_CRITS, and its shuffled-label check passes. Otherwise the first is kept. At 0.5 neither
# model saves money, so the two differ there by noise; it is reported, not compared.
RULE_P_CRITS = (0.1, 0.25)


def entries() -> set[int]:
    with open(baselines.ENTRIES, newline="") as f:
        return {int(r["entry"]) for r in csv.DictReader(f)}


def read_fold(kind: str, year: int, train: Path) -> tuple[pd.DataFrame, ...]:
    """A fold's cells, its fine bands, and every entry's tier and the counts at p_crit = 0.5 the run
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
    at_half = evaluate.counts_at(cells, folds.P_CRIT).set_index("entry")[["tp", "fp", "fn"]]
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

        for p_crit in evaluate.P_CRITS:
            counts = evaluate.counts_at(cells["model"], p_crit)
            pooled = evaluate.score(counts)
            parts = sum(
                evaluate.score(counts[counts["tier"] == t])[["tp", "fp", "fn"]] for t in TIERS
            )
            add(counts, parts, f"{year} {p_crit}: the tiers")
            for scope in ("pooled", *TIERS):
                s = pooled if scope == "pooled" else evaluate.score(counts[counts["tier"] == scope])
                row = {"test_year": year, "p_crit": p_crit, "scope": scope}
                scores.append(
                    {
                        **row,
                        "source": "model",
                        **s.drop("promised"),
                        "saved": evaluate.saved(s, p_crit),
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
                            "saved": evaluate.saved(b, p_crit),
                        }
                    )

            g = evaluate.by_group(counts, groups)
            add(counts, g[["tp", "fp", "fn"]].sum(), f"{year} {p_crit}: the groups")
            g.insert(1, "group_path", g["group_id"].map(paths))
            read = g["precision"].notna() & g["recall"].notna()
            saved = [evaluate.saved(r, p_crit) for _, r in g.iterrows()]
            g["saved"] = pd.Series(saved, index=g.index).where(read)
            by_group.append(g.assign(test_year=year, p_crit=p_crit))

            sh = evaluate.score(evaluate.counts_at(cells["shuffled"], p_crit))
            mp = b_score["most_popular", "pooled"]
            shuffled.append(
                {
                    "test_year": year,
                    "p_crit": p_crit,
                    **sh.drop("promised"),
                    **{f"most_popular_{k}": v for k, v in mp.drop("promised").items()},
                    "passes": not evaluate.beats(sh, mp),
                }
            )

            check = {
                "test_year": year,
                "p_crit": p_crit,
                "promised": pooled["promised"],
                "delivered": pooled["precision"],
            }
            if pd.notna(pooled["precision"]):
                check["allowed_gap"] = evaluate.allowed_gap(pooled["promised"])
                check["off"] = evaluate.is_off(pooled["precision"], pooled["promised"])
                if check["off"] and previous is not None:
                    mapping = evaluate.isotonic_map(previous)
                    after = evaluate.score(
                        evaluate.counts_at(evaluate.remap(cells["model"], mapping), p_crit)
                    )
                    check.update({f"after_{k}": v for k, v in after.items()})
                    check["after_saved"] = evaluate.saved(after, p_crit)
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
    first = {"groups": ["test_year", "p_crit"], "calibration": ["test_year"]}
    for name, t in tables.items():
        lead = first.get(name, [])
        t = t[lead + [c for c in t.columns if c not in lead]]
        t.to_csv(out / f"{name}.csv", index=False, lineterminator="\n")
    summary(tables, encoding)
    if encoding == "pooled":
        compare()


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


def compare() -> None:
    """The second model against the first, year by year, under the rule; writes compare.csv
    beside the second model's results and prints the verdict."""
    read = {
        k: {n: pd.read_csv(OUT_DIRS[k] / f"{n}.csv") for n in ("scores", "brier", "shuffled")}
        for k in ("pairs", "pooled")
        if (OUT_DIRS[k] / "brier.csv").exists()
    }
    if len(read) < 2:
        raise SystemExit("score the first model with this version before comparing")
    rows = []
    for year in folds.TEST_YEARS:
        value = {}
        for k, t in read.items():
            b = t["brier"]
            pooled = b[(b["test_year"] == year) & (b["scope"] == "pooled")]
            value[k, "skill"] = float(pooled.loc[pooled["source"] == "model", "skill"].iloc[0])
            s = t["scores"]
            s = s[(s["test_year"] == year) & (s["scope"] == "pooled") & (s["source"] == "model")]
            for p_crit in RULE_P_CRITS:
                value[k, f"saved at {p_crit}"] = float(
                    s.loc[s["p_crit"] == p_crit, "saved"].iloc[0]
                )
        for measure in ["skill", *(f"saved at {p_crit}" for p_crit in RULE_P_CRITS)]:
            first, second = value["pairs", measure], value["pooled", measure]
            rows.append(
                {
                    "test_year": year,
                    "measure": measure,
                    "first": first,
                    "second": second,
                    "second_leads": second > first,
                }
            )
        sh = read["pooled"]["shuffled"]
        passes = bool(sh.loc[sh["test_year"] == year, "passes"].all())
        rows.append({"test_year": year, "measure": "shuffled check", "second_leads": passes})
    t = pd.DataFrame(rows)
    t.to_csv(OUT_DIRS["pooled"] / "compare.csv", index=False, lineterminator="\n")
    print("the second model against the first: where it does not lead")
    print(t[~t["second_leads"]].to_string(index=False) if not t["second_leads"].all() else "  none")
    better = bool(t["second_leads"].all())
    print(
        f"verdict: the second model is {'better' if better else 'not better'}; "
        f"{'it replaces the first' if better else 'the first is kept'}"
    )


def groups_2025(groups: pd.DataFrame) -> None:
    """The groups in 2025: at p_crit = 0.1, those whose money saved is read, the three that save
    the most and the three that save the least, and those never flagged; and the example groups'
    money saved at each p_crit."""
    year = groups[groups["test_year"] == 2025]
    g = year[year["p_crit"] == 0.1]
    problems = g["problems"].sum()
    read = g[g["saved"].notna()].sort_values("saved", ascending=False)
    never = g[(g["problems"] >= evaluate.MIN_PROBLEMS) & (g["flags"] == 0)]
    print(
        f"groups in 2025 at p_crit 0.1: {len(g)} with problems; money saved read for {len(read)}, "
        f"{pct(read['problems'].sum() / problems)} of the problems, {(read['saved'] > 0).sum()} "
        f"saving money; {len(never)} with {evaluate.MIN_PROBLEMS} problems or more never flagged, "
        f"{pct(never['problems'].sum() / problems)} of the problems"
    )
    for label, rows in (("most", read.head(3)), ("least", read.tail(3).iloc[::-1])):
        for _, r in rows.iterrows():
            print(
                f"  saves the {label}: {r['group_path']}, {r['problems']:,} problems, "
                f"precision {pct(r['precision'])}, recall {pct(r['recall'])}, "
                f"saved {pct(r['saved'])}"
            )
    for gid in EXAMPLE_GROUPS:
        rows = year[year["group_id"] == gid].set_index("p_crit")
        steps = ", ".join(f"p_crit {p}: {pct(rows.loc[p, 'saved'])}" for p in evaluate.P_CRITS)
        print(f"  example, {rows['group_path'].iloc[0]}: money saved at {steps}")


def summary(t: dict[str, pd.DataFrame], encoding: str) -> None:
    """The pooled scores, the shuffled check and calibration per year, then 2025 beside the
    prediction."""
    s = t["scores"][t["scores"]["scope"] == "pooled"].set_index(["test_year", "p_crit", "source"])
    sh = t["shuffled"].set_index(["test_year", "p_crit"])
    ch = t["calibration_check"].set_index(["test_year", "p_crit"])
    print("pooled, precision / recall; beats Repeat, Most popular; shuffled passes; off")
    for year in folds.TEST_YEARS:
        for p_crit in evaluate.P_CRITS:
            m = s.loc[year, p_crit, "model"]
            r = s.loc[year, p_crit, "repeat"]
            p = s.loc[year, p_crit, "most_popular"]
            print(
                f"{year} {p_crit:4}: model {pct(m['precision'])} {pct(m['recall'])}  "
                f"repeat {pct(r['precision'])} {pct(r['recall'])}  "
                f"most popular {pct(p['precision'])} {pct(p['recall'])}  "
                f"{'Y' if m['beats_repeat'] else 'n'}{'Y' if m['beats_most_popular'] else 'n'}  "
                f"shuffled {'passes' if sh.loc[year, p_crit]['passes'] else 'FAILS'}  "
                f"off {ch.loc[year, p_crit].get('off', '-')}"
            )
    print("money saved at p_crit = t/m: model, Repeat, Most popular")
    for year in folds.TEST_YEARS:
        print(
            f"{year}: "
            + "  ".join(
                f"p_crit {p_crit}: "
                + " ".join(pct(s.loc[year, p_crit, src]["saved"]) for src in SOURCES)
                for p_crit in evaluate.P_CRITS
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
    groups_2025(t["groups"])
    print("2025 beside the prediction written down before any score was computed:")
    lo, hi = PREDICTED_SKILL[encoding]
    m = b.loc[2025, "pooled", "model"]
    print(f"  Brier skill {m['skill']:+.4f}, predicted {lo:+.4f} to {hi:+.4f}")
    for p_crit, (lo, hi) in PREDICTED_SAVED.get(encoding, {}).items():
        saved = s.loc[2025, p_crit, "model"]["saved"]
        print(f"  money saved at p_crit {p_crit}: {pct(saved)}, predicted {pct(lo)} to {pct(hi)}")
    for p_crit, ((p_lo, p_hi), (r_lo, r_hi)) in PREDICTIONS[encoding].items():
        m = s.loc[2025, p_crit, "model"]
        print(
            f"  p_crit {p_crit}: precision {pct(m['precision'])}, "
            f"predicted {pct(p_lo)} to {pct(p_hi)}; "
            f"recall {pct(m['recall'])}, predicted {pct(r_lo)} to {pct(r_hi)}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Q1_NEXT_TEST, scored against both baselines.")
    parser.add_argument(
        "--encoding", choices=folds.ENCODINGS, default="pairs", help="which model to score"
    )
    main(parser.parse_args().encoding)
