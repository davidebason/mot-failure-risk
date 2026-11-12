-- Every staged test is in exactly one slot, and the slots split a vehicle's tests where, and only
-- where, two consecutive tests are more than slot_gap_weeks apart (DATA.md, "What the model
-- predicts"): tests within a slot are at most that far apart, consecutive slots further, and each
-- slot has one first test, the slots numbered 1, 2, ... in date order. Returns the tests that break
-- this, and any staged test with no slot. int_test_slots.test_id is unique, by its schema test.

with

ordered as (
    select
        test_id,
        test_date,
        starts_slot,
        slot_number,
        test_date - lag(test_date) over by_date as days_since_previous,
        lag(slot_number) over by_date as previous_slot_number
    from {{ ref('int_test_slots') }}
    -- On a day with several tests, the slot's first test first.
    window by_date as (partition by vehicle_id order by test_date, starts_slot desc, test_id)
)

select test_id, 'breaks the slots' as failure
from ordered
where
    case
        when days_since_previous is null
            then not starts_slot or slot_number <> 1
        when days_since_previous > {{ var('slot_gap_weeks') * 7 }}
            then not starts_slot or slot_number <> previous_slot_number + 1
        else starts_slot or slot_number <> previous_slot_number
    end

union all

select t.test_id, 'staged test with no slot' as failure
from {{ ref('stg_test_results') }} as t
where not exists (
    select 1 from {{ ref('int_test_slots') }} as s where s.test_id = t.test_id
)
