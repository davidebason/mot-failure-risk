"""Export from the dbt build the two tables the steps on our computer read.

Run from the repository's root, once the dbt build has written data/processed/mot.duckdb:

    python src/motrisk/export.py

- The training table, one Parquet file per target year, into data/training_rows/, printing each
  year's rows and bytes (DATA.md, "The training table: every possible row accounted for").
- Most popular's lists, the dbt model most_popular, into data/processed/most_popular.csv, printing
  them (DATA.md, "The baselines").
"""

from pathlib import Path

import duckdb

DATABASE = Path("data/processed/mot.duckdb")
ROWS = Path("data/training_rows")
MOST_POPULAR = Path("data/processed/most_popular.csv")
TARGET_YEARS = range(2019, 2026)


def main() -> None:
    con = duckdb.connect(str(DATABASE), read_only=True)
    # Lets DuckDB write rows as they come rather than in order, which keeps memory small; the
    # order of the rows carries no meaning.
    con.execute("SET preserve_insertion_order = false")
    ROWS.mkdir(parents=True, exist_ok=True)
    for year in TARGET_YEARS:
        out = ROWS / f"{year}.parquet"
        con.execute(
            f"COPY (SELECT * FROM training_rows WHERE target_year = {year}) "
            f"TO '{out}' (FORMAT parquet, COMPRESSION zstd)"
        )
        (rows,) = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()
        print(year, rows, out.stat().st_size, flush=True)
    query = "SELECT * FROM most_popular ORDER BY list_year, list_rank"
    con.execute(f"COPY ({query}) TO '{MOST_POPULAR}' (HEADER)")
    print(con.execute(query).fetchall())
    con.close()


if __name__ == "__main__":
    main()
