"""Land the 17 source files in the Azure container raw, straight from the publishers.

Run as `python src/motrisk/fetch.py` for all 17, or with file names after it for only those.
"""

import hashlib
import logging
import sys
import time
from urllib.parse import urljoin

import requests
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

CATALOGUE = "https://data.dft.gov.uk/anonymised-mot-test/test_data/"
C_LIST = [
    "dft_test_result_2018.zip",
    "dft_test_result_2019.zip",
    "dft_test_result_2020.zip",
    "dft_test_result_2021.zip",
    "dft_test_item_2018.zip",
    "dft_test_item_2019.zip",
    "dft_test_item_2020.zip",
    "dft_test_item_2021.zip",
]
PORTAL = "https://edh-dvsa-data-gov-uk-files-prod.s3.eu-west-1.amazonaws.com/"
P_LIST = [
    "dft_test_result_2022.zip",
    "dft_test_result_2023.zip",
    "dft_test_result_extracts_2024.zip",
    "dft_test_result_extracts_2025.zip",
    "dft_test_item_2022.zip",
    "dft_test_item_2023.zip",
    "dft_test_item_extracts_2024.zip",
    "dft_test_item_extracts_2025.zip",
    "lookup.zip",
]
CHUNK = 4 * 1024 * 1024

# Every file to land, by name, with its address.
rel = {}
for x in C_LIST:
    rel[x] = urljoin(CATALOGUE, x)
for x in P_LIST:
    rel[x] = urljoin(PORTAL, x)


"""
USEFUL FUNCTIONS
"""


def upload(container, name, url):
    """Stream url into the file name in container, 4 MiB block by block; return size and SHA-256.

    The file appears only at the final commit, which also stores its SHA-256 and address with it.
    """
    blob = container.get_blob_client(name)
    # (3, 10): 3 s to connect, then at most 10 s between two pieces of data, not for the whole file.
    r = requests.get(url, stream=True, timeout=(3, 10))
    r.raise_for_status()
    h = hashlib.sha256()

    n = 0
    id_list = []
    size = 0

    for x in r.iter_content(chunk_size=CHUNK):
        id_list.append(f"{n:06d}")
        n += 1
        size += len(x)

        blob.stage_block(id_list[-1], x)
        h.update(x)

    blob.commit_block_list(id_list, metadata={"sha256": h.hexdigest(), "source_url": url})

    return {"size": size, "sha256": h.hexdigest()}


def upload_with_retries(container, name, url):
    """upload, tried up to 4 times on a cut or slow connection, waiting 1, 2, 4 and 8 s.

    A server's refusal (an HTTP error such as 404) is not retried: it raises at once. Each retry
    starts from the first byte, and nothing is committed until one attempt gets the whole file.
    """
    for i in range(4):
        try:
            result = upload(container, name, url)
            break
        except (
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            time.sleep(2**i)
            logging.warning("attempt %d failed: %s", i + 1, type(e).__name__)
            if i == 3:
                logging.warning("End of final attempt.")
                raise

    return result


"""
CODE
"""


def main(names):
    """Land each file in names into the container raw, printing a line as each one lands."""
    credential = DefaultAzureCredential()
    service = BlobServiceClient(
        account_url="https://stmotrisk.blob.core.windows.net", credential=credential
    )
    container = service.get_container_client("raw")

    size_hex = {}
    i = 1
    for name in names:
        size_hex[name] = upload_with_retries(container, name, rel[name])
        print(f"[{i:02d}] {name}: size {size_hex[name]['size']} sha256 {size_hex[name]['sha256']}")
        i += 1


# Run as a script: the names typed after it, or all 17 when none are typed.
if __name__ == "__main__":
    main(sys.argv[1:] or list(rel))
