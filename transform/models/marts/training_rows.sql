-- The training table: one row per vehicle and target slot starting from 2019 to 2025 (DATA.md,
-- "What the model predicts"). The inputs are the previous slot's entries and groups, the class and
-- details of its first test, the mileage and age at the target slot's first test, and the weeks
-- between the two first tests; the label is the target slot's entries. Each list holds the
-- entries, or groups, that are 1. The rules that leave a row out are in macros/training_pairs.sql.

select
    vehicle_id,
    target_start,
    target_year,
    previous_start,
    weeks_between,
    test_class_id,
    make,
    model,
    fuel_type,
    cylinder_capacity,
    test_mileage,
    age_years,
    previous_entries,
    previous_group_ids,
    label_entries
from ({{ training_pairs(vectors=true) }}) as p
where left_out_by is null
