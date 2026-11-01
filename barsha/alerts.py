"""Next-morning rainfall report: which stations had an extreme day, which went quiet.

GSOD publishes each day one to two days late, so this is not an early warning (Nepal's
Department of Hydrology and Meteorology issues those). It answers the question responders,
reporters and insurers ask the day after: how unusual was that rain, for that place?
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .config import STALE_AFTER_DAYS

STATION_NAMES = {
    "44404099999": ("Dadeldhura", "डडेल्धुरा"),
    "44406099999": ("Dipayal", "दिपायल"),
    "44409099999": ("Dhangadhi", "धनगढी"),
    "44416099999": ("Surkhet", "सुर्खेत"),
    "44418099999": ("Nepalgunj", "नेपालगन्ज"),
    "44424099999": ("Jumla", "जुम्ला"),
    "44429099999": ("Dang", "दाङ"),
    "44434099999": ("Pokhara", "पोखरा"),
    "44438099999": ("Bhairahawa", "भैरहवा"),
    "44449099999": ("Simara", "सिमरा"),
    "44454099999": ("Kathmandu Airport", "काठमाडौं विमानस्थल"),
    "44461099999": ("Syangboche", "स्याङबोचे"),
    "44462099999": ("Okhaldhunga", "ओखलढुङ्गा"),
    "44474099999": ("Taplejung", "ताप्लेजुङ"),
    "44477099999": ("Dhankuta", "धनकुटा"),
    "44478099999": ("Biratnagar", "विराटनगर"),
}

CATEGORY_TEXT = {
    "extremely_heavy": ("extremely heavy rain", "अत्यधिक भारी वर्षा"),
    "very_heavy": ("very heavy rain", "धेरै भारी वर्षा"),
    "heavy": ("heavy rain", "भारी वर्षा"),
    "moderate": ("moderate rain", "मध्यम वर्षा"),
    "light": ("light rain", "हल्का वर्षा"),
}

LEVEL_RANK = {"red": 0, "orange": 1, "yellow": 2}
_NEPALI_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


def ne_digits(value) -> str:
    return str(value).translate(_NEPALI_DIGITS)


def names(station_id: str, fallback: str = "") -> tuple[str, str]:
    return STATION_NAMES.get(station_id, (fallback.title(), fallback.title()))


def _rain_alert(row) -> dict:
    en_name, ne_name = names(row.station_id)
    day = row.obs_date.date().isoformat()
    mm = round(float(row.prcp_mm))
    en_cat, ne_cat = CATEGORY_TEXT.get(row.rain_category, (str(row.rain_category), str(row.rain_category)))

    en = [f"Barsha rain report ({en_name}): {mm} mm on {day}, {en_cat}."]
    ne = [f"वर्षा प्रतिवेदन ({ne_name}): {ne_digits(day)} मा {ne_digits(mm)} मिमि, {ne_cat}।"]
    if row.is_station_record:
        en.append(f"Wettest day in this station's record (previous highest {round(row.prior_max_mm)} mm).")
        ne.append(f"यो स्टेशनको रेकर्डमै सबैभन्दा धेरै (पहिलेको अधिकतम {ne_digits(round(row.prior_max_mm))} मिमि)।")
    elif pd.notna(row.p99_wet_mm) and row.prcp_mm >= row.p99_wet_mm:
        en.append(f"Above the level this station reaches on only 1 in 100 rainy days ({round(row.p99_wet_mm)} mm).")
        ne.append(f"यो स्टेशनमा १०० वर्षा-दिनमा १ पटक मात्र पुग्ने स्तर ({ne_digits(round(row.p99_wet_mm))} मिमि) भन्दा बढी।")
    if pd.notna(row.rain_3day_mm) and row.rain_3day_mm >= 1.2 * row.prcp_mm:
        en.append(f"{round(row.rain_3day_mm)} mm over 3 days: landslide and flood risk stays high.")
        ne.append(f"३ दिनमा {ne_digits(round(row.rain_3day_mm))} मिमि: पहिरो र बाढीको जोखिम उच्च छ।")

    return {
        "type": "EXTREME_RAIN",
        "level": row.alert_level,
        "audience": "public",
        "station_id": row.station_id,
        "obs_date": day,
        "prcp_mm": float(row.prcp_mm),
        "en": " ".join(en),
        "ne": " ".join(ne),
    }


def build_bulletin(rain_daily: pd.DataFrame, health: pd.DataFrame, as_of: date, lookback_days: int = 2) -> dict:
    alerts: list[dict] = []
    window_start = pd.Timestamp(as_of - timedelta(days=lookback_days))
    recent = rain_daily[(rain_daily["obs_date"] >= window_start) & (rain_daily["obs_date"] <= pd.Timestamp(as_of))]

    # One alert per station: its wettest day in the window.
    flagged = recent[recent["alert_level"].isin(["red", "orange"])]
    wettest = flagged.sort_values("prcp_mm", ascending=False).drop_duplicates("station_id")
    for row in wettest.itertuples():
        alerts.append(_rain_alert(row))

    for row in recent[recent["alert_level"] == "suspect"].itertuples():
        en_name, _ = names(row.station_id)
        alerts.append({
            "type": "SUSPECT_VALUE",
            "level": "review",
            "audience": "operator",
            "station_id": row.station_id,
            "obs_date": row.obs_date.date().isoformat(),
            "prcp_mm": float(row.prcp_mm),
            "en": (f"{en_name} reported {round(row.prcp_mm)} mm on {row.obs_date.date()}, over "
                   f"3x its 99.9th percentile with no heavy rain within 200 km. Held back for review."),
        })

    # The feed's age comes from every station, retired or not: when the whole feed stops,
    # all stations retire together after RETIRED_AFTER_DAYS and the lag must not vanish.
    newest = pd.to_datetime(health["last_obs"]).max() if len(health) else None
    if newest is not None and pd.isna(newest):
        newest = None
    source_lag = (pd.Timestamp(as_of) - newest).days if newest is not None else None
    reporting = health[health["status"] != "retired"]
    if source_lag is None:
        alerts.append({
            "type": "SOURCE_STALE",
            "level": "page",
            "audience": "operator",
            "en": (f"There is no station data in the lake up to {as_of.isoformat()}. "
                   "Run a backfill or check the ingest step; reports are paused, not quiet."),
        })
    elif source_lag > STALE_AFTER_DAYS:
        alerts.append({
            "type": "SOURCE_STALE",
            "level": "page",
            "audience": "operator",
            "en": (f"No station has reported for {source_lag} days (newest day {newest.date()}). "
                   "The upstream feed has stopped; reports are paused, not quiet."),
        })
    else:
        for row in reporting[reporting["status"] == "stale"].itertuples():
            en_name, _ = names(row.station_id, row.station_name)
            alerts.append({
                "type": "STATION_SILENT",
                "level": "warn",
                "audience": "operator",
                "station_id": row.station_id,
                "en": f"{en_name} has not reported since {pd.Timestamp(row.last_obs).date()}; other stations have.",
            })

    alerts.sort(key=lambda a: (a["audience"] != "public", LEVEL_RANK.get(a["level"], 9), -a.get("prcp_mm", 0)))
    return {"as_of": as_of.isoformat(), "source_lag_days": source_lag, "alerts": alerts}


def render(bulletin: dict) -> str:
    lag = bulletin["source_lag_days"]
    lag_text = "no data" if lag is None else f"{lag} days"
    lines = [f"Barsha bulletin for {bulletin['as_of']} (source lag: {lag_text})"]
    if not bulletin["alerts"]:
        lines.append("No extreme rain and no reporting problems.")
    for a in bulletin["alerts"]:
        lines.append("")
        lines.append(f"[{a['level'].upper()}] {a['en']}")
        if "ne" in a:
            lines.append(f"        {a['ne']}")
    return "\n".join(lines)
