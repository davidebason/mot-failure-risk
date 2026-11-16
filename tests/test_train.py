"""Training: the folds, the tiers, the tally, the shuffle, the counts, and the full models' inputs.

The rows are invented and written in the test as data/training_rows/ is, one Parquet file per
target year; entries and classes come from the seed, and the groups are given here, since the
lookup tables are not in the repository.
"""

import collections
import csv

import duckdb
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from motrisk import baselines, folds, full_models, small_models


def _entries_of(classes: str) -> list[int]:
    with open(baselines.ENTRIES, newline="") as f:
        return [int(r["entry"]) for r in csv.DictReader(f) if r["classes"] == classes]


CAR = _entries_of("3 4 5 7")[:6]
MOTORCYCLE = _entries_of("1 2")[:2]
GROUP = {**{e: 101 for e in CAR[:3]}, **{e: 102 for e in CAR[3:]}, **dict.fromkeys(MOTORCYCLE, 103)}
YEARS = (2019, 2020, 2021)
PAIRS = [("FORD", "FIESTA"), ("FORD", "FOCUS"), ("VAUXHALL", "CORSA")]


def _year(rng, year: int, n: int) -> list[dict]:
    """Invented rows of one target year: a car or a motorcycle, its last slot and its label."""
    rows = []
    for i in range(n):
        motorcycle = rng.random() < 0.2
        cls = 1 if motorcycle else int(rng.choice([4, 7]))
        pool = MOTORCYCLE if motorcycle else CAR
        previous = sorted({int(e) for e in rng.choice(pool, size=rng.integers(0, 3))})
        # A problem recorded before is likelier again, so the models have something to learn.
        label = sorted(
            {e for e in previous if rng.random() < 0.5}
            | {int(e) for e in pool if rng.random() < 0.1}
        )
        make, model = PAIRS[i % 3] if year < 2021 or i % 7 else ("TESLA", "MODEL 3")
        rows.append(
            {
                "vehicle_id": year * 10_000 + i,
                "target_start": f"{year}-06-{1 + i % 28:02d}",
                "target_year": year,
                "test_class_id": cls,
                "fuel_type": "PE" if i % 4 else "DI",
                "make": make,
                "model": model,
                "test_mileage": int(rng.integers(1_000, 200_000)),
                "age_years": float(rng.uniform(3, 20)),
                "cylinder_capacity": int(rng.integers(600, 3_000)),
                "weeks_between": float(rng.choice([52, 50, 60, 104])) + year - 2019,
                "previous_entries": previous,
                "previous_group_ids": sorted({GROUP[e] for e in previous}),
                "label_entries": label,
            }
        )
    return rows


@pytest.fixture
def toy(tmp_path, monkeypatch):
    """A folder of invented training rows, and a connection that knows the entries' groups."""
    rng = np.random.default_rng(7)
    root = tmp_path / "training_rows"
    root.mkdir()
    for year in YEARS:
        rows = _year(rng, year, 400)
        con = duckdb.connect()
        con.execute(
            """CREATE TABLE t (vehicle_id BIGINT, target_start DATE, target_year INTEGER,
               test_class_id INTEGER, fuel_type VARCHAR, make VARCHAR, model VARCHAR,
               test_mileage INTEGER, age_years DOUBLE, cylinder_capacity INTEGER,
               weeks_between DOUBLE, previous_entries INTEGER[], previous_group_ids INTEGER[],
               label_entries INTEGER[])"""
        )
        con.executemany(
            "INSERT INTO t VALUES (" + ", ".join("?" * 14) + ")", [list(r.values()) for r in rows]
        )
        con.execute(f"COPY t TO '{root / f'{year}.parquet'}' (FORMAT parquet)")
    monkeypatch.setattr(folds, "ROWS", root)
    monkeypatch.setattr(small_models, "COUNTS", tmp_path / "counts")
    con = baselines.connect(memory_limit="1GB")
    con.execute("CREATE TABLE entry_groups (entry INTEGER, group_id INTEGER)")
    con.executemany("INSERT INTO entry_groups VALUES (?, ?)", list(GROUP.items()))
    return con


def test_the_tier_rule():
    # Full at ten ones per weight of the full model, small at ten per weight of the small one.
    d = 100
    assert folds.tier(1010, d) == "full"
    assert [folds.tier(k, d) for k in (1009, 150)] == ["small", "small"]
    assert [folds.tier(k, d) for k in (149, 1, 0)] == ["base_rate", "base_rate", "none"]


def test_each_kind_of_vehicle_has_its_own_curve_across_the_bands():
    # Over 3 years: the same entry before; about a year: group only; 1 to 2 years: neither.
    x = small_models.small_inputs([1, 0, 0], [1, 1, 0], [2000, 365, 500])
    names = small_models.SMALL_WEIGHTS
    assert x.shape == (3, folds.SMALL_INPUTS) and len(names) == folds.SMALL_INPUTS
    on = [{names[j] for j in np.flatnonzero(row)} for row in x]
    assert on[0] == {"w_u", "w_g", "w_band4", "w_u_band4"}
    assert on[1] == {"w_g"}
    assert on[2] == {"w_band2"}


def test_the_tally_and_its_bands():
    tp, fp, fn, band_rows, band_ones = folds.tally([0.2, 0.5, 1.0], [10, 5, 2], [1, 3, 2])
    assert (tp, fp, fn) == (5, 2, 1)
    assert (band_rows[20], band_rows[50], band_rows[99]) == (10, 5, 2)
    assert (band_ones[20], band_ones[50], band_ones[99]) == (1, 3, 2)
    folds.check_tally(0, tp, fp, fn, band_rows, band_ones, 17, 6)
    with pytest.raises(SystemExit):
        folds.check_tally(0, tp + 1, fp, fn, band_rows, band_ones, 17, 6)


def test_the_shuffle_keeps_each_class_labels_and_moves_them(toy):
    def labels(shuffled):
        return toy.execute(
            f"""SELECT vehicle_id, test_class_id, label_entries
                FROM ({folds.rows_sql(2019, shuffled)}) ORDER BY vehicle_id"""
        ).fetchall()

    own, moved = labels(False), labels(True)

    def by_class(rows):
        return collections.Counter((cls, tuple(label)) for _, cls, label in rows)

    assert by_class(own) == by_class(moved)
    assert [r[0] for r in own] == [r[0] for r in moved]
    assert sum(a[2] != b[2] for a, b in zip(own, moved, strict=True)) > len(own) / 2
    assert moved == labels(True)


def test_the_counts_are_every_row_grouped(toy):
    out = small_models.count_year(toy, 2019, False)
    for e in [*CAR, *MOTORCYCLE]:
        r = small_models.every_row(toy, e, 2019)
        brute = collections.Counter(
            zip(
                r["u"].tolist(),
                r["g"].tolist(),
                r["days_between"].tolist(),
                r["y"].tolist(),
                strict=True,
            )
        )
        got = toy.execute(
            f"SELECT u, g, days_between, y, n FROM read_parquet('{out}') WHERE entry = {e}"
        ).fetchall()
        assert {(u, g, d, y): n for u, g, d, y, n in got} == dict(brute)


def test_a_fit_on_counts_is_the_fit_on_every_row(toy):
    small_models.count_year(toy, 2019, False)
    c = small_models.cells(toy, [2019], False)
    e = CAR[0]
    s = small_models.by_entry(c)[e]
    r = small_models.every_row(toy, e, 2019)
    a = small_models.fit_counts(r["u"], r["g"], r["days_between"], r["y"], np.ones(len(r["y"])))
    b = small_models.fit_counts(c["u"][s], c["g"][s], c["days_between"][s], c["y"][s], c["n"][s])
    assert np.allclose(np.r_[a.intercept_, a.coef_[0]], np.r_[b.intercept_, b.coef_[0]], atol=1e-6)


def test_the_full_inputs_come_from_the_training_years_only(toy):
    cols = full_models.prepare(toy, 2021)
    assert cols["d"] == small_models.fold_inputs(toy, 2021)
    files = [str(folds.ROWS / f"{y}.parquet") for y in (2019, 2020)]
    train = toy.execute(f"SELECT test_mileage, age_years FROM read_parquet({files})").fetchnumpy()
    assert np.isclose(cols["scaling"][0, 0], train["test_mileage"].mean())
    assert np.isclose(cols["scaling"][1, 1], train["age_years"].std())

    x, classes, label_rows, label_entries = full_models.design(toy, [2019, 2020], False, cols)
    rows = toy.execute(f"SELECT * FROM ({folds.rows_sql(2019, False)})").fetchall()
    first = dict(zip([c[0] for c in toy.description], rows[0], strict=True))
    dense = x[0].toarray()[0]
    set_columns = set(np.flatnonzero(dense))
    assert set(first["previous_entries"]) <= set_columns
    assert all(
        full_models.N_ENTRIES + sorted(set(GROUP.values())).index(g) in set_columns
        for g in first["previous_group_ids"]
    )
    z = (first["test_mileage"] - cols["scaling"][0, 0]) / cols["scaling"][0, 1]
    assert np.isclose(dense[cols["first_number"]], z, atol=1e-5)
    kept = full_models.KEPT[folds.gap_band(first["days_between"])]
    crossed = len(first["previous_entries"]) if kept >= 0 else 0
    banded = 1 if kept >= 0 else 0
    assert len(set_columns) == (
        len(first["previous_entries"]) + len(first["previous_group_ids"]) + crossed + 3 + 3 + banded
    )
    assert classes[0] == first["test_class_id"]


def test_the_entries_are_crossed_with_the_band_of_the_gap(toy):
    cols = full_models.prepare(toy, 2021)
    x, *_ = full_models.design(toy, [2019, 2020], False, cols)
    # Year by year, in the order the matrix is built: a UNION would not keep the years in order.
    rows = [
        r
        for year in (2019, 2020)
        for r in toy.execute(
            f"SELECT previous_entries, days_between FROM ({folds.rows_sql(year, False)})"
        ).fetchall()
    ]
    n_kept = len(folds.BANDS_KEPT)
    seen_off = 0
    for i, (previous, days) in enumerate(rows):
        kept = int(full_models.KEPT[folds.gap_band(days)])
        set_columns = set(x[i].indices)
        crossed = {
            c
            for c in set_columns
            if cols["entry_band"] <= c < cols["entry_band"] + full_models.N_ENTRIES * n_kept
        }
        bands = {c for c in set_columns if c >= cols["first_band"]}
        if kept < 0:
            assert not crossed and not bands
        else:
            seen_off += 1
            assert crossed == {cols["entry_band"] + e * n_kept + kept for e in previous}
            assert bands == {cols["first_band"] + kept}
        assert list(x[i].indices) == sorted(x[i].indices)
    assert seen_off > 0

    # A make and model first seen in the test year has no column there.
    x_test, *_ = full_models.design(toy, [2021], False, cols)
    test_rows = toy.execute(
        f"""SELECT make, len(previous_entries), len(previous_group_ids)
            FROM ({folds.rows_sql(2021, False)})"""
    ).fetchall()
    test_days = [
        d
        for (d,) in toy.execute(
            f"SELECT days_between FROM ({folds.rows_sql(2021, False)})"
        ).fetchall()
    ]
    tesla = [i for i, r in enumerate(test_rows) if r[0] == "TESLA"]
    assert tesla
    pair_columns = set(range(cols["first_number"] - len(PAIRS), cols["first_number"]))
    for i in tesla:
        _, previous, groups = test_rows[i]
        # Its entries, groups, crossed entries, class, fuel, numbers and band: no pair.
        kept = full_models.KEPT[folds.gap_band(test_days[i])]
        assert x_test[i].nnz == previous + groups + (previous + 1) * (kept >= 0) + 2 + 3
        assert not set(x_test[i].indices) & pair_columns


def test_rows_of_other_classes_weigh_nothing(toy):
    cols = full_models.prepare(toy, 2021)
    x, classes, label_rows, label_entries = full_models.design(toy, [2019, 2020], False, cols)
    e = CAR[1]
    y = full_models.labels(label_rows, label_entries, x.shape[0], e)
    car = classes != 1
    # In 64-bit floats and run to a tight tolerance, so that only the weights could differ.
    x = x.astype(np.float64)
    fit = dict(C=1.0, tol=1e-12, max_iter=10_000)
    weighted = LogisticRegression(**fit).fit(x, y, sample_weight=car.astype(np.float64))
    subset = LogisticRegression(**fit).fit(x[car], y[car])
    assert np.allclose(weighted.coef_, subset.coef_, atol=1e-6)
    assert np.isclose(weighted.intercept_[0], subset.intercept_[0], atol=1e-6)


def test_a_warm_start_ends_where_a_cold_one_does(toy):
    cols = full_models.prepare(toy, 2021)
    x, classes, label_rows, label_entries = full_models.design(toy, [2019, 2020], False, cols)
    x = x.astype(np.float64)
    y = full_models.labels(label_rows, label_entries, x.shape[0], CAR[0])
    fit = dict(C=1.0, tol=1e-10, max_iter=10_000)
    cold = LogisticRegression(**fit).fit(x, y)
    warm = LogisticRegression(warm_start=True, **fit)
    rng = np.random.default_rng(1)
    warm.coef_ = cold.coef_ + rng.normal(0, 0.5, cold.coef_.shape)
    warm.intercept_ = cold.intercept_ + 1.0
    warm.fit(x, y)
    assert np.allclose(warm.coef_, cold.coef_, atol=1e-5)
    assert np.isclose(warm.intercept_[0], cold.intercept_[0], atol=1e-5)


def test_the_weights_carry_over_column_by_column(tmp_path):
    # The previous fold had pairs A, B, C; this one B, D, C, A, and one column more for D.
    n_tail = len(folds.NUMBERS) + len(folds.BANDS_KEPT)
    first_pair = 10
    old_pairs = [("A", "1"), ("B", "1"), ("C", "1")]
    new_pairs = [("B", "1"), ("D", "1"), ("C", "1"), ("A", "1")]
    old_d = first_pair + len(old_pairs) + n_tail
    w = np.arange(old_d, dtype=np.float32) + 1
    path = tmp_path / "previous.npz"
    np.savez(
        path,
        entries=np.array([5]),
        coef=w[None, :],
        intercept=np.array([-3.0]),
        pair_makes=np.array([m for m, _ in old_pairs]),
        pair_models=np.array([m for _, m in old_pairs]),
        first_pair=first_pair,
        first_number=first_pair + len(old_pairs),
        d=old_d,
    )
    cols = {
        "pairs": new_pairs,
        "first_pair": first_pair,
        "first_number": first_pair + len(new_pairs),
        "d": first_pair + len(new_pairs) + n_tail,
    }
    start, intercept = full_models.carried(path, cols)[5]
    assert intercept == -3.0
    assert np.array_equal(start[:first_pair], w[:first_pair])
    pair_part = start[first_pair : first_pair + len(new_pairs)]
    # B was column 1 of the pairs, C column 2, A column 0; D is new.
    assert list(pair_part) == [w[first_pair + 1], 0.0, w[first_pair + 2], w[first_pair]]
    assert np.array_equal(start[cols["first_number"] :], w[first_pair + len(old_pairs) :])


def test_nothing_carries_over_without_a_previous_fold(tmp_path):
    assert full_models.carried(tmp_path / "missing.npz", {"first_pair": 0}) == {}
