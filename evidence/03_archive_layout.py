"""What is inside each archive downloaded into data/raw/.

Establishes the layout of the files from 2018 on given under "The files" in DATA.md, from the copies
in data/raw/ rather than over HTTP: for every ZIP, the members that carry data, how each is
compressed, its size uncompressed, its separator and header, and which columns of its first data row
are enclosed in double quotes. Folder entries and the `__MACOSX/` entries some archives carry are
counted but hold no data. Members compressed with Deflate64, which Python's zipfile cannot open,
are read through `motrisk.archives`. Run from the repository root:

    python evidence/03_archive_layout.py
"""

import re
import zipfile
from collections import defaultdict
from pathlib import Path

from motrisk.archives import open_member

RAW = Path("data/raw")
# ZIP compression methods by their number in the ZIP format specification.
METHODS = {0: "stored", 8: "deflate", 9: "Deflate64"}


def year_and_name(path: Path) -> tuple[int, str]:
    found = re.search(r"\d{4}", path.name)
    return (int(found.group()) if found else 0, path.name)


def first_lines(path: Path, member: zipfile.ZipInfo) -> tuple[str, str]:
    """The header and the first data row of a member, Deflate64 included."""
    with open_member(path, member.filename) as f:
        header = f.readline().decode("utf-8-sig").rstrip("\r\n")
        row = f.readline().decode("utf-8", "replace").rstrip("\r\n")
    return header, row


def describe(header: str, row: str) -> str:
    sep = "|" if header.count("|") > header.count(",") else ","
    names = [name.strip('"') for name in header.split(sep)]
    values = row.split(sep)
    if len(values) != len(names):
        quoted = "first row has a separator inside a value"
    else:
        inside = [n for n, v in zip(names, values, strict=True) if v.startswith('"')]
        quoted = ", ".join(inside) if inside else "none"
    header_quoted = "yes" if header.startswith('"') else "no"
    return (
        f"separator '{sep}', {len(names)} columns: {', '.join(names)}; "
        f"header in quotes: {header_quoted}; quoted in the first row: {quoted}"
    )


def main() -> None:
    for path in sorted(RAW.glob("*.zip"), key=year_and_name):
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            data = [m for m in entries if not m.is_dir() and not m.filename.startswith("__MACOSX/")]
            print(
                f"{path.name}: {len(data)} members carrying data, "
                f"{len(entries) - len(data)} folder or __MACOSX entries"
            )
            # Members that share a compression method and a layout are reported together.
            groups: dict[str, list[zipfile.ZipInfo]] = defaultdict(list)
            for m in data:
                layout = describe(*first_lines(path, m))
                groups[f"{METHODS.get(m.compress_type, m.compress_type)}; {layout}"].append(m)
            for key, members in groups.items():
                sizes = [m.file_size / 1e6 for m in members]
                names = sorted(m.filename for m in members)
                print(
                    f"  {len(members)} members, {min(sizes):,.0f} to {max(sizes):,.0f} MB "
                    f"uncompressed, {names[0]} to {names[-1]}"
                )
                print(f"    {key}")


if __name__ == "__main__":
    main()
