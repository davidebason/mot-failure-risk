"""Where the bounds on mileage, engine size and age come from, and what each turns missing.

Over the tests staging keeps, from 20 May 2018 to the end of 2025 with stopped tests removed, and
with a zero mileage or engine size already counted as missing, this prints:

- the highest mileage and the earliest first-use date;
- the 99.9% point of the mileages of class 5, the class whose mileages run highest, from which the
  one bound on mileage for every class comes, and how many mileages of each class lie above that
  bound once rounded;
- for each class, the 0.1% and 99.9% points of its engine sizes, from which its bounds come, and
  how many sizes lie outside those bounds once rounded outward;
- how many ages at the test, from the first-use dates staging keeps, are over 50 years.

The rounded bounds are read from transform/dbt_project.yml and
transform/seeds/engine_size_bounds.csv, which staging applies; yaml comes with dbt.
Reads the local Parquet copy in data/parquet/. Run from the repository root, in about two minutes:

    python evidence/13_value_bounds.py
"""

import csv
from pathlib import Path

import duckdb
import yaml

PROJECT = Path("transform/dbt_project.yml")
ENGINE = Path("transform/seeds/engine_size_bounds.csv")

KEPT = """(
    SELECT test_class_id AS class,
           test_date::DATE AS test_date,
           nullif(test_mileage::INT, 0) AS mileage,
           nullif(cylinder_capacity::INT, 0) AS engine_size,
           CASE WHEN first_use_date <> '1971-01-01' AND first_use_date::DATE <= test_date::DATE
                THEN first_use_date::DATE END AS first_use_date
    FROM read_parquet('data/parquet/dft_test_result_*/*.parquet', union_by_name = true)
    WHERE test_date >= '2018-05-20' AND test_result NOT IN ('ABR', 'ABA', 'ABRVE')
)"""


def main() -> None:
    bounds = yaml.safe_load(PROJECT.read_text())["vars"]
    with open(ENGINE) as f:
        engine = {row["test_class_id"]: row for row in csv.DictReader(f)}
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")
    # A view, not a table: each query reads the Parquet files afresh, so memory stays small.
    con.execute(f"CREATE VIEW kept AS SELECT * FROM {KEPT}")

    mileage_max = bounds["mileage_max"]
    [(point,)] = con.execute(
        "SELECT quantile_disc(mileage, 0.999) FROM kept WHERE class = '5'"
    ).fetchall()
    [(highest, earliest)] = con.execute(
        "SELECT max(mileage), min(first_use_date) FROM kept"
    ).fetchall()
    print(f"highest mileage: {highest:,}; earliest first-use date: {earliest}")
    print(f"mileage: class 5's 99.9% point {point:,}; bound for every class {mileage_max:,}")
    for cls, over, total in con.execute(
        f"""SELECT class, count(*) FILTER (WHERE mileage > {mileage_max}), count(mileage)
            FROM kept GROUP BY class ORDER BY class"""
    ).fetchall():
        print(f"  class {cls}: {over:,} of {total:,} mileages above it ({over / total:.3%})")

    print("engine size, cc: 0.1% and 99.9% points, rounded bounds, sizes outside them")
    for cls, (low, high), total in con.execute(
        """SELECT class, quantile_disc(engine_size, [0.001, 0.999]), count(engine_size)
           FROM kept GROUP BY class ORDER BY class"""
    ).fetchall():
        lo, hi = int(engine[cls]["lowest"]), int(engine[cls]["highest"])
        [(outside,)] = con.execute(
            "SELECT count(*) FROM kept WHERE class = ? AND (engine_size < ? OR engine_size > ?)",
            [cls, lo, hi],
        ).fetchall()
        print(
            f"  class {cls}: points {low:,} and {high:,}; bounds {lo:,} to {hi:,};"
            f" {outside:,} of {total:,} outside ({outside / total:.3%})"
        )

    age_max = bounds["age_max_years"]
    [(over, total)] = con.execute(
        f"""SELECT count(*) FILTER (WHERE first_use_date < test_date - INTERVAL {age_max} YEAR),
                   count(first_use_date)
            FROM kept"""
    ).fetchall()
    print(f"age: {over:,} of {total:,} known ages over {age_max} years ({over / total:.3%})")


if __name__ == "__main__":
    main()
