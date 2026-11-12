-- Where every possible training row goes, per year of its target slot: kept in training_rows, or
-- left out by one rule, each rule counted on its own (macros/training_pairs.sql). The kept rows
-- per year are the row counts DATA.md records. tests/training_rows_accounted.sql checks that the
-- counts add up to every pair of consecutive slots, and the kept rows to the training table.

select
    target_year,
    coalesce(left_out_by, 'kept') as outcome,
    count(*) as row_count
from ({{ training_pairs(vectors=false) }}) as p
group by target_year, coalesce(left_out_by, 'kept')
