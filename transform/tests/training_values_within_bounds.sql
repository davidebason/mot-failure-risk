-- In every kept training row, mileage, age and engine size are present and within their bounds
-- (DATA.md, "The vehicle columns, cleaned"): mileage from 1 to mileage_max, age from 0 to
-- age_max_years, and engine size within its class's range, or 0 for an electric vehicle. Returns
-- the rows that are not.
--
-- Age is checked as staging bounds it, in calendar years: the first use is recovered from the age
-- in days, and must not fall more than age_max_years before the test. Compared as a decimal, an
-- age of exactly 50 calendar years reads 50.0014, since those years hold 13 leap days.

select
    t.vehicle_id,
    t.target_start,
    t.test_class_id,
    t.fuel_type,
    t.test_mileage,
    t.age_years,
    t.cylinder_capacity
from {{ ref('training_rows') }} as t
left join {{ ref('engine_size_bounds') }} as e
    on e.test_class_id = t.test_class_id
where t.test_mileage is null
    or t.test_mileage not between 1 and {{ var('mileage_max') }}
    or t.age_years is null
    or t.age_years < 0
    or t.target_start - cast(round(t.age_years * 365.25) as integer)
        < t.target_start - interval {{ var('age_max_years') }} year
    or t.cylinder_capacity is null
    or not (
        t.cylinder_capacity between e.lowest and e.highest
        or (t.fuel_type = 'EL' and t.cylinder_capacity = 0)
    )
