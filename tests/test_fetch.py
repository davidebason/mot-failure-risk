"""Landing the 17 files: their addresses, the upload in blocks, the retries and the main loop.

Nothing here touches the network or Azure: the download is a fake response and the container a
fake that records what it is asked to store.
"""

import csv
import hashlib
from pathlib import Path

import pytest
import requests

from motrisk import fetch

CHUNKS = [b"first block ", b"second block ", b"last"]
URL = "https://example.invalid/data/file.zip"


class FakeResponse:
    """A streamed download that yields its chunks, then optionally fails as a cut transfer does."""

    def __init__(self, chunks, status=200, cut_after=None):
        self.chunks, self.status, self.cut_after = chunks, status, cut_after
        self.chunk_sizes = []

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.exceptions.HTTPError(f"{self.status} error")

    def iter_content(self, chunk_size):
        self.chunk_sizes.append(chunk_size)
        for n, chunk in enumerate(self.chunks):
            if self.cut_after is not None and n == self.cut_after:
                raise requests.exceptions.ChunkedEncodingError("connection broken")
            yield chunk


class FakeBlob:
    def __init__(self):
        self.staged, self.commits = [], []

    def stage_block(self, block_id, data):
        self.staged.append((block_id, data))

    def commit_block_list(self, block_ids, metadata):
        self.commits.append((list(block_ids), metadata))


class FakeContainer:
    def __init__(self):
        self.blobs = {}

    def get_blob_client(self, name):
        return self.blobs.setdefault(name, FakeBlob())


def serve(monkeypatch, *responses):
    """Make requests.get return the given responses in turn, and record the calls."""
    queue, calls = list(responses), []

    def fake_get(url, stream, timeout):
        calls.append((url, stream, timeout))
        return queue.pop(0)

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    return calls


def no_sleep(monkeypatch):
    """Record the retry waits instead of waiting them."""
    waits = []
    monkeypatch.setattr(fetch.time, "sleep", waits.append)
    return waits


def test_the_addresses_are_exactly_those_of_the_fetch_log() -> None:
    with Path("data/fetch_log.tsv").open(newline="") as f:
        logged = {row["file"]: row["url"] for row in csv.DictReader(f, delimiter="\t")}
    assert fetch.rel == logged


def test_upload_streams_in_blocks_and_commits_them_with_the_hash(monkeypatch) -> None:
    response = FakeResponse(CHUNKS)
    calls = serve(monkeypatch, response)
    container = FakeContainer()

    result = fetch.upload(container, "file.zip", URL)

    blob = container.blobs["file.zip"]
    data = b"".join(CHUNKS)
    assert calls == [(URL, True, (3, 10))]
    assert response.chunk_sizes == [fetch.CHUNK]
    assert blob.staged == [("000000", CHUNKS[0]), ("000001", CHUNKS[1]), ("000002", CHUNKS[2])]
    assert blob.commits == [
        (
            ["000000", "000001", "000002"],
            {"sha256": hashlib.sha256(data).hexdigest(), "source_url": URL},
        )
    ]
    assert result == {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_a_server_error_stops_before_anything_is_staged(monkeypatch) -> None:
    serve(monkeypatch, FakeResponse(CHUNKS, status=404))
    container = FakeContainer()

    with pytest.raises(requests.exceptions.HTTPError):
        fetch.upload(container, "file.zip", URL)
    assert container.blobs["file.zip"].staged == []
    assert container.blobs["file.zip"].commits == []


def test_a_cut_transfer_is_retried_from_the_first_byte(monkeypatch, caplog) -> None:
    serve(monkeypatch, FakeResponse(CHUNKS, cut_after=1), FakeResponse(CHUNKS))
    waits = no_sleep(monkeypatch)
    container = FakeContainer()

    result = fetch.upload_with_retries(container, "file.zip", URL)

    data = b"".join(CHUNKS)
    blob = container.blobs["file.zip"]
    assert waits == [1]
    assert len(blob.commits) == 1
    assert blob.commits[0][0] == ["000000", "000001", "000002"]
    assert blob.commits[0][1]["sha256"] == hashlib.sha256(data).hexdigest()
    assert result == {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    assert caplog.messages == ["attempt 1 failed: ChunkedEncodingError"]


def test_four_failed_attempts_give_up_and_commit_nothing(monkeypatch, caplog) -> None:
    serve(monkeypatch, *[FakeResponse(CHUNKS, cut_after=0) for _ in range(4)])
    waits = no_sleep(monkeypatch)
    container = FakeContainer()

    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        fetch.upload_with_retries(container, "file.zip", URL)
    assert waits == [1, 2, 4, 8]
    assert container.blobs["file.zip"].commits == []
    assert caplog.messages[-1] == "End of final attempt."


def test_a_server_error_is_not_retried(monkeypatch) -> None:
    calls = serve(monkeypatch, FakeResponse(CHUNKS, status=404))
    waits = no_sleep(monkeypatch)

    with pytest.raises(requests.exceptions.HTTPError):
        fetch.upload_with_retries(FakeContainer(), "file.zip", URL)
    assert len(calls) == 1
    assert waits == []


def test_main_lands_only_the_names_it_is_given_and_prints_a_line_each(monkeypatch, capsys) -> None:
    landed = []

    def fake_upload(container, name, url):
        landed.append((name, url))
        return {"size": 7, "sha256": "ab" * 32}

    class FakeService:
        def __init__(self, account_url, credential):
            pass

        def get_container_client(self, name):
            assert name == "raw"
            return FakeContainer()

    monkeypatch.setattr(fetch, "DefaultAzureCredential", lambda: None)
    monkeypatch.setattr(fetch, "BlobServiceClient", FakeService)
    monkeypatch.setattr(fetch, "upload_with_retries", fake_upload)

    fetch.main(["lookup.zip", "dft_test_item_2022.zip"])

    assert landed == [
        ("lookup.zip", fetch.rel["lookup.zip"]),
        ("dft_test_item_2022.zip", fetch.rel["dft_test_item_2022.zip"]),
    ]
    assert capsys.readouterr().out.splitlines() == [
        f"[01] lookup.zip: size 7 sha256 {'ab' * 32}",
        f"[02] dft_test_item_2022.zip: size 7 sha256 {'ab' * 32}",
    ]
