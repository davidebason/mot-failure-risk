-- Most popular's list of each year is built from that year's slots alone and has k entries: k is
-- the median number of entries per slot starting that year, recounted here; each listed entry is
-- on as many of those slots as it says; and no entry left out is on more slots than the list's
-- last one. Returns the years that break this.

with

slots as (
    select cast(extract(year from slot_start) as integer) as list_year, entries
    from {{ ref('int_slots') }}
),

recounted as (
    select list_year, entry, count(*) as slots_with_entry
    from (select list_year, unnest(entries) as entry from slots) as u
    group by list_year, entry
),

medians as (
    select list_year, percentile_disc(0.5) within group (order by len(entries)) as k
    from slots
    group by list_year
),

lists as (
    select
        list_year,
        count(*) as listed,
        min(k) as k,
        min(slots_with_entry) as last_on_list
    from {{ ref('most_popular') }}
    group by list_year
),

wrong_count as (
    select distinct m.list_year
    from {{ ref('most_popular') }} as m
    left join recounted as r
        on r.list_year = m.list_year and r.entry = m.entry
    where r.slots_with_entry is distinct from m.slots_with_entry
),

beaten as (
    select distinct r.list_year
    from recounted as r
    inner join lists as l
        on l.list_year = r.list_year
    where r.slots_with_entry > l.last_on_list
        and r.entry not in (
            select m.entry from {{ ref('most_popular') }} as m where m.list_year = r.list_year
        )
)

select m.list_year, 'k or the list length is wrong' as failure
from medians as m
left join lists as l
    on l.list_year = m.list_year
where m.k > 0 and (l.listed is distinct from m.k or l.k is distinct from m.k)

union all

select list_year, 'an entry is on another number of slots' as failure
from wrong_count

union all

select list_year, 'an entry left out is on more slots than one listed' as failure
from beaten
