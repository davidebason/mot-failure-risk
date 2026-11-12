"""Converting the CSVs to Parquet: the reading per archive, the counts, the values, the check.

Nothing here touches Azure: the CSVs are written in the test, one per way the files are read, and
converted from a temporary folder laid out as data/extracted/ is.
"""

import duckdb
import pytest

from motrisk import convert

HEADER = "test_id,make,model,test_mileage"
# The same three vehicles in each of the three ways the files are written: a comma inside a
# value, an inch mark inside one, a mileage written with a decimal, and an empty mileage.
WRITTEN = {
    # Comma-separated, a quote inside a quoted value escaped by a backslash: 2018 to 2020, 2024 on.
    "dft_test_result_2019": (
        HEADER + "\n"
        '1,LAND ROVER,"SERIES 1, 80 INCH",071614.0\n'
        '2,LAND ROVER,"SWB 88\\"",\n'
        "3,FORD,FIESTA,52000\n"
    ),
    # Comma-separated, a quote inside a quoted value doubled: the 2021 results.
    "dft_test_result_2021": (
        '"test_id","make","model","test_mileage"\n'
        '1,"LAND ROVER","SERIES 1, 80 INCH","071614.0"\n'
        '2,"LAND ROVER","SWB 88""",\n'
        '3,"FORD","FIESTA","52000"\n'
    ),
    # `|`-separated, no quoting at all: 2022 and 2023.
    "dft_test_result_2022": (
        "test_id|make|model|test_mileage\n"
        "1|LAND ROVER|SERIES 1, 80 INCH|071614.0\n"
        '2|LAND ROVER|SWB 88"|\n'
        "3|FORD|FIESTA|52000\n"
    ),
}
VALUES = [
    ("1", "LAND ROVER", "SERIES 1, 80 INCH", "071614.0"),
    ("2", "LAND ROVER", 'SWB 88"', None),
    ("3", "FORD", "FIESTA", "52000"),
]


@pytest.fixture
def extracted(tmp_path):
    """A folder laid out as data/extracted/: one archive folder per way of writing, one CSV each."""
    root = tmp_path / "extracted"
    for archive, text in WRITTEN.items():
        (root / archive).mkdir(parents=True)
        (root / archive / "part.csv").write_text(text)
    return root


@pytest.mark.parametrize(
    ("archive", "options"),
    [
        ("lookup", "delim = '|', quote = ''"),
        ("dft_test_item_2022", "delim = '|', quote = ''"),
        ("dft_test_result_2023", "delim = '|', quote = ''"),
        ("dft_test_result_2021", "delim = ',', quote = '\"', escape = '\"'"),
        ("dft_test_item_2021", "delim = ',', quote = '\"', escape = '\\'"),
        ("dft_test_result_2018", "delim = ',', quote = '\"', escape = '\\'"),
        ("dft_test_result_extracts_2025", "delim = ',', quote = '\"', escape = '\\'"),
    ],
)
def test_reading_follows_the_archive(archive, options):
    assert convert.reading(archive) == options


def test_expected_rows_reads_each_files_line(tmp_path):
    log = tmp_path / "run.log"
    log.write_text(
        "file   bytes columns rows skipped\n"
        "a/one.csv   1,000   5   18,172,242   0\n"
        "lookup/two.csv   146   2   6   0\n"
        "b/three.csv   500 not read: some error\n"
        "files: 2, bytes: 1,146, rows read: 18,172,248, rows skipped: 0, problems: 1\n"
    )
    assert convert.expected_rows(log) == {"a/one.csv": 18_172_242, "lookup/two.csv": 6}


def test_every_way_of_writing_gives_the_same_text(extracted, tmp_path):
    out = tmp_path / "parquet"
    expected = {f"{archive}/part.csv": 3 for archive in WRITTEN}
    con = duckdb.connect()
    assert convert.to_local(con, extracted, out, [], expected) == 3
    for archive in WRITTEN:
        path = out / archive / "part.parquet"
        columns = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
        assert [c[0] for c in columns] == HEADER.split(",")
        assert {c[1] for c in columns} == {"VARCHAR"}
        rows = con.execute("SELECT * FROM read_parquet(?) ORDER BY 1", [str(path)]).fetchall()
        assert rows == VALUES


def test_a_file_whose_rows_differ_from_the_count_is_not_kept(extracted, tmp_path, capsys):
    out = tmp_path / "parquet"
    expected = {"dft_test_result_2019/part.csv": 4}
    kept = convert.to_local(duckdb.connect(), extracted, out, ["dft_test_result_2019"], expected)
    assert kept == 0
    assert not (out / "dft_test_result_2019" / "part.parquet").exists()
    assert "evidence/09 counted 4" in capsys.readouterr().out


def test_only_the_archives_named_are_converted(extracted, tmp_path):
    out = tmp_path / "parquet"
    expected = {f"{archive}/part.csv": 3 for archive in WRITTEN}
    kept = convert.to_local(duckdb.connect(), extracted, out, ["dft_test_result_2022"], expected)
    assert kept == 1
    assert [p.parent.name for p in out.glob("*/*.parquet")] == ["dft_test_result_2022"]


def test_an_archive_not_present_stops_the_run(extracted, tmp_path):
    with pytest.raises(SystemExit, match="Not found: dft_test_result_2099"):
        convert.to_local(duckdb.connect(), extracted, tmp_path, ["dft_test_result_2099"], {})
