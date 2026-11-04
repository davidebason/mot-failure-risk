"""How values are quoted and escaped in the comma-separated files.

Establishes the quoting described under "The files" in DATA.md. From 2024 the files are
comma-separated. A value that itself contains a comma, such as the model SERIES 1, 80 INCH, is
enclosed in double quotes, and a double quote inside such a value, an inch mark as in the model
SWB 88", is escaped with a backslash rather than doubled. A reader that ignores the quotes splits a
row into one column too many; a reader that expects doubled quotes misreads the inch marks.

For every monthly CSV inside the 2024 and 2025 extracts, this counts the rows, the rows holding a
double quote, the rows that splitting on commas alone gets wrong, the rows holding a backslash
before a double quote, the rows whose double quotes do not pair up once those are set aside, and
the rows that do not split into as many values as the header has columns when read with the double
quote as quote character and the backslash as escape. It names the columns whose values contain a
comma, and gives the line of the first row holding a double quote, the header being line 1. Reads
the archives already in data/raw/; nothing is fetched. Run from the repository root:

    python evidence/02_csv_quoting.py
"""

import csv
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

RAW = Path("data/raw")
ARCHIVES = [
    "dft_test_result_extracts_2024.zip",
    "dft_test_item_extracts_2024.zip",
    "dft_test_result_extracts_2025.zip",
    "dft_test_item_extracts_2025.zip",
]
QUOTE = b'"'
ESCAPED_QUOTE = b'\\"'


@dataclass
class Counts:
    rows: int = 0
    quoted: int = 0
    split_wrongly: int = 0
    escaped: int = 0
    unpaired: int = 0
    wrong_width: int = 0
    first_quoted_line: int | None = None
    comma_inside: Counter = field(default_factory=Counter)

    def add(self, other: "Counts") -> None:
        self.rows += other.rows
        self.quoted += other.quoted
        self.split_wrongly += other.split_wrongly
        self.escaped += other.escaped
        self.unpaired += other.unpaired
        self.wrong_width += other.wrong_width
        self.comma_inside.update(other.comma_inside)


def scan(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> Counts:
    counts = Counts()
    with archive.open(member) as f:
        header = f.readline().decode("utf-8-sig").rstrip("\r\n").split(",")
        # The header is line 1, so the first data row is line 2.
        for line_number, line in enumerate(f, start=2):
            counts.rows += 1
            if QUOTE not in line:
                continue
            counts.quoted += 1
            if counts.first_quoted_line is None:
                counts.first_quoted_line = line_number
            if ESCAPED_QUOTE in line:
                counts.escaped += 1
            if (line.count(QUOTE) - line.count(ESCAPED_QUOTE)) % 2:
                counts.unpaired += 1
            text = line.decode("utf-8", "replace").rstrip("\r\n")
            if text.count(",") + 1 != len(header):
                counts.split_wrongly += 1
            values = next(csv.reader([text], escapechar="\\", doublequote=False))
            if len(values) != len(header):
                counts.wrong_width += 1
                continue
            for name, value in zip(header, values, strict=True):
                if "," in value:
                    counts.comma_inside[name] += 1
    return counts


def describe(label: str, counts: Counts) -> str:
    inside = ", ".join(f"{k} {v:,}" for k, v in counts.comma_inside.most_common()) or "none"
    first = f", first on line {counts.first_quoted_line:,}" if counts.first_quoted_line else ""
    return (
        f"{label}: {counts.rows:,} rows, {counts.quoted:,} holding a double quote{first}; "
        f"{counts.split_wrongly:,} split wrongly on commas alone; "
        f"{counts.escaped:,} with a backslash-escaped quote; {counts.unpaired:,} unpaired; "
        f"{counts.wrong_width:,} of the wrong width when read; comma inside a value: {inside}"
    )


def main() -> None:
    for name in ARCHIVES:
        print(name)
        total = Counts()
        with zipfile.ZipFile(RAW / name) as archive:
            members = sorted(
                (m for m in archive.infolist() if m.filename.endswith(".csv")),
                key=lambda m: m.filename,
            )
            for member in members:
                counts = scan(archive, member)
                print("  " + describe(member.filename.rsplit("/", 1)[-1], counts), flush=True)
                total.add(counts)
        print("  " + describe("all months", total), flush=True)


if __name__ == "__main__":
    main()
