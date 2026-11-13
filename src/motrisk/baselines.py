"""Score the baselines, Repeat and Most popular, on every test year, before any model is trained.

Run from the repository's root as `python src/motrisk/baselines.py`, once data/training_rows/
holds the training table, one Parquet file per target year, and data/processed/most_popular.csv
the lists the dbt model most_popular builds on the virtual machine. Writes
data/processed/baseline_counts.csv: for each baseline, test year and entry, the true positives,
false positives and false negatives (DATA.md, "The baselines").

- Repeat predicts, for each row, the entries of its previous slot.
- Most popular predicts, for every row, the same list: the k entries on the most slots starting
  in the year before the test year.

An entry is scored only on rows of the classes it is listed for, as the models will be, so that
the three are counted on the same ground. For every test year and entry, each baseline's true
positives plus false negatives must equal the ones of the labels, counted on their own by
`label_ones`; the run stops if they do not.

The list functions, list_intersect, list_filter and list_contains, and the lambda in list_filter,
are DuckDB's; PostgreSQL would unnest both lists and join them.
"""

import csv
from pathlib import Path

import duckdb

ROWS = Path("data/training_rows")
LISTS = Path("data/processed/most_popular.csv")
ENTRIES = Path("transform/seeds/year_vector_entries.csv")
OUT = Path("data/processed/baseline_counts.csv")
TEST_YEARS = range(2020, 2026)


def connect(entries: Path = ENTRIES, memory_limit: str = "5GB") -> duckdb.DuckDBPyConnection:
    """A DuckDB connection holding entry_classes: one row per entry and class it is listed for."""
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{memory_limit}'")
    con.execute("SET preserve_insertion_order = false")
    con.execute(
        f"""CREATE TABLE entry_classes AS
            SELECT entry, CAST(unnest(string_split(classes, ' ')) AS INTEGER) AS test_class_id
            FROM read_csv('{entries}', header = true)"""
    )
    return con


def label_ones(con, rows: Path) -> dict[int, int]:
    """For each entry, the rows of rows whose label holds it, on rows of its classes only."""
    return dict(
        con.execute(
            f"""SELECT u.entry, count(*)
                FROM (SELECT test_class_id, unnest(label_entries) AS entry
                      FROM read_parquet('{rows}')) AS u
                WHERE EXISTS (SELECT 1 FROM entry_classes AS c
                              WHERE c.entry = u.entry AND c.test_class_id = u.test_class_id)
                GROUP BY u.entry"""
        ).fetchall()
    )


def repeat(con, rows: Path) -> dict[int, tuple[int, int, int]]:
    """Repeat's true positives, false positives and false negatives for each entry, on rows.

    In each row, an entry in both lists is a true positive, one only in the previous slot's a
    false positive, one only in the label a false negative.
    """
    found = con.execute(
        f"""WITH r AS (
                SELECT test_class_id, previous_entries AS p, label_entries AS l
                FROM read_parquet('{rows}')
            ),
            kinds AS (
                SELECT test_class_id, unnest(list_intersect(p, l)) AS entry, 'tp' AS kind
                FROM r
                UNION ALL
                SELECT test_class_id,
                       unnest(list_filter(p, lambda x: NOT list_contains(l, x))), 'fp'
                FROM r
                UNION ALL
                SELECT test_class_id,
                       unnest(list_filter(l, lambda x: NOT list_contains(p, x))), 'fn'
                FROM r
            )
            SELECT k.entry,
                   count(*) FILTER (WHERE k.kind = 'tp'),
                   count(*) FILTER (WHERE k.kind = 'fp'),
                   count(*) FILTER (WHERE k.kind = 'fn')
            FROM kinds AS k
            INNER JOIN entry_classes AS c
                ON c.entry = k.entry AND c.test_class_id = k.test_class_id
            GROUP BY k.entry"""
    ).fetchall()
    return {entry: (tp, fp, fn) for entry, tp, fp, fn in found}


def most_popular(con, rows: Path, listed: list[int]) -> dict[int, tuple[int, int, int]]:
    """Most popular's true positives, false positives and false negatives for each entry, on rows.

    Every row is predicted the entries of listed. A listed entry is a true positive on each row of
    its classes whose label holds it and a false positive on every other row of its classes; an
    entry not listed is a false negative wherever a label holds it.
    """
    rows_of_classes = dict(
        con.execute(
            f"""SELECT c.entry, count(*)
                FROM read_parquet('{rows}') AS r
                INNER JOIN entry_classes AS c ON c.test_class_id = r.test_class_id
                WHERE c.entry IN (SELECT unnest(?::INTEGER[]))
                GROUP BY c.entry""",
            [listed],
        ).fetchall()
    )
    counts = {}
    for entry, ones in label_ones(con, rows).items():
        counts[entry] = (ones, 0, 0) if entry in listed else (0, 0, ones)
    for entry in listed:
        tp = counts.get(entry, (0, 0, 0))[0]
        counts[entry] = (tp, rows_of_classes.get(entry, 0) - tp, 0)
    return counts


def lists(path: Path = LISTS) -> dict[int, list[int]]:
    """Most popular's list for each year, in rank order, from the file the VM's build wrote."""
    by_year: dict[int, list[tuple[int, int]]] = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            by_year.setdefault(int(r["list_year"]), []).append(
                (int(r["list_rank"]), int(r["entry"]))
            )
    return {year: [e for _, e in sorted(ranked)] for year, ranked in by_year.items()}


def check(name: str, year: int, counts: dict, ones: dict) -> None:
    """Stop unless each entry's true positives plus false negatives are the labels' ones."""
    wrong = [
        e
        for e in set(counts) | set(ones)
        if counts.get(e, (0, 0, 0))[0] + counts.get(e, (0, 0, 0))[2] != ones.get(e, 0)
    ]
    if wrong:
        raise SystemExit(f"{name} {year}: true positives plus false negatives differ for {wrong}")


def main() -> None:
    con = connect()
    entries = [e for (e,) in con.execute("SELECT DISTINCT entry FROM entry_classes").fetchall()]
    listed = lists()
    with open(OUT, "w", newline="") as f:
        out = csv.writer(f, lineterminator="\n")
        out.writerow(["baseline", "test_year", "entry", "tp", "fp", "fn"])
        for year in TEST_YEARS:
            rows = ROWS / f"{year}.parquet"
            ones = label_ones(con, rows)
            scored = {
                "repeat": repeat(con, rows),
                "most_popular": most_popular(con, rows, listed[year - 1]),
            }
            for name, counts in scored.items():
                check(name, year, counts, ones)
                for e in sorted(entries):
                    out.writerow([name, year, e, *counts.get(e, (0, 0, 0))])
                tp, fp, fn = (sum(c[i] for c in counts.values()) for i in range(3))
                print(
                    f"{name} {year}: tp {tp:,} fp {fp:,} fn {fn:,} "
                    f"precision {tp / (tp + fp):.4f} recall {tp / (tp + fn):.4f}",
                    flush=True,
                )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
