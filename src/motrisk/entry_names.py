"""A dictionary of the year vector's entries in names people understand.

Each of the 4,821 entries is a problem recorded one way. The dictionary gives, for each: the way,
in words; the problem's code, the one used first, and the later code where the problem was
renumbered; its category under the 2018 rules; its descriptions; its group, by number and by the
path of group names from the top of the tree. Descriptions and the path are read from the lookup
for class 4 where the problem is listed for it, and otherwise for the lowest class listed; a group
number has the same name and parent in every class (DATA.md, "The lookup tables").

Run as a module from the repository's root, after the seeds exist:

    python -m motrisk.entry_names
"""

import csv
import io
import zipfile
from pathlib import Path

LOOKUP = Path("data/raw/lookup.zip")
SEEDS = Path("transform/seeds")
OUT = Path("data/processed/entry_dictionary.csv")
WAY_NAMES = {
    "F": "failure",
    "P": "failure put right at the station",
    "M": "minor defect",
    "A": "advisory",
}
COLUMNS = [
    "entry",
    "way",
    "way_name",
    "code",
    "later_code",
    "category",
    "description",
    "manual_description",
    "advisory_text",
    "group_id",
    "group_path",
    "classes",
]


def _read(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with archive.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter="|"))


def _seed(name: str) -> list[dict[str, str]]:
    with open(SEEDS / name, newline="") as f:
        return list(csv.DictReader(f))


def build() -> list[dict[str, str]]:
    """One row per entry, in entry order."""
    with zipfile.ZipFile(LOOKUP) as archive:
        details = _read(archive, "item_detail.csv")
        groups = _read(archive, "item_group.csv")
    detail = {(r["rfr_id"], r["test_class_id"]): r for r in details}
    group = {(r["test_item_id"], r["test_class_id"]): r for r in groups}

    later = {}
    for r in _seed("code_dictionary.csv"):
        if r["rfr_id"] != r["problem"]:
            later[r["problem"]] = r["rfr_id"]

    def path(group_id: str, cls: str) -> str:
        names = []
        while True:
            g = group[(group_id, cls)]
            if g["item_name"] == "Vehicle":
                break
            names.append(g["item_name"])
            group_id = g["parent_id"]
        return " > ".join(reversed(names))

    rows = []
    for e in _seed("year_vector_entries.csv"):
        classes = e["classes"].split()
        cls = "4" if "4" in classes else min(classes, key=int)
        d = detail[(e["problem"], cls)]
        rows.append(
            {
                "entry": e["entry"],
                "way": e["way"],
                "way_name": WAY_NAMES[e["way"]],
                "code": e["problem"],
                "later_code": later.get(e["problem"], ""),
                "category": d["rfr_deficiency_category"],
                "description": d["rfr_desc"].strip(),
                "manual_description": d["rfr_insp_manual_desc"].strip(),
                "advisory_text": d["rfr_advisory_text"].strip() if e["way"] == "A" else "",
                "group_id": d["test_item_id"],
                "group_path": path(d["test_item_id"], cls),
                "classes": e["classes"],
            }
        )
    return rows


def main() -> None:
    rows = build()
    with open(OUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows):,} entries to {OUT}")


if __name__ == "__main__":
    main()
