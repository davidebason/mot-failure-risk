"""Reading a member of the publisher's ZIP archives, whatever its compression.

Python's zipfile reads stored and deflated members, but not Deflate64, which the 2022 and 2023
results files use. Importing `zipfile_deflate64` teaches zipfile to read Deflate64 too, so
`open_member` is zipfile's own reading for every member, which checks the CRC-32 the archive
records once the member is read to its end. It replaces a reader built on the `inflate64` package,
which held on to every compressed byte it was given: a 1.2 GB archive needed more memory than the
virtual machine has, while `zipfile_deflate64` reads it in about 50 MB.
"""

import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

import zipfile_deflate64  # noqa: F401  imported for its effect: zipfile reads Deflate64


@contextmanager
def open_member(archive: Path, name: str) -> Iterator[BinaryIO]:
    """Open member `name` of `archive` for reading as bytes, Deflate64 included."""
    with zipfile.ZipFile(archive) as zf, zf.open(name) as f:
        yield f
