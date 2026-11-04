"""How values are quoted in the files of 2018 to 2023.

Establishes the quoting of the older layouts described under "The files" in DATA.md, as
`02_csv_quoting.py` does for 2024 and 2025. The 2018 to 2021 files are comma-separated, and the
2021 ones enclose most values in double quotes; the 2022 and 2023 files are `|`-separated.

For every CSV in the archives of 2018 to 2023, this counts the rows, the rows holding a double
quote, the rows that splitting on the separator alone gets wrong, the rows holding a backslash
before a double quote, and the rows that do not split into as many values as the header has
columns under each of two readings: double quotes as quote characters with a quote inside a value
doubled, the CSV standard, and with it escaped by a backslash instead, the reading 2024 and 2025
need. It names the columns whose values contain the separator, under the standard reading. The
2022 and 2023 results, compressed with Deflate64, which Python's zipfile cannot open, are read
through `motrisk.archives`. Reads the archives already in data/raw/; nothing is fetched. Run from
the repository root:

    python evidence/06_csv_quoting_2018_2023.py
"""

import csv
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path

from motrisk.archives import open_member

RAW = Path("data/raw")
YEARS = range(2018, 2024)
QUOTE = b'"'
ESCAPED_QUOTE = b'\\"'


@dataclass
class Counts:
    rows: int = 0
    quoted: int = 0
    split_wrongly: int = 0
    escaped: int = 0
    wrong_width_standard: int = 0
    wrong_width_backslash: int = 0
    separator_inside: Counter = field(default_factory=Counter)

    def add(self, other: "Counts") -> None:
        self.rows += other.rows
        self.quoted += other.quoted
        self.split_wrongly += other.split_wrongly
        self.escaped += other.escaped
        self.wrong_width_standard += other.wrong_width_standard
        self.wrong_width_backslash += other.wrong_width_backslash
        self.separator_inside.update(other.separator_inside)


def scan(path: Path, name: str) -> Counts:
    """Counts for one member."""
    counts = Counts()
    with open_member(path, name) as f:
        first = f.readline().decode("utf-8-sig").rstrip("\r\n")
        sep = "|" if first.count("|") > first.count(",") else ","
        header = next(csv.reader([first], delimiter=sep))
        for line in f:
            counts.rows += 1
            if QUOTE not in line:
                continue
            counts.quoted += 1
            if ESCAPED_QUOTE in line:
                counts.escaped += 1
            text = line.decode("utf-8", "replace").rstrip("\r\n")
            if text.count(sep) + 1 != len(header):
                counts.split_wrongly += 1
            standard = next(csv.reader([text], delimiter=sep))
            backslash = next(csv.reader([text], delimiter=sep, escapechar="\\", doublequote=False))
            if len(backslash) != len(header):
                counts.wrong_width_backslash += 1
            if len(standard) != len(header):
                counts.wrong_width_standard += 1
                continue
            for column, value in zip(header, standard, strict=True):
                if sep in value:
                    counts.separator_inside[column] += 1
    return counts


def members(year: int) -> list[tuple[Path, str]]:
    found = []
    for kind in ("result", "item"):
        path = RAW / f"dft_test_{kind}_{year}.zip"
        with zipfile.ZipFile(path) as archive:
            for m in archive.infolist():
                if m.filename.endswith(".csv") and not m.filename.startswith("__MACOSX/"):
                    found.append((path, m.filename))
    return found


def describe(counts: Counts) -> str:
    inside = ", ".join(f"{k} {v:,}" for k, v in counts.separator_inside.most_common()) or "none"
    return (
        f"{counts.rows:,} rows, {counts.quoted:,} holding a double quote; "
        f"{counts.split_wrongly:,} split wrongly on the separator alone; "
        f"{counts.escaped:,} with a backslash before a quote; wrong width, standard reading "
        f"{counts.wrong_width_standard:,}, backslash reading {counts.wrong_width_backslash:,}; "
        f"separator inside a value: {inside}"
    )


def main() -> None:
    jobs = [job for year in YEARS for job in members(year)]
    with Pool(6) as pool:
        results = pool.starmap(scan, jobs)
    totals: dict[str, Counts] = {}
    for (path, _), counts in zip(jobs, results, strict=True):
        totals.setdefault(path.name, Counts()).add(counts)
    for name, counts in totals.items():
        print(f"{name}: {describe(counts)}")


if __name__ == "__main__":
    main()
