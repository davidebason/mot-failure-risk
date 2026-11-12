"""Which groups the entries of the vector fall in, the inputs read from the previous slot by group.

Each entry belongs to a kept defect, numbered by the code used first (transform/seeds/
code_dictionary.csv), and its group is the one directly above that code in `item_detail`, the same
in every class (evidence/04). This prints how many groups the kept defects fall in, and the
renumbered defects whose two codes sit under different groups, with both groups. Reads the two
seeds and the local Parquet copy of the lookup tables in data/parquet/lookup/. Run from the
repository root:

    python evidence/17_entry_groups.py
"""

import duckdb


def main() -> None:
    con = duckdb.connect()
    con.execute(
        """CREATE TABLE code_groups AS
           SELECT DISTINCT rfr_id::INT AS rfr_id, test_item_id::INT AS group_id
           FROM read_parquet('data/parquet/lookup/item_detail.parquet')"""
    )
    con.execute(
        "CREATE TABLE codes AS SELECT * FROM read_csv('transform/seeds/code_dictionary.csv')"
    )
    con.execute(
        "CREATE TABLE entries AS SELECT * FROM read_csv('transform/seeds/year_vector_entries.csv')"
    )

    (multi,) = con.execute(
        """SELECT count(*) FROM (SELECT rfr_id FROM code_groups
                                 GROUP BY rfr_id HAVING count(*) > 1)"""
    ).fetchall()[0]
    print(f"codes listed under more than one group across classes: {multi}")

    defects, groups, no_group = con.execute(
        """SELECT count(DISTINCT e.problem), count(DISTINCT g.group_id),
                  count(DISTINCT e.problem) FILTER (WHERE g.group_id IS NULL)
           FROM entries e LEFT JOIN code_groups g ON g.rfr_id = e.problem"""
    ).fetchall()[0]
    print(
        f"kept defects: {defects:,}, under {groups} groups by the code each is numbered by; "
        f"without a group: {no_group}"
    )

    (pairs,) = con.execute("SELECT count(*) FROM codes WHERE rfr_id <> problem").fetchall()[0]
    split = con.execute(
        """SELECT c.problem,
                  any_value(g.group_id) FILTER (WHERE c.rfr_id = c.problem) AS group_of_first,
                  any_value(c.rfr_id) FILTER (WHERE c.rfr_id <> c.problem) AS later_code,
                  any_value(g.group_id) FILTER (WHERE c.rfr_id <> c.problem) AS group_of_later
           FROM codes c JOIN code_groups g USING (rfr_id)
           GROUP BY c.problem
           HAVING count(DISTINCT g.group_id) > 1
           ORDER BY c.problem"""
    ).fetchall()
    print(f"renumbered pairs kept: {pairs}; with their codes under different groups: {len(split)}")
    for problem, first, later, group_later in split:
        print(f"  {problem} under {first}, renumbered {later} under {group_later}")


if __name__ == "__main__":
    main()
