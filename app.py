"""Streamlit demo of Barsha: replay the daily bulletin, browse a station's monsoons and query the lake.

    streamlit run app.py

Reads the local lake in ./lake. If it isn't there yet, it is built once from NOAA's public bucket
(anonymous S3, about a minute), the same as `make backfill`.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import streamlit as st

from barsha import pipeline
from barsha.alerts import render
from barsha.gold import TABLES, gold_key
from barsha.source import open_source
from barsha.storage import open_lake

st.set_page_config(page_title="Barsha", page_icon="🌧️", layout="wide")

LAKE = "lake"
PRESETS = {
    "Wettest days on record": (
        "select s.station_name, r.obs_date, r.prcp_mm, r.rain_category\n"
        "from rain_daily r join station_dim s using (station_id)\n"
        "where s.is_current\norder by r.prcp_mm desc nulls last limit 20"
    ),
    "Station health": (
        "select station_name, first_obs, last_obs, completeness_last_365, status\n"
        "from station_health order by station_name"
    ),
    "Monsoon totals for 2024": (
        "select s.station_name, m.jjas_total_mm, m.completeness, m.total_status, m.max_1day_mm\n"
        "from monsoon_season m join station_dim s using (station_id)\n"
        "where m.year = 2024 and s.is_current order by m.jjas_total_mm desc nulls last"
    ),
}


@st.cache_resource(show_spinner="Building the lake from NOAA's public bucket (about a minute, first visit only)...")
def lake():
    lk = open_lake(LAKE)
    if not Path(LAKE, gold_key("rain_daily")).exists():
        today = datetime.now(UTC).date()
        pipeline.run_all(open_source("s3://noaa-gsod-pds"), lk, pipeline.backfill_years(today), today)
    return lk


@st.cache_resource
def db():
    lk = lake()
    con = duckdb.connect()
    silver = lk.uri("silver/daily_weather") + "/*/*.parquet"
    con.execute(f"create view daily_weather as select * from read_parquet('{silver}', hive_partitioning = true)")
    for table in TABLES:
        if lk.exists(gold_key(table)):
            con.execute(f"create view {table} as select * from read_parquet('{lk.uri(gold_key(table))}')")
    return con


def sql(q: str):
    return db().cursor().sql(q).df()


st.title("Barsha (वर्षा)")
st.caption("50 years of Nepal's weather-station rainfall in a lakehouse: how unusual was yesterday's rain, and where?")

lk = lake()
bulletin, stations, query = st.tabs(["Daily bulletin", "A station's monsoons", "SQL"])

with bulletin:
    day = st.date_input("Replay the bulletin for", value=date(2024, 9, 28), min_value=date(1977, 1, 1))
    st.caption("28 September 2024 is the Kathmandu flood. Bulletins are in English and Nepali.")
    st.code(render(pipeline.replay_bulletin(lk, day)), language=None)

with stations:
    names = sql("select station_id, station_name from station_dim where is_current order by station_name")
    labels = dict(zip(names.station_id, names.station_name.str.replace(", NP", "").str.title(), strict=True))
    default = list(labels).index("44454099999") if "44454099999" in labels else 0
    sid = st.selectbox("Station", list(labels), index=default, format_func=labels.get)
    m = sql(
        f"select year, jjas_total_mm, completeness, total_status, max_1day_mm, heavy_days from monsoon_season "
        f"where station_id = '{sid}' order by year"
    )
    published = m[m.total_status == "published"]
    st.subheader("June to September total, seasons complete enough to publish")
    st.bar_chart(published.set_index("year")["jjas_total_mm"], y_label="mm")
    st.dataframe(m.sort_values("year", ascending=False), hide_index=True, width="stretch")

with query:
    preset = st.selectbox("Start from", list(PRESETS))
    text = st.text_area("SQL (DuckDB) over daily_weather, " + ", ".join(TABLES), PRESETS[preset], height=150)
    if st.button("Run"):
        try:
            st.dataframe(sql(text), hide_index=True, width="stretch")
        except duckdb.Error as e:
            st.error(str(e))
