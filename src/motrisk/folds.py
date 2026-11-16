"""What the full and the small models share: the folds, the tiers, the shuffle and the tally.

- **Folds.** Walking forward by target year: the fold of test year Y trains on the rows of target
  years 2019 to Y - 1 and is tested on those of Y (DATA.md, "The models").
- **Tiers.** In each fold, an entry with at least 10(d + 1) ones in its training rows gets the
  full model, with all d inputs; one with at least 10 per weight of the small model, 150, the
  small model; one with fewer its base rate, the share of its training rows that hold it, 0 when
  none does. An entry's ones and rows are counted on rows of the classes it is listed for only,
  as everything else here is.
- **The gap.** The days between the two slots enter as bands: under 300 days, about a year (300
  to 430), 431 to 730, 731 to 1,095, and over 1,095. About a year is the reference, so each other
  band is one 0/1 input. Each kind of vehicle gets a curve of its own across the bands: in the
  small models the bands are crossed with u and g, in the full models with each entry of the
  previous slot (DATA.md, "The models").
- **Shuffle.** For the shuffled-label check, the labels are permuted among the rows of each
  target year and class, by a fixed hash, so that each entry keeps its ones in every year and
  the pairing of inputs and labels is broken. The same SQL serves both machines.
- **Tally.** Every model's predictions, row by row or cell by cell, become the same counts: true
  positives, false positives and false negatives at tau = 0.5, and the rows and ones in each
  band of probability 0.01 wide.
"""

from pathlib import Path

import numpy as np

ROWS = Path("data/training_rows")
LOOKUP = Path("data/parquet/lookup/item_detail.parquet")
FIRST_YEAR = 2019
TEST_YEARS = range(2020, 2026)
TAU = 0.5
BANDS = 100
# The small model's inputs: u, g, the four bands, and the bands crossed with u and with g alone.
SMALL_INPUTS = 14
NUMBERS = ["test_mileage", "age_years", "cylinder_capacity"]
# The gap's band edges in days, the author's of 2026-11-13; band 1, about a year, is the reference.
BAND_EDGES = (300, 431, 731, 1096)
BANDS_KEPT = (0, 2, 3, 4)
# scikit-learn divides the loss by the rows' total weight, so its default tolerance stops a fit
# before the weights of rare inputs settle. The small models are run to this one.
SMALL_TOL = 1e-10
MAX_ITER = 10_000
# The columns of a training row the models read, besides its label and the gap in days.
INPUTS = [
    "vehicle_id",
    "target_start",
    "target_year",
    "test_class_id",
    "fuel_type",
    "make",
    "model",
    "test_mileage",
    "age_years",
    "cylinder_capacity",
    "previous_entries",
    "previous_group_ids",
]


def training_years(test_year: int) -> list[int]:
    """The target years a fold trains on: from 2019 to the year before its test year."""
    return list(range(FIRST_YEAR, test_year))


def tier(ones: int, d: int) -> str:
    """The model an entry gets in a fold from its ones in the training rows, with d inputs."""
    if ones >= 10 * (d + 1):
        return "full"
    if ones >= 10 * (SMALL_INPUTS + 1):
        return "small"
    return "base_rate" if ones > 0 else "none"


def gap_band(days) -> np.ndarray:
    """Each gap's band, 0 to 4: under 300 days, about a year, 1 to 2 years, 2 to 3, over 3."""
    return np.digitize(np.asarray(days), BAND_EDGES)


def load_entry_groups(con, lookup: Path = LOOKUP) -> None:
    """Add entry_groups to con: each entry with the group directly above its defect's code.

    The same mapping as the dbt model int_entry_groups: a code's group is the same in every
    class, and a renumbered defect takes the group of the code it is numbered by.
    """
    con.execute(
        f"""CREATE OR REPLACE TABLE entry_groups AS
            SELECT DISTINCT e.entry, CAST(d.test_item_id AS INTEGER) AS group_id
            FROM (SELECT DISTINCT entry FROM entry_classes) AS x
            JOIN read_csv('transform/seeds/year_vector_entries.csv', header = true) AS e
                USING (entry)
            JOIN read_parquet('{lookup}') AS d ON CAST(d.rfr_id AS INTEGER) = e.problem"""
    )


def rows_sql(year: int, shuffled: bool, rows: Path | None = None) -> str:
    """A query for the training rows of one target year, the labels permuted when shuffled.

    Each row keeps its own inputs; when shuffled, its label is that of the row of the same class
    at the same place in an order fixed by a hash of the key, so the permutation is the same on
    every machine and every run. days_between is the gap in whole days.
    """
    source = f"read_parquet('{(rows or ROWS) / f'{year}.parquet'}')"
    inputs = ", ".join(f"i.{c}" for c in INPUTS)
    inputs += ", CAST(round(i.weeks_between * 7) AS INTEGER) AS days_between"
    if not shuffled:
        return f"SELECT {inputs}, i.label_entries FROM {source} AS i"
    return f"""WITH r AS (SELECT * FROM {source}),
               i AS (
                   SELECT *, row_number() OVER (
                       PARTITION BY test_class_id ORDER BY vehicle_id, target_start) AS place
                   FROM r
               ),
               s AS (
                   SELECT test_class_id, label_entries, row_number() OVER (
                       PARTITION BY test_class_id
                       ORDER BY hash(vehicle_id, target_start, 'shuffle'), vehicle_id, target_start
                   ) AS place
                   FROM r
               )
               SELECT {inputs}, s.label_entries
               FROM i
               JOIN s ON s.test_class_id = i.test_class_id AND s.place = i.place"""


def tally(p, rows, ones) -> tuple[int, int, int, np.ndarray, np.ndarray]:
    """True positives, false positives, false negatives at TAU, and rows and ones per band.

    p, rows and ones are arrays of the same length: a probability, and the rows that carry it and
    how many of them hold the entry; one row each when the model predicts row by row. Band b holds
    the probabilities from b/100 to (b + 1)/100, the last one including 1.
    """
    p = np.asarray(p, dtype=np.float64)
    rows = np.asarray(rows, dtype=np.int64)
    ones = np.asarray(ones, dtype=np.int64)
    flagged = p >= TAU
    tp = int(ones[flagged].sum())
    fp = int((rows - ones)[flagged].sum())
    fn = int(ones[~flagged].sum())
    band = np.minimum((p * BANDS).astype(np.int64), BANDS - 1)
    return (
        tp,
        fp,
        fn,
        np.bincount(band, weights=rows, minlength=BANDS).astype(np.int64),
        np.bincount(band, weights=ones, minlength=BANDS).astype(np.int64),
    )


def check_tally(entry, tp, fp, fn, band_rows, band_ones, rows, ones) -> None:
    """Stop unless the bands add up to the rows and ones scored and agree with the counts at TAU.

    The bands from 0.50 hold exactly the rows flagged at TAU, true and false positives, and the
    ones among them, the true positives.
    """
    first = int(TAU * BANDS)
    if (
        band_rows.sum() != rows
        or band_ones.sum() != ones
        or tp + fn != ones
        or band_rows[first:].sum() != tp + fp
        or band_ones[first:].sum() != tp
    ):
        raise SystemExit(f"entry {entry}: the bands and the counts at tau disagree")
