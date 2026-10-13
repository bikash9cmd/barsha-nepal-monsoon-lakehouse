-- How every station-day's precipitation was classified, and why.
select
    station_id,
    prcp_quality,
    coalesce(prcp_flag, '(blank)') as prcp_flag,
    count(*) as days,
    count(*) filter (where rain_observed) as days_rain_observed,
    count(*) filter (where prcp_reported_mm = 0) as reported_zero
from rain_daily
group by all
order by station_id, prcp_quality, prcp_flag
