"""Whether DuckDB reads every CSV in the Azure container csv, with the reading DATA.md sets out.

For each CSV that src/motrisk/extract.py committed to csv, this reads the file straight from Azure
through DuckDB's azure extension, with the separator and quoting set out under "The files" in
DATA.md: `|` and no quoting for 2022, 2023 and the lookup tables; double quotes, a quote inside a
value doubled, for the 2021 results; double quotes and a backslash as the escape for every other
comma-separated file. Every value is read as text, since types are for the staging models to set.
It prints each file's size, its columns, the rows read and the rows skipped for not splitting into
as many values as the header has columns, and counts the files that could not be read at all or
that read as a single column, the sign of a wrong separator.

Needs a login holding Storage Blob Data Reader or Contributor on the storage account: `az login`
on the laptop, or the machine's own identity on the virtual machine. It reads all 51 GB, so it is
run on the virtual machine, from the repository root:

    python evidence/09_csv_from_azure.py
"""

import duckdb

from motrisk.convert import reading

ACCOUNT = "stmotrisk"
CONTAINER = "csv"


def main() -> None:
    con = duckdb.connect()
    # DuckDB takes 80% of the memory by default; the virtual machine's 1 GiB leaves too little
    # beside it for Python and the system, which killed the first extraction run there.
    con.execute("SET memory_limit = '400MB'")
    con.execute("INSTALL azure")
    con.execute("LOAD azure")
    # On Linux the extension's default transport looks for certificates where Ubuntu keeps none.
    con.execute("SET azure_transport_option_type = 'curl'")
    con.execute(f"CREATE SECRET (TYPE azure, PROVIDER credential_chain, ACCOUNT_NAME '{ACCOUNT}')")
    # Selecting only the size reads each file's listing in the container, not the file itself.
    files = con.execute(
        f"SELECT filename, size FROM read_blob('az://{CONTAINER}/*/*.csv') ORDER BY filename"
    ).fetchall()

    problems = 0
    total_rows = total_skipped = 0
    print(f"{'file':<100} {'bytes':>15} {'columns':>7} {'rows':>12} {'skipped':>7}")
    for path, size in files:
        name = path.removeprefix(f"az://{CONTAINER}/")
        options = f"{reading(name.split('/')[0])}, header = true, all_varchar = true"
        try:
            columns = len(
                con.execute(f"DESCRIBE SELECT * FROM read_csv(?, {options})", [path]).fetchall()
            )
            # Every result is read to its end: DuckDB writes the skipped rows only once it is.
            [(rows,)] = con.execute(
                f"SELECT count(*) FROM read_csv(?, {options}, store_rejects = true)", [path]
            ).fetchall()
            [(skipped,)] = con.execute("SELECT count(DISTINCT line) FROM reject_errors").fetchall()
            con.execute("DROP TABLE reject_errors")
            con.execute("DROP TABLE reject_scans")
        except duckdb.Error as e:
            print(f"{name:<100} {size:>15,} not read: {str(e).splitlines()[0]}")
            problems += 1
            continue
        flag = "  ONE COLUMN" if columns == 1 else ""
        problems += columns == 1
        total_rows += rows
        total_skipped += skipped
        print(f"{name:<100} {size:>15,} {columns:>7} {rows:>12,} {skipped:>7,}{flag}")

    total_bytes = sum(size for _, size in files)
    print(
        f"files: {len(files)}, bytes: {total_bytes:,}, rows read: {total_rows:,},"
        f" rows skipped: {total_skipped:,}, problems: {problems}"
    )


if __name__ == "__main__":
    main()
