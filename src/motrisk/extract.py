"""Extract the CSVs of the 17 archives, into the Azure container csv or into data/extracted/.

Run from the repository's root as `python src/motrisk/extract.py azure` or `... local`, for every
archive, or with archive names after it for only those. Each CSV is named after its archive and
its own name, without the folders inside the archive: `dft_test_item_2022/test_item.csv`.
"""

import argparse
import tempfile
import zipfile
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from motrisk import archives
from motrisk.fetch import CHUNK

RAW = Path("data/raw")
EXTRACTED = Path("data/extracted")


def choose(present, names):
    """The archives in present that names asks for, in present's order; all of them if none.

    A name that is not present stops the run before anything is extracted.
    """
    missing = sorted(set(names) - set(present))
    if missing:
        raise SystemExit(f"Not found: {', '.join(missing)}. Present: {', '.join(present)}.")
    return [x for x in present if not names or x in names]


def to_azure(raw, csv, names):
    """Extract the archives named, from the container raw into the container csv.

    Each archive is downloaded to a temporary folder, deleted once its CSVs are in csv. Each CSV
    is staged 4 MiB block by block and appears only at the commit, made only if the bytes read
    are as many as the archive records.
    """
    blobs = list(raw.list_blobs())
    chosen = choose([x.name for x in blobs], names)
    for x in blobs:
        if x.name not in chosen:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / x.name
            with open(path, "wb") as f:
                bd = raw.download_blob(x.name).readinto(f)
                print(f"Downloaded {x.name}: {bd} bytes.")
            with zipfile.ZipFile(path) as zf:
                info = zf.infolist()
            for y in info:
                if y.is_dir() or y.filename.startswith("__MACOSX/"):
                    continue
                else:
                    with archives.open_member(path, y.filename) as f:
                        size = 0
                        i = 1
                        id_list = []
                        target = f"{Path(x.name).stem}/{Path(y.filename).name}"
                        blob = csv.get_blob_client(target)

                        while chunk := f.read(CHUNK):
                            id_list.append(f"{i:06d}")
                            blob.stage_block(id_list[-1], chunk)
                            size += len(chunk)
                            i += 1

                        if size == y.file_size:
                            print(
                                f"Committing {target}: {i - 1} blocks, {size} bytes,"
                                " the size the archive records."
                            )
                            blob.commit_block_list(id_list)
                        else:
                            print(
                                f"Not committing {target}: {size} bytes read,"
                                f" but the archive records {y.file_size}."
                            )


def to_local(raw_dir, out_dir, names):
    """Extract the archives named, from the ZIPs in raw_dir into out_dir.

    Each CSV is written 4 MiB at a time, and deleted if the bytes written are not as many as the
    archive records. Files in raw_dir that are not ZIPs are left alone.
    """
    arc_l = sorted(raw_dir.glob("*.zip"))
    chosen = choose([path.name for path in arc_l], names)
    for path in arc_l:
        if path.name not in chosen:
            continue
        with zipfile.ZipFile(path) as zf:
            info = zf.infolist()
        for y in info:
            if y.is_dir() or y.filename.startswith("__MACOSX/"):
                continue
            else:
                target = out_dir / path.stem / Path(y.filename).name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archives.open_member(path, y.filename) as f:
                    size = 0
                    i = 1

                    with open(target, "wb") as w:
                        while chunk := f.read(CHUNK):
                            size += len(chunk)
                            i += 1
                            w.write(chunk)
                    if size == y.file_size:
                        print(
                            f"Wrote {target}: {i - 1} chunks, {size} bytes,"
                            " the size the archive records."
                        )
                    else:
                        print(
                            f"Deleting {target}: {size} bytes written,"
                            f" but the archive records {y.file_size}."
                        )
                        target.unlink()


def main(where, names):
    """Extract the archives named, every one if none, into the container csv or data/extracted/."""
    if where == "azure":
        credential = DefaultAzureCredential()
        service = BlobServiceClient(
            account_url="https://stmotrisk.blob.core.windows.net", credential=credential
        )
        raw = service.get_container_client("raw")
        csv = service.get_container_client("csv")
        to_azure(raw, csv, names)
    else:
        to_local(RAW, EXTRACTED, names)


# Run as a script: where to extract to, then the archives, or every one when none are typed.
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract the CSVs of the 17 archives.")
    parser.add_argument(
        "where", choices=["azure", "local"], help="into the container csv, or into data/extracted/"
    )
    parser.add_argument(
        "names", nargs="*", help="the archives to extract, such as lookup.zip; every one if none"
    )
    args = parser.parse_args()
    main(args.where, args.names)
