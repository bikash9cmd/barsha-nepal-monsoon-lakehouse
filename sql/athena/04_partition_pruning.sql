-- Silver is partitioned by year with partition projection. Filtering on `year` reads one
-- ~30 KB file; filtering only on obs_date reads all 50. Compare "Data scanned" in the console.
SELECT station_id, count(*) AS station_days, count(prcp_mm) AS complete_days
FROM barsha.daily_weather
WHERE year = 2024
GROUP BY station_id
ORDER BY station_id;
