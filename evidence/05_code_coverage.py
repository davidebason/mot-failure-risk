"""Which defect codes are recorded in which years, which were renumbered, and which entries the
year vector keeps.

Establishes the figures under "Which defect codes are kept" in DATA.md. Every failure item from
2018 to 2025 is counted by its code and the way it was recorded (`F`, `P`, `M`, `A`) and by year,
with 2018 split at 20 May, the day the 2018 rules came into force; the tests of April to June 2018
are placed on either side of that day by their date in the 2018 results file. Items carry no test
result, so these counts are over all tests, aborted and abandoned ones included.

From those counts and the lookup tables this reports: the codes recorded before and after 20 May
2018; the codes of the earlier rules still recorded after it; when each code of the 2018 rules is
first and last recorded; the entries the 2018 rules exclude (a dangerous or major defect never
recorded as minor, a minor one never as a failure, an advisory only under a code with advisory
wording) and whether any is ever recorded; the codes renumbered during the period, matched into
pairs by the two rules stated in `motrisk.codes.renumbered`; the problems recorded from 2018 to
2025, which are kept; and the entries of the year vector that remain, overall and for each
vehicle class.

The rules themselves are in `motrisk.codes`, which also writes the dbt seeds the build reads, so
that this file and the build cannot disagree. Reads the archives and data/raw/lookup.zip already
in data/raw/; nothing is fetched. Takes about ten minutes on six cores. Run from the repository
root:

    python evidence/05_code_coverage.py
"""

from collections import Counter
from pathlib import Path

from motrisk.codes import (
    BEFORE,
    PERIODS,
    PRE_EU,
    UNMATCHED,
    allowed,
    count_items,
    coverage,
    read_lookup,
)

RAW = Path("data/raw")


def main() -> None:
    counts = count_items(RAW)
    codes = read_lookup(RAW / "lookup.zip")
    rules = {c for c, code in codes.items() if code.category != PRE_EU}
    earlier = set(codes) - rules
    cov = coverage(codes, counts)

    def items(period: str, subset: set[int]) -> int:
        return sum(n for (c, _), n in counts[period].items() if c in subset)

    unmatched = counts[UNMATCHED].total()
    print(f"items of April to June 2018 matching no test of the results file: {unmatched}")
    print(
        f"before 20 May 2018: {counts[BEFORE].total():,} items, {items(BEFORE, rules):,} on codes "
        f"of the 2018 rules"
    )
    print("from 20 May 2018, per period: items; codes recorded, 2018 rules / earlier / unlisted")
    for p in PERIODS:
        recorded = {c for c, _ in counts[p]}
        unlisted = recorded - set(codes)
        share = 100 * items(p, earlier) / counts[p].total()
        print(
            f"  {p}: {counts[p].total():,}; {len(recorded & rules):,} / {len(recorded & earlier)} "
            f"/ {len(unlisted)}; earlier-rules items {items(p, earlier):,} ({share:.1f}%), "
            f"unlisted items {items(p, unlisted):,}"
        )

    ways = Counter(w for p in PERIODS for (c, w) in counts[p] if c in cov.every)
    print(f"earlier-rules codes recorded in every period: {len(cov.every)}, {cov.every}")
    print(f"  recorded as {dict(ways)}")

    span = cov.span
    late = {c for c, y in span.items() if y[0] > 2018}
    early = {c for c, y in span.items() if y[-1] < 2025}
    print(
        f"codes of the 2018 rules: {len(rules):,}; recorded {len(span):,}, "
        f"never {len(rules) - len(span)}; first recorded after 2018 {len(late)}, "
        f"last recorded before 2025 {len(early)}, both {len(late & early)}"
    )

    print("items recorded in a way the rules exclude, per period: on codes of the 2018 rules;")
    print("  on the earlier-rules codes recorded in every period; on other earlier-rules codes")
    for p in PERIODS:
        bad = Counter()
        for (c, w), n in counts[p].items():
            if c in codes and not allowed(codes[c], w):
                kind = "2018 rules" if c in rules else "every period" if c in cov.every else "other"
                bad[kind] += n
        print(f"  {p}: {bad['2018 rules']}; {bad['every period']}; {bad['other']}")

    by_rule = Counter(rule for *_, rule in cov.pairs)
    print(f"renumbered pairs: {len(cov.pairs)}, rule (i) {by_rule['i']}, rule (ii) {by_rule['ii']}")
    for old, new, rule in cov.pairs:
        print(
            f"  ({rule}) {old}, {span[old][0]} to {span[old][-1]} -> {new}, {span[new][0]} to "
            f"{span[new][-1]}: {codes[new].short}"
        )
    kept_rules = {p for p in cov.kept if p in cov.members}
    dropped = {c for p in set(cov.members) - kept_rules for c in cov.members[p]}
    print(
        f"problems of the 2018 rules: {len(cov.members):,}; recorded from 2018 to 2025: "
        f"{len(kept_rules):,}"
    )
    print(f"codes dropped: {len(dropped)}; share of each period's items on the 2018 rules' codes:")
    for p in PERIODS:
        print(f"  {p}: {100 * items(p, dropped) / items(p, rules):.1f}%")

    print(
        f"problems kept, with the earlier-rules advisories: {len(cov.kept):,}; entries the rules "
        f"allow: {len(cov.allowed):,} of {4 * len(cov.kept):,}; never recorded: {len(cov.never)}, "
        f"{dict(sorted(Counter(w for _, w in cov.never).items()))}"
    )
    for k in "123457":
        listed = {p for p, cs in cov.kept.items() if any(k in codes[c].classes for c in cs)}
        n = sum(1 for p, _ in cov.entries if p in listed)
        print(f"  class {k}: {n:,} entries that can be 1")


if __name__ == "__main__":
    main()
