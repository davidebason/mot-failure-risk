-- One row per defect or advisory recorded in a kept test, on a kept code listed for the vehicle's
-- class and recorded in a way the rules allow, with the code as published (DATA.md, "Decisions").
-- Mapping each code to its problem is left to the mart. A defect found at two places in one test
-- gives two identical rows, since the location is not kept.

select
    cast(test_id as bigint) as test_id,
    cast(rfr_id as integer) as rfr_id,
    rfr_type_code
from ({{ classified_failure_items() }})
where removed_by is null
