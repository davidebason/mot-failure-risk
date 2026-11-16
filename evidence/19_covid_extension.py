"""How many training rows the 2020 extension of MOT due dates lengthened.

Tests due from 30 March to 31 July 2020 were put back by six months. A vehicle tested once a year
is due about a year after its previous test, so its rows are those whose previous slot started
from 30 March to 31 July 2019. For the same window of every year from 2019 to 2023, this prints
the training rows whose previous slot started in it, and how many of them have more than 430 days
between the first tests of the two slots, the upper edge of the band of about a year. The excess
of 2019's window over the mean of the windows of 2021 to 2023 is the estimate of the rows the
extension lengthened; 2020's window is left out of that mean, since its own vehicles were tested
during the extension. A vehicle whose test it moved from July 2020 to January 2021 is among them,
since its target slot then starts in 2021. Reads the training table in data/training_rows/. Run
from the repository's root:

    python evidence/19_covid_extension.py
"""

import duckdb

ROWS = "data/training_rows/*.parquet"
YEARS = [2019, 2020, 2021, 2022, 2023]
BAND_EDGE = 430


def main() -> None:
    con = duckdb.connect()
    counts = {}
    for y in YEARS:
        rows, long_gap = con.execute(
            f"""
            SELECT count(*), count(*) FILTER (WHERE target_start - previous_start > {BAND_EDGE})
            FROM read_parquet('{ROWS}')
            WHERE previous_start BETWEEN DATE '{y}-03-30' AND DATE '{y}-07-31'
            """
        ).fetchone()
        counts[y] = (rows, long_gap)
        print(
            f"previous slot from 30 March to 31 July {y}: {rows:,} rows, "
            f"{long_gap:,} over {BAND_EDGE} days ({100 * long_gap / rows:.2f}%)"
        )
    usual = sum(counts[y][1] / counts[y][0] for y in (2021, 2022, 2023)) / 3
    rows_2019, long_2019 = counts[2019]
    expected = usual * rows_2019
    total = con.execute(f"SELECT count(*) FROM read_parquet('{ROWS}')").fetchone()[0]
    print(f"usual share over {BAND_EDGE} days, mean of 2021 to 2023: {100 * usual:.2f}%")
    print(
        f"2019's window: {long_2019:,} rows over {BAND_EDGE} days against {expected:,.0f} "
        f"at the usual share, an excess of {long_2019 - expected:,.0f} rows, "
        f"{100 * (long_2019 - expected) / total:.2f}% of the {total:,} training rows"
    )


if __name__ == "__main__":
    main()
