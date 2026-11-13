"""Scoring the two baselines: the invented vehicle, the classes, the counts adding up.

The rows are written in the test as a small Parquet file shaped like data/training_rows/; the
entries and their classes are read from the seed the build uses.
"""

import csv

import duckdb
import pytest

from motrisk import baselines


def _entries_of(classes: str) -> list[int]:
    """Entries of the seed listed for exactly these classes, such as '4' or '1 2'."""
    with open(baselines.ENTRIES, newline="") as f:
        return [int(r["entry"]) for r in csv.DictReader(f) if r["classes"] == classes]


CAR = _entries_of("3 4 5 7")
MOTORCYCLE = _entries_of("1 2")
BRAKE, TYRE, HEADLAMP, OTHER = CAR[:4]


def _rows(tmp_path, rows: list[tuple[int, list[int], list[int]]]):
    """A Parquet file of training rows: class, previous slot's entries, label."""
    path = tmp_path / "rows.parquet"
    values = ", ".join(
        f"({cls}, {previous}::INTEGER[], {label}::INTEGER[])" for cls, previous, label in rows
    )
    duckdb.execute(
        f"""COPY (SELECT * FROM (VALUES {values})
                  AS t(test_class_id, previous_entries, label_entries))
            TO '{path}' (FORMAT parquet)"""
    )
    return path


@pytest.fixture
def con():
    return baselines.connect(memory_limit="1GB")


def test_the_invented_vehicle(con, tmp_path):
    # The vehicle used to explain Repeat: brake pipe and tyre before, tyre and headlamp after.
    rows = _rows(tmp_path, [(4, [BRAKE, TYRE], [TYRE, HEADLAMP])])
    counts = baselines.repeat(con, rows)
    assert counts == {TYRE: (1, 0, 0), BRAKE: (0, 1, 0), HEADLAMP: (0, 0, 1)}


def test_an_entry_is_scored_only_on_its_classes(con, tmp_path):
    # A car entry on a motorcycle's row, and a motorcycle entry on a car's, count for nothing.
    rows = _rows(tmp_path, [(1, [BRAKE], [BRAKE]), (4, [MOTORCYCLE[0]], [])])
    assert baselines.repeat(con, rows) == {}
    assert baselines.label_ones(con, rows) == {}


def test_most_popular_predicts_its_list_on_every_row_of_its_classes(con, tmp_path):
    rows = _rows(
        tmp_path,
        [(4, [], [BRAKE]), (4, [], [TYRE]), (5, [], []), (1, [], [])],
    )
    counts = baselines.most_popular(con, rows, [BRAKE])
    # BRAKE is predicted on the three rows of classes 4 and 5, and found on one; TYRE is missed.
    assert counts == {BRAKE: (1, 2, 0), TYRE: (0, 0, 1)}


def test_the_ones_add_up_for_both_baselines(con, tmp_path):
    rows = _rows(
        tmp_path,
        [
            (4, [BRAKE, TYRE], [TYRE, HEADLAMP]),
            (4, [OTHER], [OTHER, BRAKE]),
            (7, [], [HEADLAMP]),
            (1, [MOTORCYCLE[0]], [MOTORCYCLE[0], BRAKE]),
        ],
    )
    ones = baselines.label_ones(con, rows)
    assert ones == {TYRE: 1, HEADLAMP: 2, OTHER: 1, BRAKE: 1, MOTORCYCLE[0]: 1}
    for counts in (baselines.repeat(con, rows), baselines.most_popular(con, rows, [HEADLAMP])):
        baselines.check("toy", 2025, counts, ones)


def test_check_stops_when_the_ones_do_not_add_up():
    with pytest.raises(SystemExit):
        baselines.check("toy", 2025, {1: (1, 0, 0)}, {1: 2})


def test_lists_are_read_in_rank_order(tmp_path):
    path = tmp_path / "most_popular.csv"
    path.write_text(
        "list_year,k,list_rank,entry,slots_with_entry,slots_in_year\n"
        "2024,2,2,7,10,100\n"
        "2024,2,1,3,20,100\n"
    )
    assert baselines.lists(path) == {2024: [3, 7]}
