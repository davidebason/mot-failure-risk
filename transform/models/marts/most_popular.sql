-- Most popular's list for each year n: the k entries found on the most slots starting in year n,
-- where k is the median number of entries per slot of that year (DATA.md, "The baselines"). Every
-- slot counts, a vehicle's first slot included, and a vehicle with two slots starting in a year
-- counts twice. The list of year n is every vehicle's prediction for the test year n + 1.
--
-- Ties at the k-th place go to the lower entry number. percentile_disc returns a value that occurs,
-- so k is a whole number. len() is DuckDB's; PostgreSQL writes cardinality(entries).

with

slots as (
    select
        cast(extract(year from slot_start) as integer) as list_year,
        entries
    from {{ ref('int_slots') }}
),

per_year as (
    select
        list_year,
        count(*) as slots_in_year,
        percentile_disc(0.5) within group (order by len(entries)) as k
    from slots
    group by list_year
),

counts as (
    select list_year, entry, count(*) as slots_with_entry
    from (select list_year, unnest(entries) as entry from slots) as u
    group by list_year, entry
),

ranked as (
    select
        list_year,
        entry,
        slots_with_entry,
        row_number() over (
            partition by list_year order by slots_with_entry desc, entry
        ) as list_rank
    from counts
)

select
    r.list_year,
    y.k,
    r.list_rank,
    r.entry,
    r.slots_with_entry,
    y.slots_in_year
from ranked as r
inner join per_year as y
    on y.list_year = r.list_year
where r.list_rank <= y.k
