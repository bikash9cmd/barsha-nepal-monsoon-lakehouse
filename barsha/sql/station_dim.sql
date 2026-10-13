-- Slowly changing dimension (type 2) for station metadata, derived from the facts.
-- A new version starts on the first day a station's name, position or elevation changes.
with attrs as (
    select
        station_id, obs_date, station_name, latitude, longitude, elevation_m,
        concat_ws('|', station_name, latitude, longitude, elevation_m) as attr_hash
    from silver
),
flagged as (
    select *,
        case when attr_hash is distinct from lag(attr_hash) over (partition by station_id order by obs_date)
             then 1 else 0 end as is_change
    from attrs
),
versioned as (
    select *, sum(is_change) over (partition by station_id order by obs_date) as version
    from flagged
),
spans as (
    select
        station_id, version,
        any_value(station_name) as station_name,
        any_value(latitude) as latitude,
        any_value(longitude) as longitude,
        any_value(elevation_m) as elevation_m,
        min(obs_date) as valid_from,
        max(obs_date) as last_obs_in_version
    from versioned
    group by station_id, version
)
select
    station_id,
    version::integer as version,
    station_name,
    latitude, longitude, elevation_m,
    valid_from::date as valid_from,
    (lead(valid_from) over (partition by station_id order by version) - interval 1 day)::date as valid_to,
    lead(valid_from) over (partition by station_id order by version) is null as is_current
from spans
order by station_id, version
