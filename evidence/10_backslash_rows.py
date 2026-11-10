"""The rows of the 2018 to 2020 results that Python's csv and DuckDB split differently, and why.

`07_vehicle_columns.py` counts the rows of the results that do not split into as many values as
the header has columns, reading with Python's csv and a backslash as the escape, as 2018 to 2020
need. This finds those rows in the CSVs in data/extracted/ and prints each one as written, then
reads each with DuckDB, with the options `09_csv_from_azure.py` uses, and prints its make and
model and how many values DuckDB finds. Python's csv takes a backslash before the separator as
escaping it, and joins the two values on either side; DuckDB applies the escape only inside double
quotes, so a backslash outside them is part of the value. Reads data/extracted/, written by
`python src/motrisk/extract.py local`. Run from the repository root:

    python evidence/10_backslash_rows.py
"""

import csv
from multiprocessing import Pool
from pathlib import Path

import duckdb

EXTRACTED = Path("data/extracted")
YEARS = (2018, 2019, 2020)
DUCKDB_OPTIONS = "delim = ',', quote = '\"', escape = '\\', header = true, all_varchar = true"


def wrong_width(path: Path) -> list[tuple[Path, int, str]]:
    """The rows of path that Python's csv does not split into as many values as the header has."""
    found = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = csv.reader(f, delimiter=",", escapechar="\\", doublequote=False)
        header = next(rows)
        for r in rows:
            if len(r) != len(header):
                found.append((path, rows.line_num, r[0]))
    return found


def main() -> None:
    files = sorted(p for y in YEARS for p in (EXTRACTED / f"dft_test_result_{y}").glob("*.csv"))
    with Pool(6) as pool:
        found = [row for rows in pool.map(wrong_width, files) for row in rows]

    con = duckdb.connect()
    for path, line, test_id in found:
        with open(path, encoding="utf-8") as f:
            written = next(text for n, text in enumerate(f, start=1) if n == line).rstrip("\n")
        result = con.execute(
            f"SELECT * FROM read_csv(?, {DUCKDB_OPTIONS}) WHERE test_id = ?", [str(path), test_id]
        )
        [row] = result.fetchall()
        value = dict(zip([c[0] for c in result.description], row, strict=True))
        print(f"{path.parent.name}/{path.name}, line {line:,}:")
        print(f"  as written: {written}")
        print(f"  DuckDB: {len(row)} values, make {value['make']!r}, model {value['model']!r}")
    print(f"rows Python's csv splits wrongly: {len(found)}")


if __name__ == "__main__":
    main()
