-- Which stations saw an event, day by day. Change the dates for any storm.
SELECT r.obs_date, d.station_name, r.prcp_mm, r.prcp_quality, r.alert_level
FROM barsha.rain_daily r
JOIN barsha.station_dim d ON d.station_id = r.station_id AND d.is_current
WHERE r.obs_date BETWEEN DATE '2024-09-26' AND DATE '2024-09-29'
ORDER BY r.obs_date, r.prcp_mm DESC NULLS LAST;
