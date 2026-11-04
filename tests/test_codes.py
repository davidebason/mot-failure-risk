"""The rules that decide which codes the year vector keeps, on toy codes and counts."""

from collections import Counter

from motrisk.codes import PERIODS, Code, allowed, coverage, renumbered

CARS = {"3", "4", "5", "7"}


def code(category="Major", group="g1", short="not working", manual="lamp inoperative", **kw):
    return Code(
        category, group, short, manual, kw.get("advisory", False), set(kw.get("classes", CARS))
    )


def counts_for(recorded: dict[tuple[int, str], list[int]]) -> dict[str, Counter]:
    """Counts with one item for each (code, way) in each year it is listed for."""
    counts: dict[str, Counter] = {p: Counter() for p in PERIODS}
    for key, years in recorded.items():
        for p in PERIODS:
            if int(p[:4]) in years:
                counts[p][key] += 1
    return counts


def test_the_rules_fix_how_a_code_can_be_recorded() -> None:
    major, minor = code("Major"), code("Minor")
    assert allowed(major, "F") and allowed(major, "P") and not allowed(major, "M")
    assert allowed(minor, "M") and not allowed(minor, "F") and not allowed(minor, "P")
    assert not allowed(major, "A") and allowed(code("Major", advisory=True), "A")
    earlier = code("Pre-EU Directive", advisory=True)
    assert allowed(earlier, "A") and not allowed(earlier, "F")


def test_a_renamed_code_in_the_same_group_is_paired() -> None:
    codes = {1: code(), 2: code()}
    span = {1: [2018, 2019, 2020, 2021], 2: [2021, 2022, 2023, 2024, 2025]}
    assert renumbered(codes, span) == [(1, 2, "i")]


def test_a_pair_needs_the_same_category_classes_and_no_gap() -> None:
    span = {1: [2018, 2019], 2: [2021, 2025]}
    assert renumbered({1: code(), 2: code()}, span) == []  # two years apart
    span = {1: [2018, 2020], 2: [2021, 2025]}
    assert renumbered({1: code(), 2: code("Minor")}, span) == []
    assert renumbered({1: code(), 2: code(classes={"1", "2"})}, span) == []


def test_a_new_description_is_paired_only_when_the_two_codes_are_alone() -> None:
    span = {1: [2018, 2023], 2: [2023, 2025]}
    alone = {1: code(short="not tested"), 2: code(short="unable to be tested")}
    assert renumbered(alone, span) == [(1, 2, "ii")]
    crowded = alone | {3: code(short="incorrectly positioned")}
    assert renumbered(crowded, span | {3: [2018, 2025]}) == []


def test_coverage_joins_pairs_keeps_full_spans_and_lists_entries() -> None:
    every = list(range(2018, 2026))
    codes = {
        1: code(advisory=True),  # renumbered in 2021 to code 2
        2: code(advisory=True),
        3: code("Minor", group="g2", short="loose", manual="x"),  # recorded every year but 2020
        4: code(group="g3", short="binding", manual="y"),  # first recorded in 2019: dropped
        9: code("Pre-EU Directive", group="g0", short="nail in tyre", manual="z"),
    }
    recorded = {
        (1, "F"): [2018, 2019, 2020, 2021],
        (2, "F"): [2021, 2022, 2023, 2024, 2025],
        (2, "A"): [2024],
        (3, "M"): [y for y in every if y != 2020],
        (4, "F"): every[1:],
        (9, "A"): every,
    }
    cov = coverage(codes, counts_for(recorded))
    assert cov.pairs == [(1, 2, "i")]
    assert cov.problem == {1: 1, 2: 1, 3: 3, 9: 9}
    assert cov.never == {(1, "P")}
    assert cov.entries == [(1, "A"), (1, "F"), (3, "M"), (9, "A")]
