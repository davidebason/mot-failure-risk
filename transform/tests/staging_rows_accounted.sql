-- Every row of the files is accounted for: for each table, the rows of the source equal the rows
-- staging_row_counts counts, kept and removed, and the kept rows are the rows of the staged table.
-- Returns the tables for which either fails.

with

counted as (
    select
        source_table,
        sum(row_count) as counted_rows,
        sum(row_count) filter (where outcome = 'kept') as kept_rows
    from {{ ref('staging_row_counts') }}
    group by source_table
),

actual as (
    select
        'test_results' as source_table,
        (select count(*) from {{ source('mot', 'test_results') }}) as source_rows,
        (select count(*) from {{ ref('stg_test_results') }}) as staged_rows
    union all
    select
        'failure_items',
        (select count(*) from {{ source('mot', 'failure_items') }}),
        (select count(*) from {{ ref('stg_failure_items') }})
)

select *
from actual
full join counted using (source_table)
where counted_rows is distinct from source_rows
    or kept_rows is distinct from staged_rows
