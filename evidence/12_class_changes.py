"""How often a vehicle's test class changes from one test to its next, and when.

Over the tests staging keeps, from 20 May 2018 to the end of 2025 with stopped tests removed, this
finds every vehicle tested in more than one class, then every pair of its consecutive tests whose
class differs. It prints how many tests and vehicles there are in all, with the share of tests that
fail or pass after rectification and the share that are not normal tests. Then, for the changes:
how many there are and on how many vehicles; how far apart the two tests are; the earlier test's
result; the later test's type; the direction of the change; and how many changes each vehicle has.

Reads the local Parquet copy in data/parquet/, written by src/motrisk/convert.py. Run from the
repository root, in about two minutes:

    python evidence/12_class_changes.py
"""

import duckdb

KEPT = """(
    SELECT * FROM read_parquet('data/parquet/dft_test_result_*/*.parquet', union_by_name = true)
    WHERE test_date >= '2018-05-20' AND test_result NOT IN ('ABR', 'ABA', 'ABRVE')
)"""


def main() -> None:
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")
    [(tests, vehicles, failed, not_normal)] = con.execute(
        f"""SELECT count(*), count(DISTINCT vehicle_id),
                   avg((test_result IN ('F', 'PRS'))::INT), avg((test_type <> 'NT')::INT)
            FROM {KEPT}"""
    ).fetchall()
    print(
        f"kept tests: {tests:,}, vehicles: {vehicles:,}; failed or passed after rectification:"
        f" {failed:.1%}; not a normal test: {not_normal:.1%}"
    )

    con.execute(
        f"""CREATE TABLE multi AS SELECT vehicle_id FROM {KEPT}
            GROUP BY vehicle_id HAVING count(DISTINCT test_class_id) > 1"""
    )
    con.execute(
        f"""CREATE TABLE changes AS
            SELECT * FROM (
                SELECT vehicle_id, test_class_id AS class, test_date::DATE AS d,
                       test_type AS type, test_result AS result,
                       lag(test_class_id) OVER w AS class_before,
                       lag(test_date::DATE) OVER w AS d_before,
                       lag(test_result) OVER w AS result_before
                FROM {KEPT}
                WHERE vehicle_id IN (SELECT vehicle_id FROM multi)
                WINDOW w AS (PARTITION BY vehicle_id ORDER BY test_date, test_id::BIGINT)
            )
            WHERE class_before IS NOT NULL AND class <> class_before"""
    )
    [(n, changed)] = con.execute(
        "SELECT count(*), count(DISTINCT vehicle_id) FROM changes"
    ).fetchall()
    print(f"class changes: {n:,}, on {changed:,} vehicles, {changed / vehicles:.2%} of all")

    [gaps] = con.execute(
        """SELECT count(*) FILTER (WHERE d = d_before),
                  count(*) FILTER (WHERE d - d_before BETWEEN 1 AND 14),
                  count(*) FILTER (WHERE d - d_before BETWEEN 15 AND 140),
                  count(*) FILTER (WHERE d - d_before > 140)
           FROM changes"""
    ).fetchall()
    for label, count in zip(
        ["same day", "1 to 14 days", "15 days to 20 weeks", "more than 20 weeks"], gaps, strict=True
    ):
        print(f"  tests {label} apart: {count:,} ({count / n:.1%})")

    for title, query in [
        ("earlier test's result", "SELECT result_before, count(*) FROM changes GROUP BY 1"),
        ("later test's type", "SELECT type, count(*) FROM changes GROUP BY 1"),
        ("direction", "SELECT class_before || ' to ' || class, count(*) FROM changes GROUP BY 1"),
        (
            "changes per vehicle",
            "SELECT k, count(*) FROM"
            " (SELECT count(*) AS k FROM changes GROUP BY vehicle_id) GROUP BY 1",
        ),
    ]:
        rows = sorted(con.execute(query).fetchall(), key=lambda r: -r[1])
        print(f"{title}: " + ", ".join(f"{key}: {count:,}" for key, count in rows))


if __name__ == "__main__":
    main()
