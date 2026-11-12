"""Which of a vehicle's tests on one day comes first, to choose the test that starts a slot.

A slot's first test gives the row its vehicle details, mileage and age, but `test_date` is a day,
and a vehicle often has a normal test and its retest on the same day. Only the files from 2024 on
say when each test was completed, `completed_date`, which the build drops. Over those two years
this takes every two tests of a vehicle on one day, stopped tests removed, and prints how often
the lower `test_id` was completed first, how often a normal test was completed before a test of
another type, and, of two normal tests, how often the lower mileage was completed first.

To fit in a laptop's memory it takes the vehicles whose `hash(vehicle_id) % 20` is 0, about 5% of
them, chosen by their identifier alone, as evidence/14 does. Reads the local Parquet copy in
data/parquet/. Run from the repository root:

    python evidence/16_same_day_tests.py
"""

import duckdb


def main() -> None:
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")
    con.execute(
        """CREATE TABLE tests AS
           SELECT test_id::BIGINT AS test_id, vehicle_id::BIGINT AS vehicle_id,
                  test_date::DATE AS test_date, test_type,
                  completed_date::TIMESTAMP AS completed,
                  nullif(test_mileage::INT, 0) AS mileage
           FROM read_parquet('data/parquet/dft_test_result_extracts_202[45]/*.parquet')
           WHERE hash(vehicle_id::BIGINT) % 20 = 0
             AND test_result NOT IN ('ABR', 'ABA', 'ABRVE')"""
    )
    con.execute(
        """CREATE TABLE pairs AS
           SELECT a.test_type AS type_a, b.test_type AS type_b,
                  a.completed AS completed_a, b.completed AS completed_b,
                  a.mileage AS mileage_a, b.mileage AS mileage_b
           FROM tests a
           JOIN tests b
             ON a.vehicle_id = b.vehicle_id AND a.test_date = b.test_date
            AND a.test_id < b.test_id"""
    )
    (n_tests,) = con.execute("SELECT count(*) FROM tests").fetchall()[0]
    (n_pairs,) = con.execute("SELECT count(*) FROM pairs").fetchall()[0]
    print(f"tests of 2024 and 2025, 5% of vehicles, stopped tests removed: {n_tests:,}")
    print(f"pairs of a vehicle's tests on one day: {n_pairs:,}")

    first, later, same = con.execute(
        """SELECT count(*) FILTER (WHERE completed_a < completed_b),
                  count(*) FILTER (WHERE completed_a > completed_b),
                  count(*) FILTER (WHERE completed_a = completed_b)
           FROM pairs"""
    ).fetchall()[0]
    print(
        f"  the lower test_id completed first: {first:,}; later: {later:,}; "
        f"at the same time: {same:,}"
    )

    nt_first, nt_later = con.execute(
        """SELECT count(*) FILTER (WHERE (type_a = 'NT') = (completed_a < completed_b)),
                  count(*) FILTER (WHERE (type_a = 'NT') = (completed_a > completed_b))
           FROM pairs
           WHERE (type_a = 'NT') <> (type_b = 'NT') AND completed_a <> completed_b"""
    ).fetchall()[0]
    print(
        f"  a normal test and a test of another type: the normal test completed first "
        f"{nt_first:,}, later {nt_later:,}"
    )

    low_first, low_later, undecided = con.execute(
        """SELECT count(*) FILTER (WHERE (mileage_a < mileage_b) = (completed_a < completed_b)
                                     AND mileage_a <> mileage_b),
                  count(*) FILTER (WHERE (mileage_a < mileage_b) = (completed_a > completed_b)
                                     AND mileage_a <> mileage_b),
                  count(*) FILTER (WHERE mileage_a IS NULL OR mileage_b IS NULL
                                      OR mileage_a = mileage_b)
           FROM pairs
           WHERE type_a = 'NT' AND type_b = 'NT' AND completed_a <> completed_b"""
    ).fetchall()[0]
    print(
        f"  two normal tests: the lower mileage completed first {low_first:,}, later "
        f"{low_later:,}; mileage equal or missing {undecided:,}"
    )

    (differs,) = con.execute(
        "SELECT count(*) FROM pairs WHERE mileage_a IS DISTINCT FROM mileage_b"
    ).fetchall()[0]
    print(f"  pairs whose mileages differ: {differs:,}")


if __name__ == "__main__":
    main()
