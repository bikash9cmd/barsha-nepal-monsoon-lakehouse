-- June-September totals, only where 90% of the season has complete readings.
-- The withheld rows are the point: they say why a number is missing instead of printing a wrong one.
SELECT d.station_name, m.year, m.jjas_total_mm, m.total_status, m.missing_on_rain_days, m.max_1day_mm
FROM barsha.monsoon_season m
JOIN barsha.station_dim d ON d.station_id = m.station_id AND d.is_current
WHERE m.year >= 2014
ORDER BY d.station_name, m.year;
