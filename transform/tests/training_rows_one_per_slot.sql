-- One training row per vehicle and target slot: the key, the vehicle and the date of the target
-- slot's first test, is unique. Returns the keys that repeat.

select vehicle_id, target_start, count(*) as rows_with_key
from {{ ref('training_rows') }}
group by vehicle_id, target_start
having count(*) > 1
