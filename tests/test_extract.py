"""Extracting the CSVs: which members are kept, their names, the blocks, the checks, the choice.

Nothing here touches Azure: the containers are fakes that record what they are asked to store,
and the archives are built in the test.
"""

import io
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from motrisk import archives, extract

FIRST = b"test_id,mileage\n" + b"".join(b"%d,%d\n" % (n, 1000 * n) for n in range(30))
SECOND = b"code,meaning\nP,pass\nF,fail\n"
# Two CSVs, one in a folder; the folder's own entry; and the macOS junk the 2022 archive carries.
MEMBERS = [
    ("tables/", b"", zipfile.ZIP_STORED),
    ("tables/first.csv", FIRST, zipfile.ZIP_DEFLATED),
    ("second.csv", SECOND, zipfile.ZIP_STORED),
    ("__MACOSX/", b"", zipfile.ZIP_STORED),
    ("__MACOSX/tables/._first.csv", b"junk", zipfile.ZIP_STORED),
]
CHUNK = 10  # small, so that FIRST takes several blocks


def archive(members=MEMBERS) -> bytes:
    """A ZIP holding members, each with its own compression."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data, method in members:
            zf.writestr(name, data, compress_type=method)
    return buffer.getvalue()


def blocks(n: int) -> int:
    """How many blocks of CHUNK bytes n bytes take."""
    return -(-n // CHUNK)


class FakeDownload:
    def __init__(self, data):
        self.data = data

    def readinto(self, stream):
        stream.write(self.data)
        return len(self.data)


class FakeRaw:
    """The container raw: archives by name, listed in name order as Azure lists them."""

    def __init__(self, archives_by_name):
        self.archives = archives_by_name
        self.downloads = []

    def list_blobs(self):
        return [SimpleNamespace(name=n, size=len(d)) for n, d in sorted(self.archives.items())]

    def download_blob(self, name):
        self.downloads.append(name)
        return FakeDownload(self.archives[name])


class FakeBlob:
    def __init__(self):
        self.staged, self.commits = [], []

    def stage_block(self, block_id, data):
        self.staged.append((block_id, data))

    def commit_block_list(self, block_ids):
        self.commits.append(list(block_ids))

    def content(self):
        """What the blob holds after its last commit, as Azure would assemble it."""
        staged = dict(self.staged)
        return b"".join(staged[block_id] for block_id in self.commits[-1])


class FakeCsv:
    def __init__(self):
        self.blobs = {}

    def get_blob_client(self, name):
        return self.blobs.setdefault(name, FakeBlob())


@pytest.fixture
def small_chunks(monkeypatch):
    monkeypatch.setattr(extract, "CHUNK", CHUNK)


def short_reads(monkeypatch):
    """Make every member read as 5 bytes, fewer than the archive records."""
    monkeypatch.setattr(archives, "open_member", lambda path, name: io.BytesIO(b"short"))


def test_choose_keeps_the_order_present_and_takes_all_when_none_are_named() -> None:
    present = ["a.zip", "b.zip", "c.zip"]
    assert extract.choose(present, []) == present
    assert extract.choose(present, ["c.zip", "a.zip"]) == ["a.zip", "c.zip"]


def test_choose_stops_on_a_name_not_present() -> None:
    with pytest.raises(SystemExit, match="Not found: lookup.zp"):
        extract.choose(["lookup.zip"], ["lookup.zp"])


def test_to_azure_commits_each_csv_under_its_archive_in_blocks(small_chunks, capsys) -> None:
    data = archive()
    raw, csv = FakeRaw({"pack.zip": data}), FakeCsv()

    extract.to_azure(raw, csv, [])

    assert set(csv.blobs) == {"pack/first.csv", "pack/second.csv"}
    first = csv.blobs["pack/first.csv"]
    ids = [f"{i:06d}" for i in range(1, blocks(len(FIRST)) + 1)]
    assert [block_id for block_id, _ in first.staged] == ids
    assert all(len(chunk) <= CHUNK for _, chunk in first.staged)
    assert first.commits == [ids]
    assert first.content() == FIRST
    assert csv.blobs["pack/second.csv"].content() == SECOND
    assert capsys.readouterr().out.splitlines() == [
        f"Downloaded pack.zip: {len(data)} bytes.",
        f"Committing pack/first.csv: {blocks(len(FIRST))} blocks, {len(FIRST)} bytes,"
        " the size the archive records.",
        f"Committing pack/second.csv: {blocks(len(SECOND))} blocks, {len(SECOND)} bytes,"
        " the size the archive records.",
    ]


def test_to_azure_downloads_only_the_archives_named() -> None:
    raw = FakeRaw({"a.zip": archive(), "b.zip": archive(), "c.zip": archive()})
    csv = FakeCsv()

    extract.to_azure(raw, csv, ["b.zip"])

    assert raw.downloads == ["b.zip"]
    assert set(csv.blobs) == {"b/first.csv", "b/second.csv"}


def test_to_azure_stops_on_an_unknown_name_before_downloading_anything() -> None:
    raw, csv = FakeRaw({"lookup.zip": archive()}), FakeCsv()

    with pytest.raises(SystemExit):
        extract.to_azure(raw, csv, ["lookup.zip", "lookup.zp"])
    assert raw.downloads == []
    assert csv.blobs == {}


def test_to_azure_commits_nothing_of_a_member_whose_crc_fails() -> None:
    data = bytearray(archive())
    at = data.find(SECOND)  # second.csv is stored, so its bytes sit in the archive as they are
    data[at] ^= 0xFF
    raw, csv = FakeRaw({"pack.zip": bytes(data)}), FakeCsv()

    with pytest.raises(zipfile.BadZipFile):
        extract.to_azure(raw, csv, [])
    assert csv.blobs["pack/first.csv"].commits != []
    assert csv.blobs["pack/second.csv"].commits == []


def test_to_azure_commits_nothing_when_fewer_bytes_are_read(monkeypatch, capsys) -> None:
    short_reads(monkeypatch)
    raw, csv = FakeRaw({"pack.zip": archive()}), FakeCsv()

    extract.to_azure(raw, csv, [])

    assert all(blob.commits == [] for blob in csv.blobs.values())
    assert (
        f"Not committing pack/first.csv: 5 bytes read, but the archive records {len(FIRST)}."
        in capsys.readouterr().out.splitlines()
    )


def test_to_local_writes_each_csv_under_its_archive(tmp_path, capsys) -> None:
    raw_dir, out_dir = tmp_path / "raw", tmp_path / "extracted"
    raw_dir.mkdir()
    (raw_dir / "pack.zip").write_bytes(archive())
    (raw_dir / "download.sh").write_text("not an archive\n")

    extract.to_local(raw_dir, out_dir, [])

    written = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*") if p.is_file())
    assert written == ["pack/first.csv", "pack/second.csv"]
    assert (out_dir / "pack/first.csv").read_bytes() == FIRST
    assert (out_dir / "pack/second.csv").read_bytes() == SECOND
    assert capsys.readouterr().out.splitlines() == [
        f"Wrote {out_dir / 'pack/first.csv'}: 1 chunks, {len(FIRST)} bytes,"
        " the size the archive records.",
        f"Wrote {out_dir / 'pack/second.csv'}: 1 chunks, {len(SECOND)} bytes,"
        " the size the archive records.",
    ]


def test_to_local_extracts_only_the_archives_named(tmp_path) -> None:
    raw_dir, out_dir = tmp_path / "raw", tmp_path / "extracted"
    raw_dir.mkdir()
    for name in ["a.zip", "b.zip"]:
        (raw_dir / name).write_bytes(archive())

    extract.to_local(raw_dir, out_dir, ["b.zip"])

    assert [p.name for p in out_dir.iterdir()] == ["b"]


def test_to_local_deletes_a_csv_with_fewer_bytes_than_recorded(monkeypatch, tmp_path) -> None:
    short_reads(monkeypatch)
    raw_dir, out_dir = tmp_path / "raw", tmp_path / "extracted"
    raw_dir.mkdir()
    (raw_dir / "pack.zip").write_bytes(archive())

    extract.to_local(raw_dir, out_dir, [])

    assert [p for p in out_dir.rglob("*") if p.is_file()] == []


def test_main_azure_extracts_from_raw_into_csv(monkeypatch) -> None:
    calls = []

    class FakeService:
        def __init__(self, account_url, credential):
            assert account_url == "https://stmotrisk.blob.core.windows.net"

        def get_container_client(self, name):
            return name

    monkeypatch.setattr(extract, "DefaultAzureCredential", lambda: None)
    monkeypatch.setattr(extract, "BlobServiceClient", FakeService)
    monkeypatch.setattr(extract, "to_azure", lambda *args: calls.append(args))

    extract.main("azure", ["lookup.zip"])

    assert calls == [("raw", "csv", ["lookup.zip"])]


def test_main_local_extracts_from_data_raw_into_data_extracted(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(extract, "to_local", lambda *args: calls.append(args))

    extract.main("local", [])

    assert calls == [(Path("data/raw"), Path("data/extracted"), [])]


@pytest.mark.parametrize("args", [[], ["locl"]])
def test_the_command_line_refuses_a_run_without_azure_or_local(args) -> None:
    run = subprocess.run(
        [sys.executable, extract.__file__, *args], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 2
    assert run.stderr.startswith("usage:")
