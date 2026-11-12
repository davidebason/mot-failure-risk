"""Whether the container parquet holds one Parquet file per CSV, with the rows evidence/09 counted.

For each Parquet file src/motrisk/convert.py uploaded to parquet, this reads its row count from the
file's own footer, through DuckDB's azure extension, so no data is downloaded. It compares the count
with the rows evidence/09 read from the CSV of the same name, as its run log records, and prints
each file's size, columns and rows, then the totals, the CSVs with no Parquet file, and the
problems: files whose rows differ, or that match no CSV.

Needs a login holding Storage Blob Data Reader or Contributor on the storage account: `az login`
on the laptop. Run from the repository root:

    python evidence/11_parquet_in_azure.py
"""

import duckdb

from motrisk.convert import COUNTS, expected_rows

ACCOUNT = "stmotrisk"
CONTAINER = "parquet"


def main() -> None:
    expected = expected_rows(COUNTS)
    con = duckdb.connect()
    con.execute("INSTALL azure")
    con.execute("LOAD azure")
    # On Linux the extension's default transport looks for certificates where Ubuntu keeps none.
    con.execute("SET azure_transport_option_type = 'curl'")
    con.execute(f"CREATE SECRET (TYPE azure, PROVIDER credential_chain, ACCOUNT_NAME '{ACCOUNT}')")
    # Selecting only the size reads each file's listing in the container, not the file itself.
    files = con.execute(
        f"SELECT filename, size FROM read_blob('az://{CONTAINER}/*/*.parquet') ORDER BY filename"
    ).fetchall()

    problems = 0
    total_rows = 0
    seen = set()
    print(f"{'file':<100} {'bytes':>15} {'columns':>7} {'rows':>12} {'evidence/09':>12}")
    for path, size in files:
        name = path.removeprefix(f"az://{CONTAINER}/")
        csv = f"{name.removesuffix('.parquet')}.csv"
        seen.add(csv)
        [(rows,)] = con.execute("SELECT num_rows FROM parquet_file_metadata(?)", [path]).fetchall()
        # The schema lists the file's root, then one leaf per column.
        [(columns,)] = con.execute(
            "SELECT count(*) FROM parquet_schema(?) WHERE num_children IS NULL", [path]
        ).fetchall()
        counted = expected.get(csv)
        flag = "" if rows == counted else "  DIFFERS"
        problems += rows != counted
        total_rows += rows
        print(f"{name:<100} {size:>15,} {columns:>7} {rows:>12,} {counted or 0:>12,}{flag}")

    missing = sorted(set(expected) - seen)
    for csv in missing:
        print(f"no Parquet file for {csv}")
    total_bytes = sum(size for _, size in files)
    print(
        f"files: {len(files)}, bytes: {total_bytes:,}, rows: {total_rows:,},"
        f" rows evidence/09 counted: {sum(expected.values()):,},"
        f" CSVs without a Parquet file: {len(missing)}, problems: {problems}"
    )


if __name__ == "__main__":
    main()
