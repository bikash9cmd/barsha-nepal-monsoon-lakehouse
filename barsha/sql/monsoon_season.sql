-- June-September totals per station and year. A total is only published when at least 90%
-- of the season's days have a complete reading; otherwise it is null and says why.
with season as (
    select * from rain_daily
    where month(obs_date) between 6 and 9
),
agg as (
    select
        station_id, year,
        count(*) filter (where prcp_quality = 'complete') as complete_days,
        count(*) filter (where prcp_quality = 'partial') as partial_days,
        count(*) filter (where prcp_quality = 'missing') as missing_days,
        count(*) filter (where prcp_quality = 'missing' and rain_observed) as missing_on_rain_days,
        sum(prcp_mm) as complete_total_mm,
        max(prcp_mm) as max_1day_mm,
        max(rain_3day_mm) as max_3day_mm,
        count(*) filter (where prcp_mm >= 64.5) as heavy_days,
        count(*) filter (where alert_level in ('orange', 'red')) as alert_days
    from season
    group by station_id, year
)
select
    station_id, year,
    complete_days, partial_days, missing_days,
    $monsoon_days - complete_days - partial_days - missing_days as absent_days,
    missing_on_rain_days,
    round(complete_days / $monsoon_days, 3) as completeness,
    case when complete_days >= $min_completeness * $monsoon_days then round(complete_total_mm, 1) end as jjas_total_mm,
    case when complete_days >= $min_completeness * $monsoon_days then 'published'
         else 'withheld: ' || (complete_days) || ' of ' || $monsoon_days || ' days complete' end as total_status,
    round(max_1day_mm, 1) as max_1day_mm,
    max_3day_mm,
    heavy_days,
    alert_days
from agg
order by station_id, year
