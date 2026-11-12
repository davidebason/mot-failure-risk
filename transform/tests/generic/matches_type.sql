{#
  The values of a text column that do not have the form of their type, so that a column of the
  wrong type shows at once. DuckDB's own conversion is too lenient to serve: it turns '71614.0' into
  71614 and '2021-6-3' into a date. kind is whole_number, digits only, or iso_date, YYYY-MM-DD and
  a real date. regexp_full_match is DuckDB's; PostgreSQL writes column ~ '^[0-9]+$'.
#}
{% test matches_type(model, column_name, kind) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
    and not (
    {%- if kind == 'whole_number' %}
        regexp_full_match({{ column_name }}, '[0-9]+')
    {%- elif kind == 'iso_date' %}
        regexp_full_match({{ column_name }}, '[0-9]{4}-[0-9]{2}-[0-9]{2}')
        and try_cast({{ column_name }} as date) is not null
    {%- else %}
        {{ exceptions.raise_compiler_error("matches_type: unknown kind " ~ kind) }}
    {%- endif %}
    )
{% endtest %}
