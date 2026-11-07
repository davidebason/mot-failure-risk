"""The daily watcher: which files from 2026 onward has DVSA published that raw lacks?

watch, at the end, does it in three steps, each with the functions just above it:
1. the portal page's files with a year from 2026 in their name (is_new, released);
2. the SHA-256 of each, by downloading it in full (fetch, with_retries);
3. a comparison with the SHA-256 stored on each file in raw (held_hashes, decide).
The Azure Function in function/ calls watch every day and lands what it finds new or changed.
"""

import hashlib
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from motrisk.fetch import CHUNK

# DVSA's portal page, the one place that lists every file DVSA publishes, the extracts included.
DVSA_PAGE = "https://open.data.dvsa.gov.uk/mot-anonymised/index.html"


def is_new(text):
    """True for a results or items ZIP whose name holds a year from 2026 onward, anywhere in it."""
    m = re.search(r"(20\d\d)", text)
    return (
        text.startswith(("dft_test_result", "dft_test_item"))
        and text.endswith(".zip")
        and m is not None
        and int(m.group(1)) > 2025
    )


def released():
    """Every file on DVSA's portal page that is_new accepts, as {file name: address}."""
    found = {}

    r = requests.get(DVSA_PAGE, timeout=(3, 30))
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for link in soup.find_all("a", href=True):
        name = link["href"].split("/")[-1]  # the file name is the address's last part
        if is_new(name):
            found[name] = link["href"]

    return found


def fetch(url):
    """Stream url and return its size in bytes and its SHA-256 in hex."""
    # (3, 10): 3 s to connect, then at most 10 s between two pieces of data, not for the whole file.
    r = requests.get(url, stream=True, timeout=(3, 10))
    r.raise_for_status()
    h = hashlib.sha256()
    size = 0
    for x in r.iter_content(chunk_size=CHUNK):
        h.update(x)
        size += len(x)
    return size, h.hexdigest()


def with_retries(url):
    """fetch, tried up to 4 times on a cut or slow connection, waiting 1, 2, 4 and 8 s.

    A server's refusal (an HTTP error such as 404) is not retried: it raises at once.
    """
    for i in range(4):
        try:
            result = fetch(url)
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


def held_hashes(container):
    """Each file in the container, by name, with the SHA-256 stored in its metadata.

    Every file landed by fetch.upload carries one, so a file put there by other means fails here.
    """
    held = {}
    for blob in container.list_blobs(include=["metadata"]):
        held[blob.name] = blob.metadata["sha256"]
    return held


def decide(published, held):
    """For each published file, "new", "same" or "changed".

    published and held both map a file's name to its SHA-256 in hex.
    """
    result = {}
    for name, digest in published.items():
        if name not in held:
            result[name] = "new"
        elif held[name] == digest:
            result[name] = "same"
        else:
            result[name] = "changed"
    return result


def watch(container):
    """Compare the portal page's files from 2026 onward with those held in container.

    Returns their addresses, as {file name: address}, and the decisions, as a sorted list of
    (file name, "new" | "same" | "changed"). Lands nothing: the caller does.
    """
    held = held_hashes(container)
    rel = released()

    published = {}
    for i, (name, url) in enumerate(rel.items(), start=1):
        size, sha256 = with_retries(url)
        logging.info(f"[{i:02d}] {name}: size {size} sha256 {sha256}")
        published[name] = sha256

    return rel, sorted(decide(published, held).items())
