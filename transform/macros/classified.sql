{#
  Every row of the two sources, with the rule that removes it, or null when it is kept (DATA.md,
  "Decisions"). The staging models keep the rows no rule removes, and staging_row_counts counts the
  rows each rule removes, both from these two macros, so that the two cannot disagree. A row is
  counted under the first rule it meets, in the order written.
#}

{% macro classified_test_results() %}
select
    *,
    case
        -- test_date is text here, in ISO form, so it compares as a date does.
        when test_date < '2018-05-20' then 'test before 20 May 2018'
        when test_result = 'ABR' then 'test aborted, ABR'
        when test_result = 'ABA' then 'test abandoned, ABA'
        when test_result = 'ABRVE' then 'test aborted by a vehicle examiner, ABRVE'
    end as removed_by
from {{ source('mot', 'test_results') }}
{% endmacro %}


{% macro classified_failure_items() %}
select
    i.*,
    case
        -- An item whose test is in no file is not removed: the staged items' test of
        -- relationships then fails, which is how it is found.
        when t.test_id is null then null
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
