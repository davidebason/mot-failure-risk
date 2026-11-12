-- The vehicles tested in more than one class. Reported, not enforced: a vehicle's class does
-- change, for 0.33% of vehicles, and each test's class is kept as recorded (DATA.md, "A vehicle's
-- class fixes which defects it can have"; evidence/12). The warning shows the count at each build.

{{ config(severity = 'warn') }}

select vehicle_id, count(distinct test_class_id) as classes
from {{ ref('stg_test_results') }}
group by vehicle_id
having count(distinct test_class_id) > 1
