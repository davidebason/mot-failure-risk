"""Whether the copy in Azure is the set of files every figure in DATA.md was measured on.

Compares each file in the Blob Storage container `raw` with its line in data/fetch_log.tsv: that
it is there, that its size is the logged size, that the SHA-256 the fetcher computed from the
bytes as it landed them is the logged SHA-256, and that it came from the logged address. Also
lists any file in the container that the log does not name. Reads only the container's listing,
so nothing is downloaded. Needs a login holding Storage Blob Data Reader or Contributor on the
storage account, such as `az login`. Run from the repository root:

    python evidence/08_azure_copy.py
"""

import csv
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

ACCOUNT_URL = "https://stmotrisk.blob.core.windows.net"
CONTAINER = "raw"
LOG = Path("data/fetch_log.tsv")


def main() -> None:
    with LOG.open(newline="") as f:
        logged = {row["file"]: row for row in csv.DictReader(f, delimiter="\t")}

    service = BlobServiceClient(ACCOUNT_URL, credential=DefaultAzureCredential())
    container = service.get_container_client(CONTAINER)
    held = {blob.name: blob for blob in container.list_blobs(include=["metadata"])}

    problems = 0
    print(f"{'file':<36} {'bytes':>15}  landed (UTC)         size  sha256  address")
    for name, row in logged.items():
        blob = held.get(name)
        if blob is None:
            print(f"{name:<36} {'':>15}  missing")
            problems += 1
            continue
        metadata = blob.metadata or {}
        checks = [
            blob.size == int(row["bytes"]),
            metadata.get("sha256") == row["sha256"],
            metadata.get("source_url") == row["url"],
        ]
        problems += checks.count(False)
        marks = "  ".join(f"{'ok' if ok else 'DIFF':<4}" for ok in checks)
        print(f"{name:<36} {blob.size:>15,}  {blob.last_modified:%Y-%m-%d %H:%M:%S}  {marks}")

    extra = sorted(set(held) - set(logged))
    for name in extra:
        print(f"{name:<36} {held[name].size:>15,}  not in the fetch log")
    problems += len(extra)

    print(f"files logged: {len(logged)}, files held: {len(held)}, problems: {problems}")


if __name__ == "__main__":
    main()
