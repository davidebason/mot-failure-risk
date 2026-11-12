-- One row per test from 20 May 2018 to the end of 2025, stopped tests removed, with the columns
-- DATA.md keeps under "What is kept from each file", typed, and the vehicle columns cleaned as
-- "The vehicle columns, cleaned" sets out. The rules that remove tests are in macros/classified.sql.

with

kept as (
    select * from ({{ classified_test_results() }})
    where removed_by is null
),

-- From 2024 some tests name their fuel, such as ELECTRIC, rather than give its code.
fuel_names as (
    select upper(fuel_type) as name, type_code
    from {{ source('mot', 'mdr_fuel_types') }}
)

select
    cast(k.test_id as bigint) as test_id,
    cast(k.vehicle_id as bigint) as vehicle_id,
    cast(k.test_date as date) as test_date,
    cast(k.test_class_id as integer) as test_class_id,
    k.test_type,
    k.test_result,
    -- Missing mileage is blank before 2024 and 0 from 2024: both become missing.
    nullif(cast(k.test_mileage as integer), 0) as test_mileage,
    -- Trimmed and in capitals, without the backslash four rows of 2018 to 2020 end with.
    rtrim(upper(trim(k.make)), '\') as make,
    rtrim(upper(trim(k.model)), '\') as model,
    coalesce(f.type_code, k.fuel_type) as fuel_type,
    -- Blank or 0: missing.
    nullif(cast(k.cylinder_capacity as integer), 0) as cylinder_capacity,
    -- 1 January 1971 stands for an unknown date, and a first use after the test is impossible:
    -- both, like a blank, leave the date, and so the age, unknown.
    case
        when k.first_use_date <> '1971-01-01'
            and cast(k.first_use_date as date) <= cast(k.test_date as date)
            then cast(k.first_use_date as date)
    end as first_use_date
from kept as k
left join fuel_names as f
    on f.name = upper(trim(k.fuel_type))
