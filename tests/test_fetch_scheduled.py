"""The daily watcher: which names it takes, what it reads from the page and the container, what
it decides, and how it retries.

Nothing here touches the network or Azure: the page, the downloads and the container are fakes.
"""

import hashlib
import logging

import pytest
import requests

from motrisk import fetch_scheduled as fs

FILES = "https://files.example.invalid/"
PAGE = f"""<html><body>
<a href="{FILES}dft_test_result_extracts_2026.zip">results 2026</a>
<a href="{FILES}dft_test_item_extracts_2025.zip">items 2025</a>
<a href="{FILES}lookup.zip">lookup</a>
<a href="{FILES}MOT+testing+data+results+(2026).zip">first release</a>
<a href="{FILES}dft_test_result_2026.csv">not a zip</a>
<a name="top">a link with no address</a>
</body></html>"""


class FakePage:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeDownload:
    """A streamed download that yields its chunks."""

    def __init__(self, chunks):
        self.chunks, self.chunk_sizes = chunks, []

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        self.chunk_sizes.append(chunk_size)
        yield from self.chunks


class FakeBlobItem:
    """One entry of a container listing, as list_blobs yields it."""

    def __init__(self, name, sha256):
        self.name, self.metadata = name, {"sha256": sha256}


class FakeContainer:
    """A container that can only be listed: anything that tries to land a file fails."""

    def __init__(self, held):
        self.held, self.includes = held, []

    def list_blobs(self, include):
        self.includes.append(include)
        return [FakeBlobItem(name, sha256) for name, sha256 in self.held.items()]


def no_sleep(monkeypatch):
    """Record the retry waits instead of waiting them."""
    waits = []
    monkeypatch.setattr(fs.time, "sleep", waits.append)
    return waits


def fail_then(monkeypatch, *outcomes):
    """Make fetch raise or return each outcome in turn, and record the addresses it is given."""
    queue, calls = list(outcomes), []

    def fake_fetch(url):
        calls.append(url)
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(fs, "fetch", fake_fetch)
    return calls


@pytest.mark.parametrize(
    ("name", "taken"),
    [
        ("dft_test_result_2026.zip", True),
        ("dft_test_item_extracts_2026.zip", True),
        ("dft_test_result_2026_01.zip", True),  # the year may sit anywhere in the name
        ("dft_test_result_extracts_2025.zip", False),
        ("dft_test_item_latest.zip", False),  # no year at all: skipped, not a crash
        ("lookup.zip", False),
        ("MOT+testing+data+results+(2026).zip", False),
        ("dft_test_result_2026.csv", False),
    ],
)
def test_is_new_takes_only_results_and_items_zips_from_2026_on(name, taken) -> None:
    assert fs.is_new(name) == taken


def test_released_keeps_the_new_names_with_their_full_addresses(monkeypatch) -> None:
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        return FakePage(PAGE)

    monkeypatch.setattr(fs.requests, "get", fake_get)

    assert fs.released() == {
        "dft_test_result_extracts_2026.zip": f"{FILES}dft_test_result_extracts_2026.zip"
    }
    assert calls == [fs.DVSA_PAGE]


def test_fetch_returns_the_size_and_sha256_of_the_whole_download(monkeypatch) -> None:
    chunks = [b"first ", b"second ", b"last"]
    download = FakeDownload(chunks)
    monkeypatch.setattr(fs.requests, "get", lambda url, stream, timeout: download)

    data = b"".join(chunks)
    assert fs.fetch(f"{FILES}a.zip") == (len(data), hashlib.sha256(data).hexdigest())
    assert download.chunk_sizes == [fs.CHUNK]


def test_a_cut_download_is_retried_and_the_retry_is_logged(monkeypatch, caplog) -> None:
    calls = fail_then(monkeypatch, requests.exceptions.ChunkedEncodingError("cut"), (4, "ab"))
    waits = no_sleep(monkeypatch)

    assert fs.with_retries(f"{FILES}a.zip") == (4, "ab")
    assert calls == [f"{FILES}a.zip", f"{FILES}a.zip"]
    assert waits == [1]
    assert caplog.messages == ["attempt 1 failed: ChunkedEncodingError"]


def test_four_failed_downloads_give_up_after_waiting_1_2_4_and_8_s(monkeypatch, caplog) -> None:
    fail_then(monkeypatch, *[requests.exceptions.Timeout("slow") for _ in range(4)])
    waits = no_sleep(monkeypatch)

    with pytest.raises(requests.exceptions.Timeout):
        fs.with_retries(f"{FILES}a.zip")
    assert waits == [1, 2, 4, 8]
    assert caplog.messages[-1] == "End of final attempt."


def test_a_refused_download_is_not_retried(monkeypatch) -> None:
    calls = fail_then(monkeypatch, requests.exceptions.HTTPError("404"))
    waits = no_sleep(monkeypatch)

    with pytest.raises(requests.exceptions.HTTPError):
        fs.with_retries(f"{FILES}a.zip")
    assert len(calls) == 1
    assert waits == []


def test_held_hashes_reads_the_sha256_stored_on_each_file() -> None:
    container = FakeContainer({"a.zip": "11", "b.zip": "22"})

    assert fs.held_hashes(container) == {"a.zip": "11", "b.zip": "22"}
    assert container.includes == [["metadata"]]  # without it, the listing has no metadata


def test_decide_calls_each_published_file_new_same_or_changed() -> None:
    published = {"held.zip": "11", "updated.zip": "99", "fresh.zip": "33"}
    held = {"held.zip": "11", "updated.zip": "22", "only_held.zip": "44"}

    assert fs.decide(published, held) == {
        "held.zip": "same",
        "updated.zip": "changed",
        "fresh.zip": "new",
    }


def test_watch_hashes_each_new_file_decides_and_lands_nothing(monkeypatch, caplog) -> None:
    rel = {
        "dft_test_result_extracts_2026.zip": f"{FILES}result26",
        "dft_test_item_extracts_2026.zip": f"{FILES}item26",
        "dft_test_item_2026_06.zip": f"{FILES}item26_06",
    }
    hashes = {f"{FILES}result26": "new", f"{FILES}item26": "11", f"{FILES}item26_06": "99"}
    container = FakeContainer(
        {"dft_test_item_extracts_2026.zip": "11", "dft_test_item_2026_06.zip": "22"}
    )
    monkeypatch.setattr(fs, "released", lambda: rel)
    monkeypatch.setattr(fs, "with_retries", lambda url: (100, hashes[url]))
    caplog.set_level(logging.INFO)

    assert fs.watch(container) == (
        rel,
        [
            ("dft_test_item_2026_06.zip", "changed"),
            ("dft_test_item_extracts_2026.zip", "same"),
            ("dft_test_result_extracts_2026.zip", "new"),
        ],
    )
    assert caplog.messages[0] == "[01] dft_test_result_extracts_2026.zip: size 100 sha256 new"
    assert len(caplog.messages) == 3


def test_watch_downloads_nothing_when_nothing_new_is_listed(monkeypatch) -> None:
    monkeypatch.setattr(fs, "released", lambda: {})

    def no_download(url):
        raise AssertionError(f"downloaded {url}")

    monkeypatch.setattr(fs, "with_retries", no_download)

    assert fs.watch(FakeContainer({"dft_test_result_2023.zip": "11"})) == ({}, [])
