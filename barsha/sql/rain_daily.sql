-- One row per station-day with rainfall, its category, and how it compares with that
-- station's own history. Thresholds use only years before the day's year, so a replay of
-- any past day sees exactly what a live run would have seen then.
with days as (
    select
        station_id, obs_date::date as obs_date, year(obs_date) as yr,
        prcp_mm, prcp_reported_mm, prcp_flag, prcp_quality, rain_observed
    from silver
    where obs_date <= $as_of
),
wet as (
    select station_id, yr, prcp_mm from days
    where prcp_quality = 'complete' and prcp_mm >= 1.0
),
station_years as (
    select distinct station_id, yr from days
),
thresholds as (
    select
        sy.station_id, sy.yr,
        count(w.prcp_mm) as prior_wet_days,
        quantile_cont(w.prcp_mm, 0.99) as p99_wet_mm,
        quantile_cont(w.prcp_mm, 0.999) as p999_wet_mm,
        max(w.prcp_mm) as prior_max_mm
    from station_years sy
    left join wet w on w.station_id = sy.station_id and w.yr < sy.yr
    group by sy.station_id, sy.yr
),
rolled as (
    select *,
        sum(prcp_mm) over w3 as sum3,
        count(prcp_mm) over w3 as complete3
    from days
    window w3 as (partition by station_id order by obs_date range between interval 2 days preceding and current row)
),
scored as (
    select
        r.station_id, r.obs_date, r.yr as year,
        r.prcp_mm, r.prcp_reported_mm, r.prcp_flag, r.prcp_quality, r.rain_observed,
        case when r.complete3 = 3 then round(r.sum3, 1) end as rain_3day_mm,
        case
            when r.prcp_mm >= 204.5 then 'extremely_heavy'
            when r.prcp_mm >= 115.6 then 'very_heavy'
            when r.prcp_mm >= 64.5 then 'heavy'
            when r.prcp_mm >= 15.6 then 'moderate'
            when r.prcp_mm >= 2.5 then 'light'
            when r.prcp_mm >= 0.1 then 'very_light'
            when r.prcp_mm = 0 then 'dry'
        end as rain_category,
        -- Thresholds need about 300 prior wet days (several seasons) to mean anything.
        case when t.prior_wet_days >= 300 then round(t.p99_wet_mm, 1) end as p99_wet_mm,
        case when t.prior_wet_days >= 300 then round(t.p999_wet_mm, 1) end as p999_wet_mm,
        t.prior_max_mm,
        t.prior_wet_days
    from rolled r
    join thresholds t on t.station_id = r.station_id and t.yr = r.yr
),
-- A day far above the station's own extremes is only believed if another station within
-- 200 km saw heavy rain (>= 64.5 mm) the day before, the same day or the day after.
positions as (
    select station_id, any_value(latitude) as lat, any_value(longitude) as lon
    from silver group by station_id
),
neighbours as (
    select a.station_id, b.station_id as neighbour_id
    from positions a join positions b on a.station_id <> b.station_id
    where 2 * 6371 * asin(sqrt(
        pow(sin(radians(b.lat - a.lat) / 2), 2)
        + cos(radians(a.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - a.lon) / 2), 2)
    )) <= 200
),
screened as (
    select *, coalesce(prcp_mm > $suspect_multiple * p999_wet_mm, false) as far_above_station
    from scored
),
corroborated as (
    select s.station_id, s.obs_date, max(d.prcp_mm) as neighbour_max_mm
    from screened s
    join neighbours n on n.station_id = s.station_id
    join days d on d.station_id = n.neighbour_id
        and d.obs_date between s.obs_date - interval 1 day and s.obs_date + interval 1 day
    where s.far_above_station
    group by s.station_id, s.obs_date
),
flagged as (
    select s.*,
        c.neighbour_max_mm,
        s.far_above_station and coalesce(c.neighbour_max_mm, 0) < 64.5 as is_suspect
    from screened s
    left join corroborated c using (station_id, obs_date)
)
select * exclude (far_above_station),
    coalesce(prcp_mm > prior_max_mm, false) and prior_wet_days >= 300 and not is_suspect as is_station_record,
    case
        when prcp_mm is null then null
        when is_suspect then 'suspect'
        -- Station-relative levels only count from $min_relative_mm up: at a dry station,
        -- a 10 mm day can be "its 99th percentile" and still be harmless.
        when prcp_mm >= 204.5
             or (prcp_mm >= $min_relative_mm and (prcp_mm >= p999_wet_mm
                 or (prior_wet_days >= 300 and prcp_mm > prior_max_mm))) then 'red'
        when prcp_mm >= 115.6 or (prcp_mm >= $min_relative_mm and prcp_mm >= p99_wet_mm) then 'orange'
        when prcp_mm >= 64.5 then 'yellow'
    end as alert_level
from flagged
order by station_id, obs_date
