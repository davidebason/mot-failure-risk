-- Where every row of the two sources goes: kept in its staged table, or removed by one rule, each
-- rule counted on its own (DATA.md, "Decisions"). tests/staging_rows_accounted.sql checks that the
-- counts add up to the rows of the files and that the kept rows are the staged rows.

select
    'test_results' as source_table,
    coalesce(removed_by, 'kept') as outcome,
    count(*) as row_count
from ({{ classified_test_results() }})
group by all

union all

select
    'failure_items' as source_table,
    coalesce(removed_by, 'kept') as outcome,
    count(*) as row_count
from ({{ classified_failure_items() }})
group by all
