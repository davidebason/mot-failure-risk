"""How far apart a vehicle's consecutive tests are, to place the cutoff between slots.

Over the tests staging keeps, stopped tests and tests past a bound removed, this takes every pair
of a vehicle's consecutive tests, in date order and of any type, and prints how many weeks apart
they are, grouped into bands, with each band's share and the share up to it. A cutoff between
slots belongs where the bands hold few pairs: below it the retests and repeated tests of one visit,
above it the next annual test.

To fit in a laptop's memory it takes the vehicles whose `hash(vehicle_id) % 20` is 0, about 5% of
them, chosen by their identifier alone, so the shares stand for every vehicle. Reads the local
Parquet copy in data/parquet/ and the bounds staging applies. Run from the repository root:

    python evidence/14_test_gaps.py
"""

import duckdb
import yaml

BANDS = [0, 1, 2, 4, 8, 12, 16, 20, 24, 30, 40, 46, 50, 54, 58, 70, 90]


def main() -> None:
    bounds = yaml.safe_load(open("transform/dbt_project.yml"))["vars"]
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")
    con.execute(
        """CREATE TABLE engine AS
           SELECT * FROM read_csv('transform/seeds/engine_size_bounds.csv', header = true)"""
    )
    con.execute(
        f"""CREATE TABLE kept AS
            SELECT r.vehicle_id::BIGINT AS vehicle_id, r.test_id::BIGINT AS test_id,
                   r.test_date::DATE AS d
            FROM read_parquet('data/parquet/dft_test_result_*/*.parquet', union_by_name = true) r
            LEFT JOIN engine e ON e.test_class_id = r.test_class_id::INT
            WHERE hash(r.vehicle_id::BIGINT) % 20 = 0
              AND r.test_date >= '2018-05-20'
              AND r.test_result NOT IN ('ABR', 'ABA', 'ABRVE')
              AND coalesce(r.test_mileage::INT, 0) <= {bounds["mileage_max"]}
              AND NOT coalesce(r.cylinder_capacity::INT > 0
                  AND r.cylinder_capacity::INT NOT BETWEEN e.lowest AND e.highest, false)
              AND NOT coalesce(r.first_use_date <> '1971-01-01'
                  AND r.first_use_date::DATE <= r.test_date::DATE
                  AND r.first_use_date::DATE
                      < r.test_date::DATE - INTERVAL {bounds["age_max_years"]} YEAR, false)"""
    )
    [(tests, vehicles)] = con.execute(
        "SELECT count(*), count(DISTINCT vehicle_id) FROM kept"
    ).fetchall()
    con.execute(
        """CREATE TABLE gaps AS
           SELECT (d - lag(d) OVER (PARTITION BY vehicle_id ORDER BY d, test_id)) / 7.0 AS weeks
           FROM kept"""
    )
    [(pairs,)] = con.execute("SELECT count(weeks) FROM gaps").fetchall()
    print(f"sample: {vehicles:,} vehicles, {tests:,} tests, {pairs:,} consecutive pairs")
    edges = BANDS + [None]
    upto = 0
    for low, high in zip(edges[:-1], edges[1:], strict=True):
        cond = f"weeks >= {low}" + (f" AND weeks < {high}" if high is not None else "")
        [(n,)] = con.execute(f"SELECT count(*) FROM gaps WHERE {cond}").fetchall()
        upto += n
        label = f"{low} to {high}" if high is not None else f"{low} and more"
        print(f"  {label:>14} weeks: {n:>10,}  {n / pairs:7.2%}  up to here {upto / pairs:7.2%}")


if __name__ == "__main__":
    main()
