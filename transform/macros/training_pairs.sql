{#
  Every possible training row, with the rule that leaves it out, or null when it is kept (DATA.md,
  "What the model predicts" and "The vehicle columns, cleaned"). A possible row is two consecutive
  slots of a vehicle: the target slot, and the slot before it, whose first test gives the class
  and the vehicle's details. Mileage and age are taken at the target slot's first test, since both
  are known when the vehicle arrives for it. training_rows keeps the rows no rule leaves out, and
  training_row_counts counts the rows each rule leaves out, both from this macro, so that the two
  cannot disagree. A row is counted under the first rule it meets, in the order written.

  vectors: whether to carry the three lists of entries, which the counts do not need.
#}

{% macro training_pairs(vectors) %}
with

pairs as (
    select
        vehicle_id,
        slot_start as target_start,
        lag(slot_start) over by_slot as previous_start,
        lag(test_class_id) over by_slot as test_class_id,
        lag(make) over by_slot as make,
        lag(model) over by_slot as model,
        lag(fuel_type) over by_slot as fuel_type,
        lag(cylinder_capacity) over by_slot as previous_cylinder_capacity,
        test_mileage,
        first_use_date
        {%- if vectors %},
        lag(entries) over by_slot as previous_entries,
        lag(group_ids) over by_slot as previous_group_ids,
        entries as label_entries
        {%- endif %}
    from {{ ref('int_slots') }}
    window by_slot as (partition by vehicle_id order by slot_number)
)

select
    vehicle_id,
    target_start,
    cast(extract(year from target_start) as integer) as target_year,
    previous_start,
    (target_start - previous_start) / 7.0 as weeks_between,
    test_class_id,
    make,
    model,
    fuel_type,
    -- An electric vehicle has no engine, so a missing size is 0 (evidence/15).
    case
        when fuel_type = 'EL' then coalesce(previous_cylinder_capacity, 0)
        else previous_cylinder_capacity
    end as cylinder_capacity,
    test_mileage,
    (target_start - first_use_date) / 365.25 as age_years,
    {%- if vectors %}
    previous_entries,
    previous_group_ids,
    label_entries,
    {%- endif %}
    case
        when extract(year from target_start) < {{ var('first_target_year') }}
            then 'target slot starting before {{ var("first_target_year") }}'
        when test_mileage is null then 'mileage missing at the target slot''s first test'
        when first_use_date is null then 'age unknown at the target slot''s first test'
        when previous_cylinder_capacity is null and fuel_type is distinct from 'EL'
            then 'engine size missing at the previous slot''s first test, not electric'
    end as left_out_by
from pairs
-- A vehicle's first slot has no slot before it, and serves only as an input.
where previous_start is not null
{% endmacro %}
