-- The 20 wettest believable days in the record, with how each compared to its station's past.
-- Workgroup: barsha. Scans ~1 MB.
SELECT d.station_name, r.obs_date, r.prcp_mm, r.rain_3day_mm, r.prior_max_mm, r.is_station_record, r.alert_level
FROM barsha.rain_daily r
JOIN barsha.station_dim d ON d.station_id = r.station_id AND d.is_current
WHERE r.prcp_mm IS NOT NULL AND NOT r.is_suspect
ORDER BY r.prcp_mm DESC
LIMIT 20;
