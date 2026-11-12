-- No staged mileage, engine size or age lies outside its bounds (DATA.md, "The vehicle columns,
-- cleaned"): a test with one is removed (macros/classified.sql). Returns any that remain.

select t.test_id, t.test_class_id, t.test_mileage, t.cylinder_capacity, t.first_use_date
from {{ ref('stg_test_results') }} as t
left join {{ ref('engine_size_bounds') }} as e
    on e.test_class_id = t.test_class_id
where t.test_mileage not between 1 and {{ var('mileage_max') }}
    or t.cylinder_capacity not between e.lowest and e.highest
    or t.first_use_date < t.test_date - interval {{ var('age_max_years') }} year
    or t.first_use_date > t.test_date
