-- Station metadata as it was on any date (type 2 slowly changing dimension).
SELECT station_id, version, station_name, valid_from, valid_to, is_current
FROM barsha.station_dim
WHERE station_id = '44438099999';  -- Bhairahawa, renamed for Gautam Buddha International Airport
