"""What the vehicle columns of the test results hold, year by year.

Establishes the figures under "The vehicle columns, cleaned" in DATA.md. Over the normal tests of
each year, aborted and abandoned ones removed, this counts: first-use dates that are blank, that
are 1 January 1971, which the guide says stands for an unknown date, and that fall after the test;
mileage that is blank, zero, written with a decimal point, or not a number; engine sizes that are
blank, zero or not a number; makes and models recorded as `UNCLASSIFIED`; makes not written in
capitals without surrounding spaces; and the tests per fuel code. Rows that do not split into as
many values as the header has columns are counted, blank rows among them, and skipped.

Each file is read the way `02_csv_quoting.py` and `06_csv_quoting_2018_2023.py` establish: a
double quote inside a value escaped with a backslash in 2018 to 2020 and 2024 to 2025, and doubled
in 2021; the `|`-separated files of 2022 and 2023 are split on the separator alone, quotes kept
as written. Those two results files are compressed with Deflate64, which Python's zipfile cannot
open, and are read through `motrisk.archives`. Reads the archives already in data/raw/. Run from
the repository root:

    python evidence/07_vehicle_columns.py
"""

import csv
import io
import zipfile
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

from motrisk.archives import open_member

RAW = Path("data/raw")
YEARS = range(2018, 2026)
UNKNOWN_FIRST_USE = "1971-01-01"
# The years whose results escape a double quote inside a value with a backslash.
BACKSLASH_YEARS = (2018, 2019, 2020, 2024, 2025)
PIPE_YEARS = (2022, 2023)


def archive_of(year: int) -> Path:
    name = f"dft_test_result_extracts_{year}.zip" if year >= 2024 else f"dft_test_result_{year}.zip"
    return RAW / name


def is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def scan(year: int, name: str) -> Counter:
    """Counts for one member."""
    c: Counter = Counter()
    with open_member(archive_of(year), name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        if year in PIPE_YEARS:
            rows = csv.reader(text, delimiter="|", quoting=csv.QUOTE_NONE)
        elif year in BACKSLASH_YEARS:
            rows = csv.reader(text, delimiter=",", escapechar="\\", doublequote=False)
        else:
            rows = csv.reader(text, delimiter=",")
        header = next(rows)
        col = {n: i for i, n in enumerate(header)}
        for r in rows:
            if len(r) != len(header):
                c["rows of the wrong width, blank rows included"] += 1
                continue
            if r[col["test_type"]] != "NT" or r[col["test_result"]] in ("ABR", "ABA"):
                continue
            c["normal tests"] += 1
            first_use, test_date = r[col["first_use_date"]], r[col["test_date"]]
            mileage, engine = r[col["test_mileage"]], r[col["cylinder_capacity"]]
            make, model = r[col["make"]], r[col["model"]]
            if not first_use:
                c["first use blank"] += 1
            elif first_use == UNKNOWN_FIRST_USE:
                c["first use 1971-01-01"] += 1
            elif first_use[:10] > test_date[:10]:
                c["first use after the test"] += 1
            if not mileage:
                c["mileage blank"] += 1
            elif not is_number(mileage):
                c["mileage not a number"] += 1
            elif float(mileage) == 0:
                c["mileage zero"] += 1
            elif "." in mileage:
                c["mileage with a decimal point"] += 1
            if not engine:
                c["engine size blank"] += 1
            elif not is_number(engine):
                c["engine size not a number"] += 1
            elif float(engine) == 0:
                c["engine size zero"] += 1
            if make == "UNCLASSIFIED":
                c["make UNCLASSIFIED"] += 1
            if model == "UNCLASSIFIED":
                c["model UNCLASSIFIED"] += 1
            if make != make.strip().upper():
                c["make not in capitals or with spaces"] += 1
            c[f"fuel {r[col['fuel_type']] or '(blank)'}"] += 1
    return c


def main() -> None:
    jobs = []
    for year in YEARS:
        with zipfile.ZipFile(archive_of(year)) as archive:
            for m in archive.infolist():
                if m.filename.endswith(".csv") and not m.filename.startswith("__MACOSX/"):
                    jobs.append((year, m.filename))
    with Pool(6) as pool:
        results = pool.starmap(scan, jobs)
    per_year: dict[int, Counter] = {}
    for (year, _), counts in zip(jobs, results, strict=True):
        per_year.setdefault(year, Counter()).update(counts)
    for year in YEARS:
        c = per_year[year]
        n = c["normal tests"]
        print(f"{year}: {n:,} normal tests")
        for key in sorted(k for k in c if k != "normal tests" and not k.startswith("fuel ")):
            print(f"  {key}: {c[key]:,} ({100 * c[key] / n:.3f}%)")
        fuels = ", ".join(f"{k[5:]} {v:,}" for k, v in c.most_common() if k.startswith("fuel "))
        print(f"  fuel codes: {fuels}")


if __name__ == "__main__":
    main()
