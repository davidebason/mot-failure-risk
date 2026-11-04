"""Which defect codes the year vector keeps, which renumbered codes it joins, and its entries.

The rules are those under "Which defect codes are kept" and "What the model predicts" in DATA.md.
A code is the publisher's `rfr_id`; a problem is a code, or a pair of codes joined because one
took over the other's defect, numbered by the code used first; an entry of the year vector is a
problem together with a way of recording it (`F`, `P`, `M` or `A`).

Run as a module, it counts every failure item in data/raw/ and writes two dbt seeds: the code
dictionary, mapping each kept code to its problem, and the entries of the year vector. Run from
the repository root, in about ten minutes on six cores:

    python -m motrisk.codes
"""

import csv
import io
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import partial
from multiprocessing import Pool
from pathlib import Path

PRE_EU = "Pre-EU Directive"
WAYS = ("F", "P", "M", "A")
FIRST_YEAR, LAST_YEAR = 2018, 2025
CUT = b"2018-05-20"
# Periods from 20 May 2018 on, in order; 2018 before that day is counted on its own.
BEFORE = "2018 to 19 May"
UNMATCHED = "unmatched"
PERIODS = [f"{FIRST_YEAR} from 20 May"] + [str(y) for y in range(FIRST_YEAR + 1, LAST_YEAR + 1)]
YEAR_OF = {p: int(p[:4]) for p in PERIODS}


@dataclass
class Code:
    """One defect code as the lookup describes it, over every class it is listed for."""

    category: str
    group: str
    short: str
    manual: str
    advisory: bool = False
    classes: set[str] = field(default_factory=set)


def _norm(text: str) -> str:
    return " ".join(text.lower().split()).rstrip(".")


def read_lookup(lookups: Path) -> dict[int, Code]:
    """Every code in `item_detail.csv` inside the lookup archive, keyed by its number."""
    with zipfile.ZipFile(lookups) as archive, archive.open("item_detail.csv") as f:
        rows = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter="|"))
    codes: dict[int, Code] = {}
    for r in rows:
        code = codes.setdefault(
            int(r["rfr_id"]),
            Code(
                category=r["rfr_deficiency_category"],
                group=r["test_item_id"],
                short=_norm(r["rfr_desc"]),
                manual=_norm(r["rfr_insp_manual_desc"]),
            ),
        )
        code.advisory |= bool(r["rfr_advisory_text"].strip())
        code.classes.add(r["test_class_id"])
    return codes


def allowed(code: Code, way: str) -> bool:
    """Whether the rules allow a code to be recorded this way.

    A dangerous or major defect fails the test, as `F` or as `P` when put right at the station,
    and is never minor; a minor defect is only `M`; an advisory, `A`, is recorded only under a code
    with advisory wording; a code of the earlier rules only as an advisory.
    """
    if code.category == PRE_EU:
        return way == "A"
    if way == "M":
        return code.category == "Minor"
    if way in ("F", "P"):
        return code.category != "Minor"
    return code.advisory


def _item_archive(raw: Path, year: int) -> Path:
    name = f"dft_test_item_extracts_{year}.zip" if year >= 2024 else f"dft_test_item_{year}.zip"
    return raw / name


def _csv_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    return [
        m
        for m in archive.infolist()
        if m.filename.endswith(".csv") and not m.filename.startswith("__MACOSX/")
    ]


def _tests_on_either_side_of_the_cut(raw: Path) -> tuple[set[int], set[int]]:
    """The test_ids of the April to June 2018 results, before and from 20 May 2018."""
    before, after = set(), set()
    with zipfile.ZipFile(raw / "dft_test_result_2018.zip") as archive:
        for m in _csv_members(archive):
            if "2018-04-01" not in m.filename:
                continue
            with archive.open(m) as f:
                f.readline()
                for line in f:
                    test_id, _, test_date, _ = line.split(b",", 3)
                    (before if test_date < CUT else after).add(int(test_id))
    return before, after


def count_year(raw: Path, year: int) -> dict[str, Counter]:
    """Items by (code, way) in one year's archive, with 2018 split at 20 May.

    The 2018 files run by quarter, so only the April to June items need their test's date, which
    comes from the 2018 results file.
    """
    counts: dict[str, Counter] = defaultdict(Counter)
    before: set[int] = set()
    after: set[int] = set()
    if year == FIRST_YEAR:
        before, after = _tests_on_either_side_of_the_cut(raw)
    with zipfile.ZipFile(_item_archive(raw, year)) as archive:
        for m in _csv_members(archive):
            with archive.open(m) as f:
                sep = b"|" if b"|" in f.readline() else b","
                for line in f:
                    test_id, code, way, _ = line.split(sep, 3)
                    key = (int(code), way.strip(b'"').decode())
                    if year > FIRST_YEAR:
                        period = str(year)
                    elif "2018-01-01" in m.filename:
                        period = BEFORE
                    elif "2018-04-01" not in m.filename:
                        period = PERIODS[0]
                    else:
                        t = int(test_id)
                        period = BEFORE if t in before else PERIODS[0] if t in after else UNMATCHED
                    counts[period][key] += 1
    return counts


def count_items(raw: Path, processes: int = 6) -> dict[str, Counter]:
    """Items by (code, way) per period, over every failure item from 2018 to 2025.

    Items carry no test result, so the counts are over all tests, aborted and abandoned included.
    """
    with Pool(processes) as pool:
        per_year = pool.map(partial(count_year, raw), range(FIRST_YEAR, LAST_YEAR + 1))
    counts: dict[str, Counter] = defaultdict(Counter)
    for c in per_year:
        for period, counter in c.items():
            counts[period].update(counter)
    return counts


def renumbered(codes: dict[int, Code], span: dict[int, list[int]]) -> list[tuple[int, int, str]]:
    """Pairs (old code, new code, rule) where the new code takes over the old one's defect.

    `span` holds the years each code is recorded in. Both rules require the same category and the
    same vehicle classes, and the old code to be last recorded in the year the new one is first
    recorded or the year before. Rule (i): the same short description, and either the same group
    or the same inspection-manual wording. Rule (ii): the same group and manual wording, when
    these two are the only codes in the lookup with that group, wording and category. Pairs come
    in the order the new code first appears.
    """
    late = [c for c in span if span[c][0] > FIRST_YEAR]
    early = [c for c in span if span[c][-1] < LAST_YEAR]
    cell = Counter((c.group, c.manual, c.category) for c in codes.values())
    pairs = []
    for new in late:
        for old in early:
            a, b = codes[old], codes[new]
            if (
                old == new
                or a.category != b.category
                or a.classes != b.classes
                or span[old][-1] not in (span[new][0] - 1, span[new][0])
            ):
                continue
            if a.short == b.short and (a.group == b.group or a.manual == b.manual):
                pairs.append((old, new, "i"))
            elif (a.group, a.manual) == (b.group, b.manual) and cell[
                (b.group, b.manual, b.category)
            ] == 2:
                pairs.append((old, new, "ii"))
    return sorted(pairs, key=lambda pair: (span[pair[1]][0], pair[1], pair[0]))


@dataclass
class Coverage:
    """What the rules make of the counts: every figure DATA.md reports, and the seeds."""

    span: dict[int, list[int]]  # years each code of the 2018 rules is recorded in, from 20 May 2018
    every: list[int]  # codes of the earlier rules recorded in every period
    pairs: list[tuple[int, int, str]]
    members: dict[int, list[int]]  # problem -> its codes, for the codes of the 2018 rules
    kept: dict[int, list[int]]  # kept problem -> its codes, the earlier-rules advisories included
    allowed: set[tuple[int, str]]  # entries the rules allow for the kept problems
    never: set[tuple[int, str]]  # of those, entries never recorded

    @property
    def problem(self) -> dict[int, int]:
        """Each kept code and the problem it belongs to."""
        return {c: p for p, cs in self.kept.items() for c in cs}

    @property
    def entries(self) -> list[tuple[int, str]]:
        """The entries of the year vector, in order: allowed and recorded."""
        return sorted(self.allowed - self.never)


def coverage(codes: dict[int, Code], counts: dict[str, Counter]) -> Coverage:
    """Apply the rules to the counts: join renumbered codes, keep what spans 2018 to 2025."""
    rules = {c for c, code in codes.items() if code.category != PRE_EU}
    earlier = set(codes) - rules
    periods_of: dict[int, set[str]] = defaultdict(set)
    for p in PERIODS:
        for c, _ in counts.get(p, {}):
            periods_of[c].add(p)
    every = sorted(c for c in earlier if len(periods_of[c]) == len(PERIODS))
    span = {c: sorted({YEAR_OF[p] for p in periods_of[c]}) for c in rules if periods_of[c]}
    pairs = renumbered(codes, span)
    problem = {c: c for c in span}
    for old, new, _ in pairs:
        problem[new] = problem[old]
    members: dict[int, list[int]] = defaultdict(list)
    for c, p in problem.items():
        members[p].append(c)
    kept = {
        p: sorted(cs)
        for p, cs in members.items()
        if min(span[c][0] for c in cs) == FIRST_YEAR and max(span[c][-1] for c in cs) == LAST_YEAR
    } | {c: [c] for c in every}
    allowed_entries = {
        (p, w) for p, cs in kept.items() for w in WAYS if any(allowed(codes[c], w) for c in cs)
    }
    seen = {(problem.get(c, c), w) for p in PERIODS for (c, w) in counts.get(p, {})}
    return Coverage(
        span=span,
        every=every,
        pairs=pairs,
        members=dict(members),
        kept=kept,
        allowed=allowed_entries,
        never={e for e in allowed_entries if e not in seen},
    )


def write_seeds(cov: Coverage, codes: dict[int, Code], out: Path) -> None:
    """Write `code_dictionary.csv` and `year_vector_entries.csv` into `out`."""
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "code_dictionary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rfr_id", "problem"])
        w.writerows(sorted(cov.problem.items()))
    with open(out / "year_vector_entries.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entry", "problem", "way", "classes"])
        for i, (p, way) in enumerate(cov.entries):
            w.writerow([i, p, way, " ".join(sorted(codes[p].classes, key=int))])


def main() -> None:
    raw, out = Path("data/raw"), Path("transform/seeds")
    codes = read_lookup(raw / "lookup.zip")
    cov = coverage(codes, count_items(raw))
    write_seeds(cov, codes, out)
    print(f"{len(cov.problem):,} codes in {len(cov.kept):,} problems, {len(cov.entries):,} entries")
    print(f"written to {out}/code_dictionary.csv and {out}/year_vector_entries.csv")


if __name__ == "__main__":
    main()
