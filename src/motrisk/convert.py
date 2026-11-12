"""Convert each extracted CSV once to Parquet, into the Azure container parquet or data/parquet/.

Run from the repository's root as `python src/motrisk/convert.py azure` or `... local`, for every
archive's CSVs, or with archive names after it, such as `lookup dft_test_result_2021`, for only
those. Each CSV is read with the separator and quoting that DATA.md sets out under "The files",
every column as text, and written as `<archive>/<csv name without .csv>.parquet`.

Only the container changes: every value stays as written, except that an empty value is stored as
missing, and rows may be stored in another order, which carries no meaning. A Parquet file is kept
only if it holds as many rows as evidence/09 read from its CSV, as its run log records.
"""

import argparse
import tempfile
from pathlib import Path

import duckdb

from motrisk.extract import EXTRACTED, choose

ACCOUNT = "stmotrisk"
PARQUET = Path("data/parquet")
COUNTS = Path("data/csv_from_azure_run_2026-11-10.log")


def reading(archive: str) -> str:
    """The read_csv options DATA.md sets out for the CSVs of archive, such as `lookup`.

    `|` and no quoting for 2022, 2023 and the lookup tables; double quotes, a quote inside a value
    doubled, for the 2021 results; double quotes and a backslash as the escape for every other
    comma-separated file.
    """
    if archive == "lookup" or archive.endswith(("_2022", "_2023")):
        return "delim = '|', quote = ''"
    if archive == "dft_test_result_2021":
        return "delim = ',', quote = '\"', escape = '\"'"
    return "delim = ',', quote = '\"', escape = '\\'"


def expected_rows(log: Path) -> dict[str, int]:
    """The rows evidence/09 read from each CSV, by its name in the container csv.

    Each file's line in the log is its name, bytes, columns, rows and rows skipped.
    """
    rows = {}
    for line in log.read_text().splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[0].endswith(".csv"):
            rows[parts[0]] = int(parts[3].replace(",", ""))
    return rows


def convert(con, source: str, name: str, out: Path, expected: dict[str, int]) -> bool:
    """Write the CSV at source as Parquet at out, and keep it only if its rows are as expected.

    name is the CSV's name in the container csv, `<archive>/<file>.csv`. The rows read, the rows
    the Parquet file holds and the rows evidence/09 counted must all be equal; otherwise the file
    is deleted. Returns whether it was kept.
    """
    archive = name.split("/")[0]
    options = f"{reading(archive)}, header = true, all_varchar = true"
    out.parent.mkdir(parents=True, exist_ok=True)
    src, dst = (str(x).replace("'", "''") for x in (source, out))
    [(read,)] = con.execute(
        f"COPY (SELECT * FROM read_csv('{src}', {options}))"
        f" TO '{dst}' (FORMAT parquet, COMPRESSION zstd)"
    ).fetchall()
    [(stored,)] = con.execute("SELECT count(*) FROM read_parquet(?)", [str(out)]).fetchall()
    counted = expected.get(name)
    if read == stored == counted:
        print(f"Wrote {name}: {stored} rows, as evidence/09 counted; {out.stat().st_size} bytes.")
        return True
    print(f"Not keeping {name}: {read} rows read, {stored} stored, evidence/09 counted {counted}.")
    out.unlink()
    return False


def to_local(con, src_dir: Path, out_dir: Path, names, expected) -> int:
    """Convert the CSVs of the archives named, from src_dir into out_dir. Returns the files kept."""
    csvs = sorted(src_dir.glob("*/*.csv"))
    chosen = choose(sorted({p.parent.name for p in csvs}), names)
    kept = 0
    for p in csvs:
        if p.parent.name in chosen:
            name = f"{p.parent.name}/{p.name}"
            out = out_dir / p.parent.name / f"{p.stem}.parquet"
            kept += convert(con, str(p), name, out, expected)
    return kept


def to_azure(con, csv, parquet, names, expected) -> int:
    """Convert the CSVs of the archives named, from the container csv into the container parquet.

    DuckDB reads each CSV straight from Azure and writes its Parquet file to a temporary folder,
    which is uploaded only if it was kept, then deleted. Returns the files kept.
    """
    blobs = sorted(x.name for x in csv.list_blobs() if x.name.endswith(".csv"))
    chosen = choose(sorted({b.split("/")[0] for b in blobs}), names)
    kept = 0
    for name in blobs:
        if name.split("/")[0] not in chosen:
            continue
        target = f"{name.removesuffix('.csv')}.parquet"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "file.parquet"
            if convert(con, f"az://csv/{name}", name, out, expected):
                with open(out, "rb") as f:
                    parquet.upload_blob(target, f, overwrite=True, max_concurrency=2)
                print(f"Uploaded {target}.")
                kept += 1
    return kept


def main(where, names):
    """Convert the CSVs of the archives named, every one if none, in Azure or locally."""
    expected = expected_rows(COUNTS)
    con = duckdb.connect()
    # Lets DuckDB write rows as they come rather than hold them back to keep the CSV's order,
    # which keeps its memory small.
    con.execute("SET preserve_insertion_order = false")
    if where == "azure":
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        # The virtual machine has 1 GiB: DuckDB's default of 80% leaves too little beside it.
        con.execute("SET memory_limit = '400MB'")
        con.execute("INSTALL azure")
        con.execute("LOAD azure")
        # On Linux the extension's default transport looks for certificates where Ubuntu keeps none.
        con.execute("SET azure_transport_option_type = 'curl'")
        con.execute(
            f"CREATE SECRET (TYPE azure, PROVIDER credential_chain, ACCOUNT_NAME '{ACCOUNT}')"
        )
        service = BlobServiceClient(
            account_url=f"https://{ACCOUNT}.blob.core.windows.net",
            credential=DefaultAzureCredential(),
        )
        kept = to_azure(
            con,
            service.get_container_client("csv"),
            service.get_container_client("parquet"),
            names,
            expected,
        )
    else:
        kept = to_local(con, EXTRACTED, PARQUET, names, expected)
    print(f"Kept {kept} Parquet files.")


# Run as a script: where to convert, then the archives, or every one when none are typed.
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert the extracted CSVs to Parquet.")
    parser.add_argument(
        "where", choices=["azure", "local"], help="the container csv, or data/extracted/"
    )
    parser.add_argument(
        "names", nargs="*", help="the archives whose CSVs to convert, such as lookup; all if none"
    )
    args = parser.parse_args()
    main(args.where, args.names)
