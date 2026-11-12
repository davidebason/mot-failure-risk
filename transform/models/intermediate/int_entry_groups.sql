-- One row per entry of the vector, the 4,821 of seeds/year_vector_entries.csv, with the group
-- directly above its defect's code in item_detail, the group the inputs and the angle read it by
-- (DATA.md, "What the model predicts"). A code sits under the same group in every class
-- (evidence/04). A renumbered defect takes the group of the code it is numbered by, the one used
-- first: of the 36 pairs kept, 8 put their two codes under different groups.

with

code_groups as (
    select distinct
        cast(rfr_id as integer) as rfr_id,
        cast(test_item_id as integer) as group_id
    from {{ source('mot', 'item_detail') }}
)

select
    e.entry,
    e.problem,
    e.way,
    g.group_id
from {{ ref('year_vector_entries') }} as e
left join code_groups as g
    on g.rfr_id = e.problem
