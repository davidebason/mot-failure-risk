-- Every possible training row is accounted for: the rows training_row_counts counts, kept and left
-- out, equal the pairs of consecutive slots, which are the slots that are not a vehicle's first;
-- and the kept rows are the rows of the training table. Returns the counts when either fails.

with

counted as (
    select
        sum(row_count) as counted_rows,
        sum(case when outcome = 'kept' then row_count else 0 end) as kept_rows
    from {{ ref('training_row_counts') }}
),

actual as (
    select
        (select count(*) from {{ ref('int_slots') }})
        - (select count(distinct vehicle_id) from {{ ref('int_slots') }}) as possible_rows,
        (select count(*) from {{ ref('training_rows') }}) as training_rows
)

select *
from counted
cross join actual
where counted_rows <> possible_rows
    or kept_rows <> training_rows
