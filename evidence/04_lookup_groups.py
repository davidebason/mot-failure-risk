"""How the defect codes of the lookup tables sit in the tree of defect groups.

Establishes the figures under "The lookup tables" in DATA.md on codes and groups. `item_detail`
lists each defect code once per vehicle class, with the group it belongs to, `test_item_id`;
`item_group` lists each group once per class, with its parent, up to `Vehicle` at the root. This
counts the code numbers of the 2018 rules and of the earlier ones, checks that every code's group is
listed for its class, and, for the codes listed in more than one class, whether the group directly
above the code and the group at the top of its path are the same in every class, and whether any
code is listed both for motorcycles and for another class. It then counts the
groups directly above the codes of the 2018 rules, their names, the names shared by several groups,
and how many groups lie between a code and `Vehicle`. Reads data/raw/lookup.zip; nothing is
fetched. Run from the repository root:

    python evidence/04_lookup_groups.py
"""

import csv
import io
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

LOOKUPS = Path("data/raw/lookup.zip")
PRE_EU = "Pre-EU Directive"
ROOT = "0"


def read(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with archive.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter="|"))


def path_to_root(
    groups: dict[tuple[str, str], dict[str, str]], group: str, cls: str
) -> list[dict[str, str]]:
    """The groups from `group` up to, but not including, the root `Vehicle`, in class `cls`."""
    path = []
    while group != ROOT:
        row = groups[(group, cls)]
        path.append(row)
        group = row["parent_id"]
    return path


def main() -> None:
    with zipfile.ZipFile(LOOKUPS) as archive:
        detail = read(archive, "item_detail.csv")
        group_rows = read(archive, "item_group.csv")
    groups = {(g["test_item_id"], g["test_class_id"]): g for g in group_rows}

    new = {d["rfr_id"] for d in detail if d["rfr_deficiency_category"] != PRE_EU}
    old = {d["rfr_id"] for d in detail if d["rfr_deficiency_category"] == PRE_EU}
    print(f"code numbers: {len(new):,} of the 2018 rules, {len(old):,} of the earlier rules,")
    print(f"  {len(new & old)} used by both")

    missing = Counter(
        "2018 rules" if d["rfr_deficiency_category"] != PRE_EU else "earlier rules"
        for d in detail
        if (d["test_item_id"], d["test_class_id"]) not in groups
    )
    print(f"code-and-class rows whose group is not listed for that class: {dict(missing) or 0}")

    # A group number that means a different group in another class would make the number unsafe
    # to use across classes.
    by_number = defaultdict(set)
    for g in group_rows:
        by_number[g["test_item_id"]].add((g["item_name"].lower(), g["parent_id"]))
    differs = sum(len(v) > 1 for v in by_number.values())
    print(f"group numbers with another name or parent in another class: {differs}")

    rules = [d for d in detail if d["rfr_id"] in new]
    direct, top, steps = defaultdict(set), defaultdict(set), defaultdict(list)
    for d in rules:
        path = path_to_root(groups, d["test_item_id"], d["test_class_id"])
        direct[d["rfr_id"]].add((d["test_item_id"], path[0]["item_name"].lower()))
        top[d["rfr_id"]].add(path[-1]["item_name"].lower())
        steps[d["test_class_id"]].append(len(path))
    listed = defaultdict(set)
    for d in rules:
        listed[d["rfr_id"]].add(d["test_class_id"])
    both = sum(1 for cs in listed.values() if cs & {"1", "2"} and cs - {"1", "2"})
    only_moto = sum(1 for cs in listed.values() if cs <= {"1", "2"})
    print(
        f"codes of the 2018 rules listed only for motorcycles, classes 1 and 2: {only_moto}; "
        f"for motorcycles and another class: {both}"
    )
    classes = Counter(d["rfr_id"] for d in rules)
    several = [c for c, n in classes.items() if n > 1]
    number_differs = sum(len({n for n, _ in direct[c]}) > 1 for c in several)
    name_differs = sum(len({m for _, m in direct[c]}) > 1 for c in several)
    top_differs = sum(len(top[c]) > 1 for c in several)
    print(f"codes of the 2018 rules listed in more than one class: {len(several):,}")
    print(f"  direct group number differs between classes: {number_differs}")
    print(f"  direct group name differs between classes: {name_differs}")
    print(f"  top group name differs between classes: {top_differs}")

    numbers = {n for c in new for n, _ in direct[c]}
    names_of = defaultdict(set)
    for c in new:
        for n, m in direct[c]:
            names_of[m].add(n)
    shared = {m: ns for m, ns in names_of.items() if len(ns) > 1}
    widest = max(len(ns) for ns in shared.values())
    most = sorted(m for m, ns in shared.items() if len(ns) == widest)
    print(
        f"groups directly above a code of the 2018 rules: {len(numbers)}, carrying "
        f"{len(names_of)} names; {len(shared)} names belong to more than one group"
    )
    print(f"  the names on the most groups, {widest} each: {', '.join(most)}")
    for cls in sorted(steps, key=int):
        s = steps[cls]
        print(f"  class {cls}: {min(s)} to {max(s)} groups between a code and Vehicle")


if __name__ == "__main__":
    main()
