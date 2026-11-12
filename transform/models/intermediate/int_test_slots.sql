-- One row per staged test, with the slot of its vehicle it falls in (DATA.md, "What the model
-- predicts"). A vehicle's tests are taken in date order, and a gap of more than slot_gap_weeks
-- between two consecutive tests starts a new slot; the slots of a vehicle are numbered from 1.
--
-- Several tests on one day are put in the order normal test first, then lowest mileage, then
-- test_id, so that the test that starts a slot is the one completed first (evidence/16): a retest
-- follows the test it retests, and an odometer only goes up. test_id does not follow the order of
-- the day, completed first in half of the pairs and later in the other half.

with

gaps as (
    select
        test_id,
        vehicle_id,
        test_date,
        test_type,
        test_mileage,
        test_date - lag(test_date) over by_date as days_since_previous
    from {{ ref('stg_test_results') }}
    window by_date as (
        partition by vehicle_id
        order by test_date, test_type <> 'NT', test_mileage nulls last, test_id
    )
),

starts as (
    select
        *,
        days_since_previous is null
            or days_since_previous > {{ var('slot_gap_weeks') * 7 }} as starts_slot
    from gaps
)

select
    test_id,
    vehicle_id,
    test_date,
    starts_slot,
    cast(
        sum(case when starts_slot then 1 else 0 end) over (
            partition by vehicle_id
            order by test_date, test_type <> 'NT', test_mileage nulls last, test_id
            rows between unbounded preceding and current row
        ) as integer
    ) as slot_number
from starts
