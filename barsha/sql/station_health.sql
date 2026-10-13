-- Is each station still reporting, and how much of what it reports can be used?
with recent as (
    select
        station_id,
        min(obs_date) as first_obs,
        max(obs_date) as last_obs,
        count(*) filter (where obs_date > $as_of - interval 365 days and prcp_quality = 'complete') as complete_last_365,
        count(*) filter (where prcp_quality = 'missing' and rain_observed) as missing_on_rain_days,
        count(*) filter (where rain_observed) as rain_days_observed
    from rain_daily
    group by station_id
)
select
    r.station_id,
    d.station_name,
    r.first_obs,
    r.last_obs,
    date_diff('day', r.last_obs, $as_of::date) as days_since_last_obs,
    round(r.complete_last_365 / 365.0, 3) as completeness_last_365,
    round(r.missing_on_rain_days / nullif(r.rain_days_observed, 0), 3) as share_rain_days_missing_amount,
    case
        when date_diff('day', r.last_obs, $as_of::date) > $retired_after_days then 'retired'
        when date_diff('day', r.last_obs, $as_of::date) > $stale_after_days then 'stale'
        else 'reporting'
    end as status,
    $as_of::date as as_of
from recent r
join station_dim d on d.station_id = r.station_id and d.is_current
order by r.station_id
