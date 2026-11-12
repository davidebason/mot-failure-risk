-- One row per vehicle and slot: the details of the slot's first test, and every entry recorded on
-- any of its tests with the groups they fall in, each list sorted and without repeats (DATA.md,
-- "What the model predicts"). A slot whose tests recorded nothing has two empty lists. Each list
-- holds the entries that are 1; every other entry is 0.

with

recorded as (
    select
        s.vehicle_id,
        s.slot_number,
        array_agg(distinct e.entry order by e.entry) as entries,
        array_agg(distinct e.group_id order by e.group_id) as group_ids
    from {{ ref('stg_failure_items') }} as i
    inner join {{ ref('int_test_slots') }} as s
        on s.test_id = i.test_id
    -- Staging keeps only items on a kept code, recorded in a way the rules allow, so every item
    -- finds its defect and its entry.
    inner join {{ ref('code_dictionary') }} as d
        on d.rfr_id = i.rfr_id
    inner join {{ ref('int_entry_groups') }} as e
        on e.problem = d.problem and e.way = i.rfr_type_code
    group by s.vehicle_id, s.slot_number
)

select
    s.vehicle_id,
    s.slot_number,
    t.test_date as slot_start,
    t.test_class_id,
    t.make,
    t.model,
    t.fuel_type,
    t.cylinder_capacity,
    t.test_mileage,
    t.first_use_date,
    coalesce(r.entries, array[]::integer[]) as entries,
    coalesce(r.group_ids, array[]::integer[]) as group_ids
from {{ ref('int_test_slots') }} as s
inner join {{ ref('stg_test_results') }} as t
    on t.test_id = s.test_id
left join recorded as r
    on r.vehicle_id = s.vehicle_id and r.slot_number = s.slot_number
where s.starts_slot
