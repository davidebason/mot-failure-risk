-- Every entry in an input or a label is one of the 4,821 of the vector, and every group in an input
-- the group of one of them. Returns the ones that are not.

with

entries as (
    select unnest(previous_entries) as entry from {{ ref('training_rows') }}
    union
    select unnest(label_entries) as entry from {{ ref('training_rows') }}
),

group_ids as (
    select distinct unnest(previous_group_ids) as group_id from {{ ref('training_rows') }}
)

select 'entry' as kind, entry as value
from entries
where entry not in (select entry from {{ ref('int_entry_groups') }})

union all

select 'group' as kind, group_id as value
from group_ids
where group_id not in (select group_id from {{ ref('int_entry_groups') }})
