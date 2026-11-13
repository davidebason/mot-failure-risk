# Data

Every source, unit and cleaning decision, recorded as it is made.

## Sources

### Anonymised MOT tests and results

Every MOT test carried out in Great Britain since 2005, anonymised, together with the defects and advisories each test recorded. Published under the UK Open Government Licence (OGL).

The **MOT test** is the periodic roadworthiness and environmental check required of cars, light goods vehicles, motorcycles and some passenger vehicles once they pass a prescribed age, at least once a year from then on. Tests are carried out by garages and some local authorities authorised by DVSA, known as **Vehicle Testing Stations**. Most vehicles take their first test at three years; taxis, ambulances and passenger vehicles with nine or more seats at one year. The vehicle classes, and the age at which each is first tested, are tabled under "Test Classes" in the user guide.

**One dataset, two publishers.** The Department for Transport (DfT) published the years 2005 to 2023, catalogued on data.gov.uk as [`anonymised_mot_test`](https://ckan.publishing.service.gov.uk/dataset/anonymised_mot_test), with the files at `data.dft.gov.uk`. The Driver and Vehicle Standards Agency (DVSA) publishes from 2023 onwards, catalogued as [`anonymised-mot-tests-and-results`](https://ckan.publishing.service.gov.uk/dataset/anonymised-mot-tests-and-results) and on its own portal, [open.data.dvsa.gov.uk/mot-anonymised](https://open.data.dvsa.gov.uk/mot-anonymised/index.html). The portal is the only place the 2025 files appear: they were added on 22 June 2026, together with a second release of 2024.

**Documentation.** Two user guides, one for [tests before May 2018](https://edh-dvsa-data-gov-uk-files-prod.s3.eu-west-1.amazonaws.com/DfT+MOT+Anonymised+Data+Set+Content+2.docx) and one for [tests after](https://edh-dvsa-data-gov-uk-files-prod.s3.eu-west-1.amazonaws.com/mot-testing-data-user-guide-v5.1.odt), version 5.1. The second describes the files up to 2023 and not the layout used from 2024, which is described below from the files themselves.

#### The files

Each year is published as two files, **test results** and **failure items**, plus one set of lookup tables shared by all years. The layout has changed three times. Every size, compression method and header below is produced by [`evidence/01_source_files.py`](evidence/01_source_files.py), which reads the files over HTTP without downloading them in full, and, for the files downloaded, by [`evidence/03_archive_layout.py`](evidence/03_archive_layout.py), which reads the copies in `data/raw/`.

| Years | Container | Inside | Separator | Columns |
|---|---|---|---|---|
| 2005 to 2016 | gzip, `.txt.gz` | one file per table per year | `\|` | old set |
| 2017 | ZIP | not checked, and not used | | |
| 2018 to 2020 | ZIP | four quarterly CSVs per table; in 2018 and 2019, also folder and `__MACOSX/` entries carrying no data | `,` | old set |
| 2021 | ZIP | twelve CSVs per table, of equal size rather than one a month; the header in double quotes, and in the first row every value but `test_id`, `vehicle_id`, `rfr_id` and `location_id` | `,` | old set |
| 2022 and 2023 | ZIP | one CSV per table; in the 2022 failure items, also a `__MACOSX/` entry carrying no data | `\|` | old set |
| 2024, first release, March 2025 | ZIP | twelve monthly CSVs per table, plus folder and `__MACOSX/` entries carrying no data | `,` | new set |
| 2024 and 2025, extracts, June 2026 | ZIP, stored without compression | twelve monthly CSVs per table | `,` | new set |

The **new column set** adds `completed_date` to both tables and renames the failure item's `location_id` to `mot_test_rfr_location_type_id`. Checked: 2016, the first release of 2024, and every file from 2018 on.

| File | Size | Inside |
|---|---|---|
| 2025 test results, extracts | 4,836 MB | 12 CSVs, stored, 312 to 475 MB each |
| 2025 failure items, extracts | 4,360 MB | 12 CSVs, stored, 287 to 442 MB each |
| 2024 test results, first release | 1,531 MB | 12 CSVs, deflate, 461 to 746 MB each uncompressed |
| 2024 failure items, first release | 680 MB | 12 CSVs, deflate, 321 to 522 MB each uncompressed |
| 2023 test results | 1,193 MB | one CSV, **Deflate64**, 3,661 MB uncompressed |
| 2023 failure items | 460 MB | one CSV, deflate, 1,978 MB uncompressed |
| 2022 test results | 1,165 MB | one CSV, **Deflate64**, 3,594 MB uncompressed |
| 2016 test results | 1,087 MB | gzip |
| 2016 failure items | 348 MB | gzip |
| Lookup tables, `lookup.zip` | under 1 MB | six `\|`-separated CSVs |

Every file from 2018 on, at its size as published. The extracts are stored without compression, which is why each of their years takes about 9 GB:

| Year | Test results | Failure items | Total |
|---|---|---|---|
| 2018 | 1,098 MB | 384 MB | 1,481 MB |
| 2019 | 1,114 MB | 412 MB | 1,527 MB |
| 2020 | 1,079 MB | 385 MB | 1,463 MB |
| 2021 | 1,246 MB | 631 MB | 1,876 MB |
| 2022 | 1,165 MB | 435 MB | 1,600 MB |
| 2023 | 1,193 MB | 460 MB | 1,653 MB |
| 2024, first release | 1,531 MB | 680 MB | 2,211 MB |
| 2024, extracts | 4,798 MB | 4,330 MB | 9,127 MB |
| 2025, extracts | 4,836 MB | 4,360 MB | 9,195 MB |

The years 2018 to 2021 are served only by the DfT server, which does not resume an interrupted download; 2022 onwards are also on the DVSA server, which does.

**The fetch.** The sixteen files used, results and failure items for 2018 to 2023 and the 2024 and 2025 extracts, were downloaded untouched into `data/raw/` on 31 October and 3 November 2026, 27.9 GB in all. The lookup tables, `lookup.zip`, followed on 4 November 2026. Each is logged with its size, SHA-256 and source URL in `data/raw/fetch_log.tsv`, and a copy of that log is committed as [`data/fetch_log.tsv`](data/fetch_log.tsv), so that the repository shows exactly which files every figure comes from.

**The copy in Azure.** We landed the same 17 files, untouched, in the Blob Storage container `raw` of the storage account `stmotrisk` on 7 November 2026, by [`src/motrisk/fetch.py`](src/motrisk/fetch.py) run on a virtual machine in Azure, so that each file went from the publisher's server straight into storage. The fetcher computes each file's SHA-256 from the bytes as it lands them, and stores it with the file together with the address it came from. Every file's size, SHA-256 and address match its line in `data/fetch_log.tsv`, and the container holds no other file, as [`evidence/08_azure_copy.py`](evidence/08_azure_copy.py) shows. The run's own record, one line per file, is [`data/fetch_run_2026-11-07.log`](data/fetch_run_2026-11-07.log).

**The CSVs.** We extracted the 106 CSVs of the 17 archives on 10 November 2026 with [`src/motrisk/extract.py`](src/motrisk/extract.py), into the container `csv` from the virtual machine, and into `data/extracted/`, which git ignores, locally. Each is named after its archive and its own name, without the folders inside the archive, such as `dft_test_item_2022/test_item.csv`; folder and `__MACOSX/` entries are left out. Each is kept only if it reads to its end, where its CRC-32 is checked, with as many bytes as the archive records. The run in Azure ran out of memory at the first Deflate64 archive and was resumed for the five left once [`src/motrisk/archives.py`](src/motrisk/archives.py) read Deflate64 in constant memory; its records are [`data/extract_run_2026-11-10.log`](data/extract_run_2026-11-10.log) and [`data/extract_run_2026-11-10_resumed.log`](data/extract_run_2026-11-10_resumed.log), and the local run's is [`data/extract_local_run_2026-11-10.log`](data/extract_local_run_2026-11-10.log). DuckDB reads every CSV in `csv` from Azure with the separator and quoting set out under "The files": 106 files, 51,450,661,681 bytes, 999,154,614 rows, none skipped for not splitting into as many values as their header has columns, as [`evidence/09_csv_from_azure.py`](evidence/09_csv_from_azure.py) shows in [`data/csv_from_azure_run_2026-11-10.log`](data/csv_from_azure_run_2026-11-10.log). The build reads them through Parquet copies, as set out under "Decisions". It runs in Azure until 21 November 2026, when the Azure credit ends, and the same build runs on a local copy.

**The Parquet files.** We converted the 106 CSVs to Parquet on 12 November 2026 with [`src/motrisk/convert.py`](src/motrisk/convert.py), on the virtual machine, from the container `csv` into the container `parquet`. Each CSV is read with the separator and quoting set out below, every column as text, and is kept only if the rows read, the rows stored and the rows [`evidence/09_csv_from_azure.py`](evidence/09_csv_from_azure.py) counted for it are equal. An empty value is stored as missing, and rows may be stored in another order, which carries no meaning. The run was killed for want of memory five files in, when a system service woke on the machine's 1 GiB, and was resumed for the rest with a swap file added; its records are [`data/convert_run_2026-11-12.log`](data/convert_run_2026-11-12.log) and [`data/convert_run_2026-11-12_resumed.log`](data/convert_run_2026-11-12_resumed.log). The container holds 106 Parquet files, 11,625,664,618 bytes, under a quarter of the CSVs, with 999,154,614 rows, each file's rows equal to evidence 09's count for its CSV, as [`evidence/11_parquet_in_azure.py`](evidence/11_parquet_in_azure.py) shows in [`data/parquet_in_azure_run_2026-11-12.log`](data/parquet_in_azure_run_2026-11-12.log). We converted the local copy the same day with the same script and the same check, from `data/extracted/` into `data/parquet/`, which git ignores; every file was kept, as its record [`data/convert_local_run_2026-11-12.log`](data/convert_local_run_2026-11-12.log) shows.

**The watcher.** Until 21 November 2026, an Azure Function, [`function/function_app.py`](function/function_app.py), runs [`src/motrisk/fetch_scheduled.py`](src/motrisk/fetch_scheduled.py) every day at 00:00 UTC. It reads DVSA's portal page and takes each file whose name starts with `dft_test_result` or `dft_test_item`, ends in `.zip` and holds a year from 2026 onward. It downloads each such file to compute its SHA-256, and lands in `raw`, as the fetcher above does, every one the container does not hold or holds with a different SHA-256.

**The 2022 and 2023 results files are compressed with Deflate64**, which Python's `zipfile` cannot open. We read them through [`src/motrisk/archives.py`](src/motrisk/archives.py), which reads Deflate64 with the `zipfile-deflate64` package and checks each member against the CRC-32 the archive records. Their header is the old column set, `|`-separated.

**From 2024, a value holding a comma is enclosed in double quotes, and a double quote inside it is escaped with a backslash.** Only `make` and `model` are affected, and only in the test results. In 2024, 202 of the 42,637,055 rows hold a comma inside a value, such as the model `"SERIES 1, 80 INCH"`, and 56 an escaped inch mark, such as `"SWB 88\""`; in 2025, 209 and 47 of the 42,728,066. The failure items of both years hold no double quote at all. Read with `"` as the quote character and `\` as the escape, every row of both years that holds a double quote splits into as many values as its header has columns. We set both characters explicitly when the files are read, rather than leave them to DuckDB's automatic detection, which missed the quoting in January 2025: that month's first quoted row is on line 57,369. These counts are produced by [`evidence/02_csv_quoting.py`](evidence/02_csv_quoting.py).

**The older comma-separated results quote the same way, except those of 2021.** In 2018 to 2020, a value holding a comma is enclosed in double quotes and a double quote inside it is escaped with a backslash, as from 2024: read that way, every row of the three years that holds a double quote splits into as many values as its header has columns, while doubled quotes, the CSV standard, misread 138, 100 and 71 rows. The 2021 results enclose most values in double quotes and double a quote inside one: read that way, every row splits correctly, and one row is misread with a backslash as the escape. Only `make` and `model` hold a comma, in 300, 272, 171 and 195 rows of 2018 to 2021. The failure items of 2018 to 2021 split correctly under either reading. The `|`-separated files of 2022 and 2023 need no quoting at all: their failure items hold no double quote, and the 32 and 40 double quotes in their results, among 41,632,878 and 42,216,721 rows, sit inside values, so every row splits correctly on the separator alone. We therefore read the 2021 results with doubled quotes, every other comma-separated file with a backslash as the escape, and the `|`-separated files on the separator alone. These counts are produced by [`evidence/06_csv_quoting_2018_2023.py`](evidence/06_csv_quoting_2018_2023.py).

#### Test results: one row per test

| Column | Meaning |
|---|---|
| `test_id` | the test; primary key |
| `vehicle_id` | the vehicle, the same across all its tests, derived by the publisher from the registration and the VIN |
| `test_date` | date of the test |
| `test_class_id` | vehicle class tested: 1 and 2 motorcycles, 3 light three-wheelers, 4 cars and light vans, 5 passenger vehicles with thirteen or more seats, 7 goods vehicles of 3,000 to 3,500 kg |
| `test_type` | `NT` normal test, `RT` re-test, `PL` and `PV` partial retests, `ES` statutory appeal; decoded by `mdr_test_type` |
| `test_result` | `P` pass, `F` fail, `PRS` pass after rectification at the station, `ABA` abandoned, `ABR` aborted; decoded by `mdr_test_outcome` |
| `test_mileage` | odometer reading in miles, as entered or validated by the tester; zero or blank where none was taken |
| `postcode_area` | postcode area of the testing station, such as `OX` |
| `make`, `model` | as held in DVSA's vehicle dataset |
| `colour` | as entered or validated by the tester |
| `fuel_type` | fuel code, such as `PE` petrol or `DI` diesel, as entered or validated by the tester; decoded by `mdr_fuel_types` |
| `cylinder_capacity` | engine size, as entered or validated by the tester; the guide states no unit, and values such as 1600 read as cubic centimetres |
| `first_use_date` | the vehicle's date of first use |
| `completed_date` | from 2024 only: when the test was completed, as a UTC timestamp; not described in the guide |

**PRS** is a test that begins in a failing condition and is put right within one hour, before the result is entered, so it is recorded as a pass of a vehicle that arrived failing. DVSA accordingly reports two failure rates: an **initial failure rate** that counts PRS as a failure, and a **final failure rate** that does not. Both are defined under "Comparison with DVSA published statistics" in the user guide.

#### Failure items: one row per defect or advisory recorded in a test

| Column | Meaning |
|---|---|
| `test_id` | the test it was recorded in; many items to one test, and none for a clean pass |
| `rfr_id` | the defect, as a **reason for rejection** (RfR) code; decoded by `item_detail`, together with the test's `test_class_id` |
| `rfr_type_code` | `F` failure, `P` failure rectified at the station, `A` advisory, `M` minor defect |
| `location_id`, from 2024 `mot_test_rfr_location_type_id` | where on the vehicle, by side, end and position; decoded by `mdr_rfr_location` |
| `dangerous_mark` | the tester's mark that a failure was dangerous, used until 19 May 2018 |
| `completed_date` | from 2024 only: when the test was completed, as on the test result |

An **advisory** is a tester's warning about an item that does not fail the test.

#### The lookup tables

The two main tables store codes, not descriptions. The lookup tables translate them, and two of them carry information found nowhere else.

| File | Rows | What it holds |
|---|---|---|
| `item_detail.csv` | 21,069 | one row per defect code per vehicle class: its description, its advisory wording, its **severity** under the 2018 rules, and the group it belongs to |
| `item_group.csv` | 4,136 | the defect groups (brakes, lighting, …) as a tree: each group names its parent, up to `Vehicle` at the top |
| `mdr_rfr_location.csv` | 129 | location code → side, end and position on the vehicle |
| `mdr_fuel_types.csv` | 14 | fuel code → fuel name |
| `mdr_test_outcome.csv` | 7 | result code → outcome |
| `mdr_test_type.csv` | 6 | test type code → kind of test |

Severity and grouping are the two found nowhere else: whether a failure was major or dangerous, and that two different defect codes concern the same part of the vehicle, are recorded only in `item_detail` and `item_group`.

**Every coded column takes its values from a finite list.** `test_type` has the 6 codes of `mdr_test_type` and `test_result` the 7 of `mdr_test_outcome`; three of those the guide does not describe: `EI` inverted appeal, `ABRVE` aborted by VE, and `R` refused. `rfr_type_code` has 4 values, `F`, `P`, `A` and `M`. `item_detail` holds 7,505 distinct defect codes over 21,069 rows, because the guide defines a defect as a code together with a vehicle class, and a code is listed once for each class it applies to: 1,389 rows for class 1, 1,389 for class 2, 3,900 for class 3, 4,432 for class 4, 5,822 for class 5 and 4,137 for class 7. Of the 4,432 codes for class 4, 2,511 are categorised Pre-EU Directive, the codes used before 20 May 2018, and 1,921 belong to the 2018 rules: 1,196 major, 525 dangerous and 200 minor. These counts are produced by [`evidence/01_source_files.py`](evidence/01_source_files.py). Nine codes in the data files are not in the lookup, all recorded only in 2024 and 2025, on 21,709 and 347,008 items; this is produced by [`evidence/05_code_coverage.py`](evidence/05_code_coverage.py).

**Every code's group is listed, and a group number means the same group in every class.** Over all classes, 2,574 code numbers belong to the 2018 rules and 4,931 to the earlier ones, and no number is used by both. Every code-and-class row of `item_detail` finds its group in `item_group` for that class, and no group number carries another name or another parent in another class. Of the 2,574 codes of the 2018 rules, 2,557 are listed in more than one class, and each sits under the same group in every class, both directly above it and at the top of its path. The groups directly above those codes are 456, carrying 304 names: 92 names belong to more than one group, *Condition* and *Switch* to nine each, so a group is identified by its number, not its name. Between a code and `Vehicle` lie one to four groups for motorcycles, classes 1 and 2, and two to five for the other classes. These figures are produced by [`evidence/04_lookup_groups.py`](evidence/04_lookup_groups.py).

#### How the tables link

```
 test_result ──────────────── one row per test; test_id, vehicle_id, test_class_id, ...
      │  one test has zero or many items
      ▼
 test_item ────────────────── one row per defect or advisory; test_id, rfr_id, location id
      │  rfr_id from the item, test_class_id from its test
      ▼
 item_detail ──────────────── one row per defect code per vehicle class
      │  test_item_id, test_class_id
      ▼
 item_group ───────────────── the tree of defect groups; parent_id points at the parent

 test_item.location id      → mdr_rfr_location
 test_result.fuel_type      → mdr_fuel_types
 test_result.test_result    → mdr_test_outcome
 test_result.test_type      → mdr_test_type
```

### MOT History API

Not used so far. The [MOT History API](https://documentation.history.mot.api.gov.uk/mot-history-api/download-vehicle-mot-history-data) publishes a full snapshot every Sunday and a file of changes every day, each an archive of gzip-compressed JSON, one record per vehicle carrying its whole test history. Keys are issued only to approved applicants. It is the only source of the MOT data that updates more often than once a year.

## What the publisher says the data does and does not contain

From the post-2018 user guide, unless marked as from the portal.

- **A test describes the vehicle on the day of the test only.** The certificate is not evidence of its condition at any other time, of its general mechanical condition, or of full legal compliance.
- **Only tests that could have ended in a pass are included.**
- **2005 to March 2006 is incomplete**, because computerisation was not complete across Great Britain until 1 April 2006.
- **The rules changed on 20 May 2018**, when EU Directive 2014/45 introduced dangerous, major and minor defects. The portal warns that the change "affected the information presented in these datasets". The `dangerous_mark` used before it is not comparable with the later dangerous category.
- **The defect category was added from the 2022 data set** and has not been added to 2018 to 2021.
- **Mileage before 2022 is sometimes kilometres.** From 2022, readings taken in kilometres are converted to miles; earlier years are not corrected.
- **The location code is wrong in data sets up to 2021**, and correct from 2022.
- **Fuel type is often wrong for hybrids**, such as the Toyota Prius in the 2000s, recorded as some other fuel. Corrected from 2022 only.
- **An unknown date of manufacture is recorded as a first use of 1 January 1971**, so 1971 shows anomalies.
- **A small proportion of vehicles have make and model `UNCLASSIFIED`**, having no valid record in DVSA's vehicle dataset.
- **Postcode areas with fewer than five active testing stations are merged into `XX`**, so that no station can be identified.
- **Test class 0** marks duplicate or replacement certificates for tests made before computerisation.
- **Two years have been reissued** (portal): 2017 in June 2022, to add missing results, and 2022 in December 2023, to correct fuel type codes for a small number of vehicles.

## What the data can and cannot support

- **There is no vehicle table.** Make, model, fuel and first use are repeated on every test row, and `vehicle_id` is the only link between one vehicle's tests.
- **A failure item carries no vehicle class**, and `item_detail` is keyed on defect code and class together, so decoding a defect goes through the item's test.
- **The 2020 extension moved some tests by six months.** Cars, motorcycles and vans whose MOT was due between 30 March and 31 July 2020 were given a six-month extension, and testing became mandatory again for those due from 1 August 2020 ([Which?, 30 June 2020](https://www.which.co.uk/news/2020/06/government-cuts-short-mot-exemption-is-your-cars-mot-due)). A vehicle tested on the extension has a longer gap than a year between that test and the one before, and one due late in July could be put back to January 2021, leaving no test in 2020: a test due on 30 July 2020 was not needed until 30 January 2021. We build the rows of 2020 and 2021 as those of every other year. The model is given the weeks between the two slots, which records the longer interval, and nothing else is corrected. How many vehicles this affects is not yet measured.
- **Not in the data at all:** repairs made between tests, what any repair cost, which testing station carried out a test beyond its postcode area, the owner, and accidents.
- **The guide and the files disagree on format.** The guide gives dates as `DD-MM-YYYY` and every file as `|`-separated; the files checked carry ISO dates, `2016-01-01`, and those of 2018 to 2021 and from 2024 are comma-separated.
- **The 2024 first release is larger per month than the 2025 extracts**: 461 to 746 MB of test results a month uncompressed, against 312 to 475 MB. Whether that is more rows or a different formatting, such as mileage written as `71614.0`, is not yet checked.

## Decisions

### The three layouts are read into one, through Parquet

We convert each of the 106 CSVs once to a Parquet file. Each is read with the separator and quoting set out under "The files" above, and every column is kept as text, so that only the container changes and no value is reinterpreted. Each Parquet file is checked to hold exactly the rows [`evidence/09_csv_from_azure.py`](evidence/09_csv_from_azure.py) counted for its CSV. The build then reads the test results of every year in one query and the failure items in another, into two staged tables with the same columns for every year. The new column set's added and renamed columns are among those dropped below. The cleaning rules below are stated on values rather than on years, so they apply to every year alike.

### Every row of the files is accounted for

We built the staged tables over every year on 12 November 2026, with dbt on the Azure virtual machine, resized to 4 vCPUs and 32 GB, from the container `parquet` downloaded to its disk. Every row of the files is either kept or removed by exactly one rule, each counted on its own, and the counts add up to the rows of the files, as the model [`staging_row_counts`](transform/models/staging/staging_row_counts.sql) records in [`data/staging_row_counts_2026-11-12.log`](data/staging_row_counts_2026-11-12.log). A row that meets several rules is counted under the first, in the order of [`transform/macros/classified.sql`](transform/macros/classified.sql), which is why the counts of the bounds differ slightly from those of evidence 13.

| Table | Kept, or removed because | Rows |
|---|---|---|
| tests | kept | 308,127,375 |
|  | before 20 May 2018 | 15,665,371 |
|  | aborted, `ABR` | 1,598,012 |
|  | engine size outside its class's range | 341,084 |
|  | age at the test over 50 years | 249,746 |
|  | abandoned, `ABA` | 189,605 |
|  | mileage above 900,000 | 10,451 |
|  | aborted by a vehicle examiner, `ABRVE` | 234 |
|  | **total, the rows of the files** | **326,181,878** |
| failure items | kept | 633,027,171 |
|  | of a removed test | 30,820,336 |
|  | on a code not kept | 9,074,846 |
|  | on a code not listed for its vehicle's class | 24,846 |
|  | whose test is in no file | 175 |
|  | recorded in a way the rules exclude | 1 |
|  | **total, the rows of the files** | **672,947,375** |

**A failure item whose test is in no file is removed.** 175 items belong to tests that appear in no results file of any year; with no vehicle, date or class, they cannot be placed in any slot.

Every test of the build passes, as its records show: [`data/dbt_build_run_2026-11-12.log`](data/dbt_build_run_2026-11-12.log), [`data/dbt_retry_run_2026-11-12.log`](data/dbt_retry_run_2026-11-12.log) and [`data/dbt_items_run_2026-11-12.log`](data/dbt_items_run_2026-11-12.log). The first run filled the machine's disk with temporary files when four steps ran at once, and its failed steps were rerun one at a time; the third run rebuilt the failure items once those whose test is in no file had a rule of their own. 156,701 vehicles are tested in more than one class, reported as a warning, since each test's class is kept as recorded.

### Tests from 20 May 2018 to 31 December 2025

We use tests from 20 May 2018, the day the 2018 rules came into force, to the end of 2025, the latest year published. The recent years describe modern cars and the current test, and starting on that date puts every test under one set of rules and one list of defect codes: for class 4, the 1,921 codes of the 2018 rules, rather than those and the 2,511 used before them. The tests of 1 January to 19 May 2018 are in the 2018 files and are excluded. The period cannot start earlier: none of the 29,051,275 failure items recorded before 20 May 2018 carries a code of the 2018 rules. These counts, and those of the next section, are produced by [`evidence/05_code_coverage.py`](evidence/05_code_coverage.py), over all tests, aborted and abandoned ones included, since a failure item carries no test result.

### Which defect codes are kept: those in use from 2018 to 2025, renumbered ones joined

We keep, as data and as what the model predicts, the largest set of defects in use throughout the period. A defect is kept when it is first recorded in 2018, from 20 May, and last recorded in 2025; a year without a record in between is allowed, since a rare defect can miss a year by chance. A defect that starts later or stops earlier is dropped, in every year.

**Some defects changed code number during the period, and we join the two numbers into one.** The lookup links no old number to a new one, so we pair them ourselves. Two codes are one defect when they have the same category and are listed for the same vehicle classes, the old one is last recorded in the year the new one is first recorded or the year before, and either they have the same short description and the same group or the same inspection-manual wording, or they have the same group and manual wording and are the only two codes in the lookup with that group, wording and category. The manual wording alone does not identify a defect: 2,332 of the 2,574 codes share theirs with another code. The two rules find 40 pairs of codes, among them the lamps renumbered in 2019, the shock absorber's serious fluid leak in 2021, and the four *not tested* codes that became *unable to be tested* or *unable to be completed* in 2023. Each pair takes the number used first. Of the 40, 36 belong to defects kept under the rule below, and are the pairs in [`transform/seeds/code_dictionary.csv`](transform/seeds/code_dictionary.csv).

Of the 2,559 codes of the 2018 rules recorded from 20 May 2018, 168 are first recorded after 2018 and 159 last recorded before 2025. After joining, 2,305 defects are in use throughout and are kept; 218 codes are dropped, carrying between 1.0% and 1.5% of each year's failure items from 2019 and 2.8% of those of 2018 from 20 May. They include codes the 2018 rules split from an older one, such as the shock absorber's *negligible damping effect*, from 2021, and the lamp's *up to 1/2 not functioning*, from 2019. Fifteen codes are never recorded. Of the codes of the earlier rules, 739 are still recorded between 20 May and the end of 2018, and 16 from then on, in every year and only as advisories: the *Non-component advisories*, such as *Nail in tyre*, 3.5% to 4.2% of each year's items from 2019. Those 16 are kept, which makes 2,321 defects. The nine codes missing from the lookup are recorded only in 2024 and 2025, and are dropped.

**The build reads these rules from one place.** They are applied by [`src/motrisk/codes.py`](src/motrisk/codes.py), which writes the two dbt seeds the build reads: [`transform/seeds/code_dictionary.csv`](transform/seeds/code_dictionary.csv), each of the 2,357 kept codes with the defect it belongs to, numbered by the code used first, and [`transform/seeds/year_vector_entries.csv`](transform/seeds/year_vector_entries.csv), the 4,821 entries of the year vector in order, each with the vehicle classes its defect is listed for. The evidence file above imports the same rules, so the figures and the build cannot disagree.

### 2024 comes from the extracts

2024 is published twice. We use the extracts of June 2026, published together with 2025 and in the same layout, rather than the first release of March 2025. The first release holds more test-result bytes for the year than the extracts: each of its twelve monthly files is at least 461 MB uncompressed, against 4,798 MB for the extracts' whole year. Why is not yet checked.

### `dangerous_mark` is dropped, in every year

The guide says the tester's dangerous mark, used until 19 May 2018, is not directly comparable with the dangerous category the 2018 rules introduced. Keeping it would therefore not make the years before and after that date consistent with each other, so we drop it from the failure items of every year, including those before May 2018. Severity after 20 May 2018 remains available from `item_detail`; codes used before that date carry only "Pre-EU Directive" there.

### `completed_date` is dropped from both tables

The question is whether a car will fail its next test, and what bears on it is when the car was presented, which `test_date` records. When the test was completed adds nothing about the condition of the car, so we drop `completed_date` from the test results and the failure items. It exists only from 2024, so dropping it also leaves every year with the same date columns.

### What is kept from each file

From the test results we keep `test_id` and `vehicle_id`, which link the tables and separate the vehicles but are not given to the model, and `test_date`, `test_class_id`, `test_type`, `test_result`, `test_mileage`, `make`, `model`, `fuel_type`, `cylinder_capacity` and `first_use_date`. We drop `postcode_area` and `colour`, and `completed_date` as above. From the failure items we keep `test_id`, `rfr_id` and `rfr_type_code`, and drop the location and `dangerous_mark`. Without the location, a defect found at two places in one test gives two identical rows.

### Every vehicle class is used

We keep tests of every class, from motorcycles to goods vehicles of up to 3,500 kg, not cars alone. Each class has its own list of defect codes and its own age at first test, as set out under "The lookup tables" and "Test results: one row per test" above.

### Tests stopped before their end are removed

**The model predicts the problems a vehicle actually has, not how its tests end.** A test stopped before its end carries no information on the problem itself: it says only that this test did not finish, while we train the model to predict the vehicle's problems, which a fleet manager needs in order to decide which parts to inspect. The model does not predict that a test fails or is stopped. A vehicle whose test is stopped is normally tested again, and that complete test finds what is wrong, which is what the model aims to predict. A stopped test also leaves parts uninspected, and the absence of a record for them would read as nothing found. So we remove the three kinds of stopped test, with the failure items recorded in them:

- `ABR`, aborted because of a problem with the testing equipment or the tester, not with the vehicle;
- `ABA`, abandoned by the tester because it was unsafe to continue or because some items could not be inspected;
- `ABRVE`, aborted by a DVSA vehicle examiner, a result the user guide does not describe.

They are removed before the tests are grouped into slots (below), so they neither start nor extend one.

### What the model predicts: every problem recorded in the vehicle's next slot of tests

**We group each vehicle's tests into slots.** Its tests are taken in date order, with aborted and abandoned ones removed and every other type alike: normal tests, retests and appeals. A gap of more than 20 weeks between two consecutive tests starts a new slot. A failure and its retests, days apart, therefore stay in one slot, even across 1 January, while annual tests, about a year apart, fall in different slots. A retest more than 20 weeks after the test before it starts a new slot like any other test. A slot belongs to the year of its first test. The cutoff of 20 weeks falls in the sparse stretch between the two kinds of gap, as [`evidence/14_test_gaps.py`](evidence/14_test_gaps.py) shows on 5% of the vehicles in [`data/test_gaps_run_2026-11-12.log`](data/test_gaps_run_2026-11-12.log): 21.0% of consecutive tests are less than two weeks apart, the retests and repeated tests of one visit, and 64.5% are 46 to 58 weeks apart, the next annual test, while each four-week band from 8 to 24 weeks holds 0.28% to 0.39%. Moving the cutoff four weeks either way would move fewer than 0.4% of the pairs.

**A slot's first test is the one the vehicle arrives for, the moment of decision, so on a day with several tests we take the test completed first.** The files give only the day of a test, and `test_id` does not follow the order of the day. We therefore take the normal test first, then the lowest mileage, then the lowest `test_id`, since a retest follows the test it retests and an odometer only goes up. The files from 2024 on record when each test was completed: over a 5% sample of vehicles in 2024 and 2025, when a normal test and a test of another type fall on one vehicle's same day, the normal test was completed first in 297,173 of 298,458 pairs, and of two normal tests the lower mileage was completed first in 760 of 808 pairs where the mileages differ, while of all 300,045 pairs the lower `test_id` was completed first in 149,761 and later in 150,282, as [`evidence/16_same_day_tests.py`](evidence/16_same_day_tests.py) shows in [`data/same_day_tests_run_2026-11-12.log`](data/same_day_tests_run_2026-11-12.log). The order decides which test's details a row takes, and nothing else, since tests of one day are always in the same slot.

**Each slot is predicted from the slot before it.** The label is every problem recorded on any test of the slot: each defect code, together with the way it was recorded, as a failure, a failure rectified at the station, a minor defect or an advisory. The inputs are:
- the same record of the previous slot, however long before;
- the groups of that record: for each group directly above a kept defect's code, 1 if the previous slot recorded any entry in it, whatever the way;
- the vehicle's mileage and age at the target slot's first test, since both are known when the vehicle arrives for it, the moment of decision; and its other details as recorded at the previous slot's first test;
- the number of weeks between the first tests of the two slots.

**A row's class is that of the previous slot's first test**, since that slot is what the row learns from. When a vehicle's class differs between the two slots, which [`evidence/12_class_changes.py`](evidence/12_class_changes.py) finds for 0.33% of vehicles, a defect listed only for the target slot's class cannot be predicted for that row.

The prediction is made when the vehicle arrives for the target slot's first test, when that test's date is known. A vehicle's first slot serves only as input, and a vehicle with no later slot, whether scrapped, exported or off the road, gives no further row. A vehicle with more than one slot starting in a year has a row for each. The outcome of a test, `P`, `F`, `PRS` or `ABA`, is not predicted: what matters is the problems the vehicle had, not how its tests ended.

**Rows go to training or test by the year of the target slot's first test.** A slot that starts in December can hold a retest from the following January, so a fold's training rows can hold a few tests from the first weeks of its test year. None of them is a test label, since each belongs to a slot that starts before the test year. We accept this. At either end of the period a slot can be cut: a slot under way on 20 May 2018 loses its tests before that date, so a retest from 20 May starts the vehicle's first slot, and a slot that starts late in 2025 loses any test in 2026, which the data does not hold.

**The record is a list of 4,821 entries, each 0 or 1, one for each defect and way of recording it, and we keep only entries whose value is not fixed in advance.** The 2018 rules fix how a defect can be recorded: a dangerous or major defect fails the test, as a failure or as a failure put right at the station, and is never a minor defect; a minor defect is only ever a minor defect; an advisory is recorded only under a code that carries advisory wording; and the 16 earlier advisories only as advisories. That allows 4,961 of the 2,321 × 4 entries, and we leave the rest out. From 20 May 2018 to 2025, one item, in 2022, falls on a code of the 2018 rules in a way the rules exclude, and we remove it with the failure items. We also leave out the 140 allowed entries never recorded in the period, 125 of them failures put right at the station. These counts are produced by [`evidence/05_code_coverage.py`](evidence/05_code_coverage.py).

**A vehicle's class fixes which defects it can have.** No code of the 2018 rules is listed both for motorcycles, classes 1 and 2, and for another class, as [`evidence/04_lookup_groups.py`](evidence/04_lookup_groups.py) shows. An entry is therefore 0 for a vehicle whose class its defect is not listed for, and is learnt only from vehicles of the classes it is listed for: 1,251 entries for a motorcycle, 3,572 for a car or light van, class 4. An item on a code not listed for its vehicle's class is dropped.

**Each entry falls in one group, so that a defect has one group throughout the period, as it has one number.** The group is the one directly above the defect's code in `item_detail`, which is the same in every class (evidence 04). The 2,321 kept defects fall under 452 groups. A renumbered defect takes the group of the code it is numbered by, the code used first: 8 of the 36 renumbered pairs kept put their two codes under different groups, the six defects of the structure within 30 cm of a towbar mounting moving between two groups both named *Vehicle structure*, and the two of excessive corrosion of the structure or chassis from *Integral vehicle structure condition* to *Chassis condition*, as [`evidence/17_entry_groups.py`](evidence/17_entry_groups.py) shows in [`data/entry_groups_run_2026-11-12.log`](data/entry_groups_run_2026-11-12.log). The build reads each entry's group from [`int_entry_groups`](transform/models/intermediate/int_entry_groups.sql).

**We keep each test's class as recorded, although a vehicle's class sometimes changes, because the class is important data, noisy as it is.** It is the test's own record of what was checked: it fixes which defects can be recorded, and it separates versions of one model that make and model cannot, such as a Ford Transit van, minibus or heavier van, since the files record neither weight nor seats. The tester chooses it at each test, so some changes are recorded rather than real, and the data cannot tell which. Over the tests kept, 158,304 of 48,229,038 vehicles, 0.33%, change class at least once, in 169,568 changes. 99.5% of the changes come at a test more than 20 weeks after the one before, that is at the next annual test, and 146,128 of them are between classes 4 and 7, as [`evidence/12_class_changes.py`](evidence/12_class_changes.py) shows in [`data/class_changes_run_2026-11-12.log`](data/class_changes_run_2026-11-12.log).

### The vehicle columns, cleaned

The vehicle columns of each entry test are cleaned as below before they enter the model. The counts are over the normal tests of each year, aborted and abandoned ones removed, and are produced by [`evidence/07_vehicle_columns.py`](evidence/07_vehicle_columns.py).

- **Fuel is recorded by name as well as by code from 2024.** Beside the codes of `mdr_fuel_types`, 307,059 normal tests of 2024 carry `HYBRID ELECTRIC (CLEAN)` and 52,451 carry `ELECTRIC`, and 364,623 and 58,734 of 2025: the names that table gives `HY` and `EL`. We map each name to its code, ignoring case, so that one fuel is one value.
- **Missing mileage is blank before 2024 and zero from 2024.** It is blank on 0.25% to 0.32% of normal tests in every year from 2018 to 2023 but 2020, on 2.54% in 2020, and zero on 0.24% and 0.23% in 2024 and 2025, when none is blank. We treat both as missing. Readings taken in kilometres before 2022 cannot be told from miles, as "What the publisher says the data does and does not contain" sets out, and are kept as recorded.
- **Engine size is blank on about as many tests as are electric from 2022**: 128,625, 249,034, 460,692 and 740,156 in 2022 to 2025, against 121,717, 243,059, 455,169 and 735,598 tests with fuel `EL` or `ELECTRIC`, and on 0.15% to 0.25% of normal tests before 2022. It is zero on under 0.01% in every year. We treat blank and zero as missing, and leave the fuel code to say that a vehicle is electric.
- **Age is unknown where the first-use date is.** The first-use date is 1 January 1971, which the guide uses for an unknown date, on at most 0.03% of normal tests a year; it falls after the test on 6,392 in 2021 and on at most 10 in any other year; it is blank on at most 631. We treat all three as an unknown age.
- **A test with a value past one of the bounds below is removed, with its failure items, because filling the value in could compromise the training.** A row given the average in place of an extreme value, while its outcome reflects the extreme one, lowers that input's weight, and a correlated input takes up the difference; removing rows chosen by an input's value leaves the relation in the remaining rows intact. The cost is the tests removed, 601,281, 0.19% of the 308,728,656 kept (evidence 12), and, for engine size and age, whole vehicles, since those values repeat on every test of a vehicle: of the 190,149 vehicles with a test past a bound, 154,825 have every test past one and leave the data, as [`evidence/13_value_bounds.py`](evidence/13_value_bounds.py) shows in [`data/value_bounds_run_2026-11-12.log`](data/value_bounds_run_2026-11-12.log).
- **A test whose mileage is above 900,000 is removed.** The highest reading, 999,999, is probably the most the system can record, and readings that high stop meaning anything. Mileage means the same for every class, so one bound serves them all. It is set where it drops 0.1% of the buses' mileages, class 5, whose mileages run highest: their 99.9% point is 896,760, rounded up to 900,000. It removes 359 of the 375,136 tests of class 5 with a mileage, 2,561 of the 8,706,753 of class 7, 7,494 of the 290,343,630 of class 4, and 37 of classes 1 to 3. A bad mileage is an accident of one test: only 625 of the 5,677 vehicles concerned have one at every test.
- **A test whose engine size lies outside its class's usual range is removed.** A size such as 1 or 99,999 cc is a mistake, and what is plausible depends on the class. For each class the range runs from the 0.1% to the 99.9% point of its sizes, rounded outward so as to remove no more than those points do: 40 to 1,000 cc for class 1, 100 to 2,300 for class 2, 40 to 4,000 for class 3, 600 to 6,000 for class 4, 1,200 to 11,600 for class 5 and 1,400 to 3,500 for class 7, which staging reads from [`transform/seeds/engine_size_bounds.csv`](transform/seeds/engine_size_bounds.csv). Between 0.11% and 0.19% of each class's sizes fall outside. The size is part of the vehicle's record and repeats at every test: 75,558 of the 77,443 vehicles concerned have it at every test and leave the data.
- **A test at which the vehicle is over 50 years old is removed.** The earliest first-use date is 1 January of year 1, which no vehicle can have, while a vehicle of 50 can be tested. 256,468 of the 308,701,422 known ages are over 50 years, 0.08%. 80,985 of the 110,463 vehicles concerned are over 50 at every test and leave the data, so the model covers no vehicle over 50.
- **An electric vehicle's missing engine size is 0**, since it has no engine. The fuel input marks every electric vehicle, so a value the same for all of them adds nothing beside it and distorts no weight. Of the 2,038,463 kept tests without an engine size, 1,905,012 are of electric vehicles, whose share of tests grew from 0.20% in 2018 to 1.93% in 2025, as [`evidence/15_missing_values.py`](evidence/15_missing_values.py) shows in [`data/missing_values_run_2026-11-12.log`](data/missing_values_run_2026-11-12.log).
- **Any other missing number is dirty data, and the training row that needs it is left out of the training table**, while the test and its defects stay: a mileage or an age missing at the target slot's first test, or an engine size missing at the previous slot's first test on a vehicle that is not electric. Among the kept tests, 1,530,658 lack a mileage, 133,451 an engine size on a vehicle that is not electric, and 26,348 an age (evidence 15). Leaving out only the row, rather than the test, keeps the test's defects wherever they serve as the input of another row.
- **Make and model are trimmed and put in capitals**, which changes at most 0.003% of makes. `UNCLASSIFIED`, which the publisher gives a vehicle with no valid record in its vehicle dataset, is kept as a value of its own: about 0.3% of models a year.
- **A make or model ending in a backslash is kept, without the backslash.** Four rows of the 2018 to 2020 results end a value with a backslash just before the separator: the make `MOTOGUZZ\` in 2018 and 2020, and the model `VITESSE\` twice in 2019, the same two vehicles each time. Python's `csv`, reading a backslash as the escape, takes `\,` for a comma inside the value and joins two values into one; DuckDB, which the build reads with, applies the escape only inside double quotes, and splits all four rows into as many values as their header has columns, as [`evidence/10_backslash_rows.py`](evidence/10_backslash_rows.py) shows. No other row of any year fails to split, as [`evidence/09_csv_from_azure.py`](evidence/09_csv_from_azure.py) shows. Changed 2026-11-10, the author's decision; superseded wording, kept so the change stays visible: *Rows that do not split into as many values as their header has columns number at most 2 a year, all in 2018 to 2020, blank lines among them, and are skipped.*

### The training table: every possible row accounted for

**Every possible training row is either kept or left out by exactly one rule, each counted on its own, so that the rows the model learns from trace back to every pair of consecutive slots**, as the rows of the staged tables trace back to the files. A possible row is two consecutive slots of a vehicle, which makes as many rows as there are slots that are not a vehicle's first. We built the table on 12 November 2026 with dbt on the Azure virtual machine, from the staged tables of every year, in 35 minutes, and every test of the build passes, as its record [`data/dbt_mart_run_2026-11-12.log`](data/dbt_mart_run_2026-11-12.log) shows. The tests check that each staged test is in exactly one slot, with the slots split where and only where two consecutive tests are more than 20 weeks apart; that the table holds one row per vehicle and target slot; that every entry of an input or a label is one of the 4,821 and every group one of theirs; that the counts below add up to the possible rows and their kept rows to the table; and that every kept row has a mileage, age and engine size within its bounds, and a class among 1, 2, 3, 4, 5 and 7.

The model [`training_row_counts`](transform/models/marts/training_row_counts.sql) counts the rows per year of the target slot, as recorded in [`data/training_row_counts_2026-11-12.log`](data/training_row_counts_2026-11-12.log). A row that meets several rules is counted under the first, in the order of [`transform/macros/training_pairs.sql`](transform/macros/training_pairs.sql).

| Target year | Kept | Mileage missing at the target slot's first test | Age unknown at the target slot's first test | Engine size missing at the previous slot's first test, not electric | Possible rows |
|---|---|---|---|---|---|
| 2019 | 16,129,855 | 41,254 | 2,590 | 8,840 | 16,182,539 |
| 2020 | 27,230,182 | 67,635 | 3,163 | 12,736 | 27,313,716 |
| 2021 | 29,290,438 | 75,707 | 291 | 12,706 | 29,379,142 |
| 2022 | 30,581,637 | 77,719 | 215 | 11,917 | 30,671,488 |
| 2023 | 31,654,601 | 78,192 | 179 | 12,132 | 31,745,104 |
| 2024 | 31,942,228 | 77,179 | 156 | 10,926 | 32,030,489 |
| 2025 | 32,244,374 | 73,787 | 142 | 9,812 | 32,328,115 |
| **2019 to 2025** | **199,073,315** | **491,473** | **6,736** | **79,069** | **199,650,593** |

A further 52,824 pairs have a target slot that starts in 2018, from 20 May, and are counted under their own rule, since the first year predicted is 2019: 199,703,417 possible rows in all.

**Each vector is stored as the list of its entries that are 1**, every other entry being 0, and the groups the same way: the previous slot's entries, its groups and the label are three such lists on each row, sorted, with no repeats, and empty for a slot whose tests recorded nothing.

**The table is copied to the author's computer for the steps that run there**, since the Azure credit ends on 21 November 2026. We exported it on 13 November 2026 from the virtual machine as one Parquet file per target year, 4.3 GB in all, each file holding the kept rows `training_row_counts` counts for its year, as its record [`data/training_rows_export_run_2026-11-13.log`](data/training_rows_export_run_2026-11-13.log) shows, and downloaded it into `data/training_rows/`, which git ignores; each file's SHA-256 matched its copy on the machine.

### The baselines

**Two simple rules, fixed and scored before any model is trained, which the model has to beat to show that it has learnt anything a rule does not already know.** Both are scored as the model is, on every test year from 2020 to 2025, by [`src/motrisk/baselines.py`](src/motrisk/baselines.py), which writes the true positives, false positives and false negatives of each baseline, test year and entry to [`data/processed/baseline_counts.csv`](data/processed/baseline_counts.csv).

- **Repeat** predicts, for each row, the entries of its previous slot, however long before: the problems recur exactly. It uses the same input as the model.
- **Most popular** predicts, for every row of a test year, the same list: the *k* entries found on the most slots starting in the year before, where *k* is the median number of entries per slot of that year. Every slot counts, a vehicle's first slot included, although it is never a row's label, and a vehicle with two slots starting in a year counts twice. A tie at the *k*-th place goes to the lower entry number. The lists are built from every slot by the dbt model [`most_popular`](transform/models/marts/most_popular.sql), since a vehicle with a single slot appears in no training row. In every year from 2018 to 2025, *k* is 1 and the list is a single entry, the tyre advisory *worn close to legal limit / worn on edge*, listed for classes 3, 4 and 7 and found on 15.3% to 16.8% of each year's slots, as [`data/processed/most_popular.csv`](data/processed/most_popular.csv) shows; the list was built on the virtual machine on 13 November 2026, every test passing ([`data/dbt_most_popular_run_2026-11-13.log`](data/dbt_most_popular_run_2026-11-13.log)).

**An entry is scored only on rows of the classes it is listed for, by the baselines as by the models, so that the three are counted on the same ground.** A row's class is its previous slot's, so a defect recorded in the target slot but listed only for another class, after a change of class, is not scored for that row. For every test year and entry, each baseline's true positives plus false negatives equal the ones of the labels counted on their own, or the run stops.
