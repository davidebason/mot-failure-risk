"""What each published MOT file is: its size, how it is compressed, and what its first lines say.

Establishes the figures quoted under "Sources" in DATA.md: the layout of each kind of file, the size
of every file from 2018 on, and the row and code counts of the lookup tables. Nothing is downloaded
in full. A ZIP keeps its index at the end of the file, so a handful of HTTP range requests is enough
to list its members and read the first lines of each; a gzip file is read from its first 64 KB.
Only the lookup tables, under 1 MB, are fetched whole. Run from the repository root:

    python evidence/01_source_files.py
"""

import csv
import http.client
import io
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from collections import Counter

DVSA = "https://edh-dvsa-data-gov-uk-files-prod.s3.eu-west-1.amazonaws.com"
DFT = "https://data.dft.gov.uk/anonymised-mot-test/test_data"

# One file per layout the publishers have used, results and failure items side by side.
FILES = [
    ("2025 results, monthly extracts", f"{DVSA}/dft_test_result_extracts_2025.zip"),
    ("2025 failure items, monthly extracts", f"{DVSA}/dft_test_item_extracts_2025.zip"),
    ("2024 results", f"{DVSA}/MOT+testing+data+results+(2024).zip"),
    ("2024 failure items", f"{DVSA}/MOT+Testing+data+failure+item+(2024).zip"),
    ("2023 results", f"{DVSA}/dft_test_result_2023.zip"),
    ("2023 failure items", f"{DVSA}/dft_test_item_2023.zip"),
    ("2016 results", f"{DFT}/test_result_2016.txt.gz"),
    ("2016 failure items", f"{DFT}/test_item_2016.txt.gz"),
]
LOOKUPS = f"{DVSA}/lookup.zip"

# Every file from 2018 on, both releases of 2024 included: results, then failure items.
YEARS = [
    ("2018", f"{DFT}/dft_test_result_2018.zip", f"{DFT}/dft_test_item_2018.zip"),
    ("2019", f"{DFT}/dft_test_result_2019.zip", f"{DFT}/dft_test_item_2019.zip"),
    ("2020", f"{DFT}/dft_test_result_2020.zip", f"{DFT}/dft_test_item_2020.zip"),
    ("2021", f"{DFT}/dft_test_result_2021.zip", f"{DFT}/dft_test_item_2021.zip"),
    ("2022", f"{DVSA}/dft_test_result_2022.zip", f"{DVSA}/dft_test_item_2022.zip"),
    ("2023", f"{DVSA}/dft_test_result_2023.zip", f"{DVSA}/dft_test_item_2023.zip"),
    (
        "2024, first release",
        f"{DVSA}/MOT+testing+data+results+(2024).zip",
        f"{DVSA}/MOT+Testing+data+failure+item+(2024).zip",
    ),
    (
        "2024, extracts",
        f"{DVSA}/dft_test_result_extracts_2024.zip",
        f"{DVSA}/dft_test_item_extracts_2024.zip",
    ),
    (
        "2025, extracts",
        f"{DVSA}/dft_test_result_extracts_2025.zip",
        f"{DVSA}/dft_test_item_extracts_2025.zip",
    ),
]

# The vehicle class whose defect codes are broken down by severity: cars and light vans.
CARS = "4"

# ZIP compression methods by their number in the ZIP format specification.
METHODS = {0: "stored", 8: "deflate", 9: "deflate64", 12: "bzip2", 14: "lzma"}
FIRST_LINES = 2
ATTEMPTS = 4
# Seconds a request may wait for the server before it counts as dropped and is retried.
TIMEOUT = 60


def with_retries(action):
    """Run action, and run it again if the connection drops or stalls: both servers sometimes
    close one without replying. The fourth failure is raised."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return action()
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError):
            if attempt == ATTEMPTS:
                raise
            time.sleep(5 * attempt)


def remote_size(url: str) -> int:
    """Size in bytes of the file at url, without downloading it.

    A one-byte range request rather than HEAD, which the DfT server refuses. Where ranges are
    honoured the size is the number after the slash in Content-Range, "bytes 0-0/1234567"; the DfT
    server ignores them and starts sending the whole file, so the size is its Content-Length and
    the connection is closed before the body is read.
    """
    first_byte = urllib.request.Request(url, headers={"Range": "bytes=0-0"})

    def read_size() -> int:
        with urllib.request.urlopen(first_byte, timeout=TIMEOUT) as response:
            content_range = response.headers["Content-Range"]
            if content_range:
                return int(content_range.rsplit("/", 1)[1])
            return int(response.headers["Content-Length"])

    return with_retries(read_size)


class RemoteFile(io.RawIOBase):
    """A read-only, seekable file over HTTP, fetching only the byte ranges that are read."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.pos = 0
        self.size = remote_size(url)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        start = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = start + offset
        return self.pos

    def readinto(self, buffer) -> int:
        n = min(len(buffer), self.size - self.pos)
        if n <= 0:
            return 0
        byte_range = {"Range": f"bytes={self.pos}-{self.pos + n - 1}"}

        def read_range() -> bytes:
            request = urllib.request.Request(self.url, headers=byte_range)
            with urllib.request.urlopen(request, timeout=TIMEOUT) as r:
                return r.read()

        data = with_retries(read_range)
        buffer[: len(data)] = data
        self.pos += len(data)
        return len(data)


def mb(n_bytes: int) -> str:
    return f"{n_bytes / 1e6:,.0f} MB"


def describe_zip(url: str) -> None:
    remote = RemoteFile(url)
    archive = zipfile.ZipFile(io.BufferedReader(remote, buffer_size=1 << 16))
    # A ZIP made on a Mac also holds folder entries and __MACOSX/ metadata, which carry no data.
    members = sorted(
        (
            m
            for m in archive.infolist()
            if not m.is_dir() and not m.filename.startswith("__MACOSX/")
        ),
        key=lambda m: m.filename,
    )
    other = len(archive.infolist()) - len(members)
    print(f"  ZIP, {mb(remote.size)}, {len(members)} data file(s) and {other} other entries")
    for m in members:
        method = METHODS.get(m.compress_type, f"method {m.compress_type}")
        print(f"    {m.filename}: {method}, {mb(m.compress_size)} -> {mb(m.file_size)}")
    first = members[0]
    try:
        with archive.open(first) as f:
            lines = [
                f.readline().decode("utf-8", "replace").rstrip("\r\n") for _ in range(FIRST_LINES)
            ]
    except NotImplementedError:
        print(f"    first lines of {first.filename}: not readable with Python's zipfile")
        return
    print(f"    first lines of {first.filename}:")
    for line in lines:
        print(f"      {line}")


def describe_gzip(url: str) -> None:
    # The DfT server ignores range requests, so the file is streamed from its start and the
    # connection closed after the first 64 KB.
    def read_head() -> tuple[int, bytes]:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            return int(response.headers["Content-Length"]), response.read(1 << 16)

    size, head = with_retries(read_head)
    # wbits=31 tells zlib to expect a gzip header. A partial stream decompresses as far as it goes.
    text = zlib.decompressobj(wbits=31).decompress(head).decode("utf-8", "replace")
    print(f"  gzip, {mb(size)}")
    print("    first lines:")
    for line in text.splitlines()[:FIRST_LINES]:
        print(f"      {line}")


def print_sizes() -> None:
    print("Size of every file from 2018 on: results + failure items = total")
    for label, results_url, items_url in YEARS:
        results, items = remote_size(results_url), remote_size(items_url)
        print(f"  {label}: {mb(results)} + {mb(items)} = {mb(results + items)}")


def fetch_lookups(url: str) -> zipfile.ZipFile:
    def read_all() -> bytes:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            return response.read()

    content = with_retries(read_all)
    print(f"Lookup tables, {url.rsplit('/', 1)[1]}, {len(content) / 1e6:.2f} MB")
    return zipfile.ZipFile(io.BytesIO(content))


def count_lookup_rows(archive: zipfile.ZipFile) -> None:
    for m in archive.infolist():
        with archive.open(m) as f:
            lines = f.read().decode("utf-8", "replace").splitlines()
        print(f"  {m.filename}: {len(lines) - 1:,} rows below a header of: {lines[0]}")


def count_defect_codes(archive: zipfile.ZipFile) -> None:
    with archive.open("item_detail.csv") as f:
        rows = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="|"))
    per_class = Counter(r["test_class_id"] for r in rows)
    cars = Counter(r["rfr_deficiency_category"] for r in rows if r["test_class_id"] == CARS)
    print("Defect codes in item_detail.csv")
    print(f"  {len({r['rfr_id'] for r in rows}):,} distinct rfr_id over {len(rows):,} rows")
    print(
        "  rows per vehicle class: "
        + ", ".join(f"{k}: {per_class[k]:,}" for k in sorted(per_class))
    )
    print(f"  class {CARS} by category: " + ", ".join(f"{k}: {v:,}" for k, v in cars.most_common()))


def main() -> None:
    for label, url in FILES:
        print(label)
        if url.endswith(".zip"):
            describe_zip(url)
        else:
            describe_gzip(url)
    print_sizes()
    lookups = fetch_lookups(LOOKUPS)
    count_lookup_rows(lookups)
    count_defect_codes(lookups)


if __name__ == "__main__":
    main()
