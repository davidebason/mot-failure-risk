"""Reading a member of the publisher's ZIP archives, whatever its compression.

Python's zipfile reads stored and deflated members, but not Deflate64, which the 2022 and 2023
results files use. `open_member` gives a binary stream for any member: zipfile's own for the
methods it supports, and for Deflate64 one that reads the member's compressed bytes straight from
the archive, inflates them with `inflate64`, and checks the CRC-32 the archive records.
"""

import io
import struct
import zipfile
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

import inflate64

DEFLATE64 = 9
# A local file header: signature, version, flags, method, time, date, CRC-32, compressed size,
# uncompressed size, name length, extra field length. The member's data follows the name and
# the extra field.
_LOCAL_HEADER = struct.Struct("<4s5H3L2H")
_LOCAL_SIGNATURE = b"PK\x03\x04"
_CHUNK = 1 << 20


class _Deflate64Reader(io.RawIOBase):
    """The inflated bytes of one Deflate64 member, from a file positioned at its data."""

    def __init__(self, source: BinaryIO, compressed_size: int, crc: int) -> None:
        self._source = source
        self._left = compressed_size
        self._crc_expected = crc
        self._crc = 0
        self._inflater = inflate64.Inflater()
        self._pending = memoryview(b"")

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        while not self._pending and self._left > 0:
            chunk = self._source.read(min(_CHUNK, self._left))
            if not chunk:
                raise EOFError("the archive ends inside a member")
            self._left -= len(chunk)
            out = self._inflater.inflate(chunk)
            self._crc = zlib.crc32(out, self._crc)
            self._pending = memoryview(out)
        if not self._pending:
            if self._crc != self._crc_expected:
                raise zipfile.BadZipFile("CRC-32 of the inflated member does not match")
            return 0
        n = min(len(buffer), len(self._pending))
        buffer[:n] = self._pending[:n]
        self._pending = self._pending[n:]
        return n

    def close(self) -> None:
        self._source.close()
        super().close()


@contextmanager
def open_member(archive: Path, name: str) -> Iterator[BinaryIO]:
    """Open member `name` of `archive` for reading as bytes, Deflate64 included."""
    with zipfile.ZipFile(archive) as zf:
        info = zf.getinfo(name)
        if info.compress_type != DEFLATE64:
            with zf.open(info) as f:
                yield f
            return
    source = open(archive, "rb")
    source.seek(info.header_offset)
    header = _LOCAL_HEADER.unpack(source.read(_LOCAL_HEADER.size))
    if header[0] != _LOCAL_SIGNATURE:
        source.close()
        raise zipfile.BadZipFile(f"no local file header for {name}")
    source.seek(header[-2] + header[-1], io.SEEK_CUR)
    raw = _Deflate64Reader(source, info.compress_size, info.CRC)
    with io.BufferedReader(raw, buffer_size=_CHUNK) as f:
        yield f
