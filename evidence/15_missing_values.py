"""How many of the tests staging keeps lack a mileage, an engine size or an age, and of what kind.

Over the tests staging keeps, stopped tests and tests past a bound removed, this prints by year
and in all: the tests; those with no mileage (blank or zero); those with no engine size (blank or
zero), and how many of those are electric (fuel EL, or the name ELECTRIC); and those whose age is
unknown (no first-use date, 1 January 1971, or a first use after the test). Then the electric
vehicles' tests by year, which shows how their share grows.

Reads the local Parquet copy in data/parquet/ and the bounds staging applies. Run from the
repository root:

    python evidence/15_missing_values.py
"""

import duckdb
import yaml


def main() -> None:
    bounds = yaml.safe_load(open("transform/dbt_project.yml"))["vars"]
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")
    con.execute(
        """CREATE TABLE engine AS
           SELECT * FROM read_csv('transform/seeds/engine_size_bounds.csv', header = true)"""
    )
    con.execute(
        f"""CREATE VIEW kept AS
            SELECT year(r.test_date::DATE) AS y,
                   coalesce(r.test_mileage::INT, 0) = 0 AS no_mileage,
                   coalesce(r.cylinder_capacity::INT, 0) = 0 AS no_engine,
                   upper(trim(r.fuel_type)) IN ('EL', 'ELECTRIC') AS electric,
                   (r.first_use_date IS NULL OR r.first_use_date = '1971-01-01'
                    OR r.first_use_date::DATE > r.test_date::DATE) AS no_age
            FROM read_parquet('data/parquet/dft_test_result_*/*.parquet', union_by_name = true) r
            LEFT JOIN engine e ON e.test_class_id = r.test_class_id::INT
            WHERE r.test_date >= '2018-05-20'
              AND r.test_result NOT IN ('ABR', 'ABA', 'ABRVE')
              AND coalesce(r.test_mileage::INT, 0) <= {bounds["mileage_max"]}
              AND NOT coalesce(r.cylinder_capacity::INT > 0
                  AND r.cylinder_capacity::INT NOT BETWEEN e.lowest AND e.highest, false)
              AND NOT coalesce(r.first_use_date <> '1971-01-01'
                  AND r.first_use_date::DATE <= r.test_date::DATE
                  AND r.first_use_date::DATE
                      < r.test_date::DATE - INTERVAL {bounds["age_max_years"]} YEAR, false)"""
    )
    rows = con.execute(
        """SELECT y::VARCHAR, count(*), count(*) FILTER (WHERE no_mileage),
                  count(*) FILTER (WHERE no_engine),
                  count(*) FILTER (WHERE no_engine AND electric),
                  count(*) FILTER (WHERE no_age), count(*) FILTER (WHERE electric)
           FROM kept GROUP BY ROLLUP (y) ORDER BY y NULLS LAST"""
    ).fetchall()
    print(
        f"{'year':>5} {'tests':>12} {'no mileage':>11} {'no engine':>10} {'of which EV':>12}"
        f" {'no age':>8} {'EV tests':>9}"
    )
    for y, tests, mileage, engine, ev_engine, age, ev in rows:
        print(
            f"{y or 'all':>5} {tests:>12,} {mileage:>11,} {engine:>10,} {ev_engine:>12,}"
            f" {age:>8,} {ev:>9,}  ({mileage / tests:.2%} / {engine / tests:.2%}"
            f" / {age / tests:.3%}; EVs {ev / tests:.2%})"
        )


if __name__ == "__main__":
    main()
