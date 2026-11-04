"""Reading archive members, deflated and Deflate64, from archives built in the test."""

import struct
import zipfile
import zlib

import inflate64
import pytest

from motrisk.archives import open_member

DATA = b"test_id|rfr_id|rfr_type_code\n" + b"".join(b"%d|30909|F\n" % i for i in range(20_000))


def deflate64_zip(path, name: str, data: bytes, crc: int | None = None) -> None:
    """Write a one-member archive compressed with Deflate64, method 9, by hand."""
    d = inflate64.Deflater()
    comp = d.deflate(data) + d.flush()
    crc = zlib.crc32(data) if crc is None else crc
    n = name.encode()
    local = struct.pack(
        "<4s5H3L2H", b"PK\x03\x04", 20, 0, 9, 0, 0, crc, len(comp), len(data), len(n), 0
    )
    central = struct.pack(
        "<4s6H3L5H2L", b"PK\x01\x02", 20, 20, 0, 9, 0, 0, crc, len(comp), len(data), len(n),
        0, 0, 0, 0, 0, 0,
    )  # fmt: skip
    body = local + n + comp
    end = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 1, 1, len(central) + len(n), len(body), 0)
    path.write_bytes(body + central + n + end)


def test_a_deflated_member_reads_as_zipfile_reads_it(tmp_path) -> None:
    path = tmp_path / "deflated.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("items.csv", DATA)
    with open_member(path, "items.csv") as f:
        assert f.read() == DATA


def test_a_deflate64_member_is_inflated_line_by_line(tmp_path) -> None:
    path = tmp_path / "deflate64.zip"
    deflate64_zip(path, "items.csv", DATA)
    with zipfile.ZipFile(path) as zf:
        assert zf.getinfo("items.csv").compress_type == 9
    with open_member(path, "items.csv") as f:
        assert f.readline() == b"test_id|rfr_id|rfr_type_code\n"
        assert sum(1 for _ in f) == 20_000


def test_a_wrong_crc_is_refused(tmp_path) -> None:
    path = tmp_path / "corrupt.zip"
    deflate64_zip(path, "items.csv", DATA, crc=0)
    with pytest.raises(zipfile.BadZipFile), open_member(path, "items.csv") as f:
        f.read()
