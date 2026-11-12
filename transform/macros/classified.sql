{#
  Every row of the two sources, with the rule that removes it, or null when it is kept (DATA.md,
  "Decisions"). The staging models keep the rows no rule removes, and staging_row_counts counts the
  rows each rule removes, both from these two macros, so that the two cannot disagree. A row is
  counted under the first rule it meets, in the order written.
#}

{% macro classified_test_results() %}
select
    r.*,
    case
        -- test_date is text here, in ISO form, so it compares as a date does.
        when r.test_date < '2018-05-20' then 'test before 20 May 2018'
        when r.test_result = 'ABR' then 'test aborted, ABR'
        when r.test_result = 'ABA' then 'test abandoned, ABA'
        when r.test_result = 'ABRVE' then 'test aborted by a vehicle examiner, ABRVE'
        -- The bounds of dbt_project.yml and seeds/engine_size_bounds.csv (DATA.md, "The vehicle
        -- columns, cleaned"). A blank or zero value is missing, not past a bound.
        when try_cast(r.test_mileage as integer) > {{ var('mileage_max') }}
            then 'mileage above {{ var("mileage_max") }}'
        when try_cast(r.cylinder_capacity as integer) > 0
            and try_cast(r.cylinder_capacity as integer) not between e.lowest and e.highest
            then 'engine size outside its class''s range'
        when r.first_use_date <> '1971-01-01'
            and try_cast(r.first_use_date as date) <= try_cast(r.test_date as date)
            and try_cast(r.first_use_date as date)
                < try_cast(r.test_date as date) - interval {{ var('age_max_years') }} year
            then 'age at the test over {{ var("age_max_years") }} years'
    end as removed_by
from {{ source('mot', 'test_results') }} as r
left join {{ ref('engine_size_bounds') }} as e
    on e.test_class_id = try_cast(r.test_class_id as integer)
{% endmacro %}


{% macro classified_failure_items() %}
select
    i.*,
    case
        -- An item whose test is in no file has no vehicle, date or class, so it cannot be placed
        -- in any slot. The full build of 2026-11-12 found 175, 167 of them in the 2022 file.
        when t.test_id is null then 'item whose test is in no file'
        when t.removed_by is not null then 'item of a removed test'
        when d.rfr_id is null then 'item on a code not kept'
        when c.rfr_id is null then 'item on a code not listed for its vehicle''s class'
        when e.entry is null then 'item recorded in a way the rules exclude'
    end as removed_by
from {{ source('mot', 'failure_items') }} as i
left join ({{ classified_test_results() }}) as t
    on t.test_id = i.test_id
left join {{ ref('code_dictionary') }} as d
    on d.rfr_id = try_cast(i.rfr_id as integer)
left join {{ source('mot', 'item_detail') }} as c
    on c.rfr_id = i.rfr_id and c.test_class_id = t.test_class_id
left join {{ ref('year_vector_entries') }} as e
    on e.problem = d.problem and e.way = i.rfr_type_code
{% endmacro %}
