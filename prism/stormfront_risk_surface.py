"""Stormfront risk surface lens — per-day × per-grid-point categorical risk.

Reads every `stormfront_convective` siphon source across the southern UK
sample grid and produces a **5-day** stack of GeoJSON FeatureCollections
— one per day — each with one point per sample, tagged with that day's
peak CAPE / shear / LPI and the derived categorical level.

The chaseit /outlook page renders this as a scrubbable risk-surface map:
click "Today", "Tomorrow", ... to see how the spatial risk distribution
evolves through the week.

Points (as of Phase 2C):

    south_uk   52.00°N  -1.00°E   Midlands central
    sw         50.73°N  -3.53°E   South West (Exeter)
    wales      51.48°N  -3.18°E   South Wales (Cardiff)
    south      50.90°N  -1.40°E   South coast (Southampton)
    se         51.27°N   0.52°E   South East (Maidstone)
    east       52.63°N   1.30°E   East Anglia (Norwich)
"""
from __future__ import annotations

from datetime import datetime, timezone, date, timedelta

from .base import BaseLens, register


GRID_POINTS = [
    {"key": "south_uk", "label": "Midlands",    "lat": 52.00, "lon": -1.00},
    {"key": "sw",       "label": "South West",  "lat": 50.73, "lon": -3.53},
    {"key": "wales",    "label": "Wales",       "lat": 51.48, "lon": -3.18},
    {"key": "south",    "label": "South coast", "lat": 50.90, "lon": -1.40},
    {"key": "se",       "label": "South East",  "lat": 51.27, "lon":  0.52},
    {"key": "east",     "label": "East Anglia", "lat": 52.63, "lon":  1.30},
]


@register("stormfront_risk_surface")
class StormfrontRiskSurfaceLens(BaseLens):
    LENS_TYPE = "stormfront_risk_surface"
    INPUTS = [f"stormfront/convective/{p['key']}" for p in GRID_POINTS]
    INTERVAL = 900
    TTL = 1200
    LOCATION_AWARE = False
    COMPUTE_CLASS = "light"
    AUTO_SEED = False

    async def compute(self, data: dict) -> dict:
        today = datetime.now(timezone.utc).date()
        target_dates = [today + timedelta(days=i) for i in range(5)]

        # Pre-group every point's hourly data by date so we only iterate
        # each upstream response once.
        per_point_hours: dict[str, dict[date, list[dict]]] = {}
        for point in GRID_POINTS:
            input_key = f"stormfront/convective/{point['key']}"
            upstream = data.get(input_key) or {}
            hourly = upstream.get("hourly") or []
            by_day: dict[date, list[dict]] = {}
            for h in hourly:
                d = _day_of(h)
                if d is None:
                    continue
                by_day.setdefault(d, []).append(h)
            per_point_hours[point["key"]] = by_day

        days_out: list[dict] = []
        overall_max_value = 0
        overall_max_key = "none"

        for d in target_dates:
            features: list[dict] = []
            level_counts = {
                "none": 0,
                "mrgl": 0,
                "slgt": 0,
                "enh": 0,
                "mdt": 0,
                "high": 0,
            }
            day_max_value = 0
            day_max_key = "none"

            for point in GRID_POINTS:
                rows = per_point_hours.get(point["key"], {}).get(d, [])
                peak_cape = 0.0
                peak_shear = 0.0
                peak_lpi = 0.0
                peak_hour: str | None = None
                precip = 0.0
                for h in rows:
                    c = float(h.get("cape_j_kg") or 0.0)
                    s = float(h.get("shear_0_6km_ms") or 0.0)
                    lp = float(h.get("lightning_potential") or 0.0)
                    if c > peak_cape:
                        peak_cape = c
                        peak_hour = _hour_of(h)
                    if s > peak_shear:
                        peak_shear = s
                    if lp > peak_lpi:
                        peak_lpi = lp
                    precip += float(h.get("precip_mm") or 0.0)

                level = _categorical(peak_cape, peak_shear)
                level_counts[level] = level_counts.get(level, 0) + 1
                value = _LEVEL_VALUE[level]
                if value > day_max_value:
                    day_max_value = value
                    day_max_key = level

                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [point["lon"], point["lat"]],
                        },
                        "properties": {
                            "key": point["key"],
                            "label": point["label"],
                            "level": level,
                            "peak_cape": round(peak_cape, 0),
                            "peak_shear": round(peak_shear, 1),
                            "peak_lpi": round(peak_lpi, 2),
                            "peak_hour": peak_hour,
                            "precip_mm": round(precip, 1),
                            "upstream_ok": bool(rows),
                        },
                    }
                )

            days_out.append(
                {
                    "date": d.isoformat(),
                    "day_label": _day_label(d, today),
                    "max_level": day_max_key,
                    "level_counts": level_counts,
                    "features": features,
                }
            )

            if day_max_value > overall_max_value:
                overall_max_value = day_max_value
                overall_max_key = day_max_key

        today_features = days_out[0]["features"] if days_out else []
        today_counts = (
            days_out[0]["level_counts"]
            if days_out
            else {k: 0 for k in _LEVEL_VALUE}
        )
        today_max = days_out[0]["max_level"] if days_out else "none"

        return {
            "updated": datetime.now(timezone.utc).isoformat(),
            "date": today.isoformat(),
            "location": "south_uk",
            "domain_bbox": {
                "west": -6.5,
                "east": 2.5,
                "south": 49.8,
                "north": 53.2,
            },
            # Today-only fields kept for backwards compat with the v1
            # /api/risk-surface shape consumed by chaseit before 5-day support.
            "features": today_features,
            "max_level": today_max,
            "level_counts": today_counts,
            "point_count": len(today_features),
            # New v2 fields — scrubbable 5-day stack.
            "days": days_out,
            "overall_max_level": overall_max_key,
        }


_LEVEL_VALUE = {
    "none": 0,
    "mrgl": 1,
    "slgt": 2,
    "enh": 3,
    "mdt": 4,
    "high": 5,
}


def _categorical(cape: float, shear: float) -> str:
    if cape >= 1500 and shear >= 22:
        return "high"
    if cape >= 1000 and shear >= 18:
        return "mdt"
    if cape >= 600 and shear >= 15:
        return "enh"
    if cape >= 300 and shear >= 12:
        return "slgt"
    if cape >= 100:
        return "mrgl"
    return "none"


def _day_of(h: dict) -> date | None:
    t = h.get("t")
    if not isinstance(t, str):
        return None
    try:
        return datetime.fromisoformat(t).date()
    except ValueError:
        return None


def _day_label(d: date, today: date) -> str:
    if d == today:
        return "Today"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return d.strftime("%A")


def _hour_of(h: dict) -> str | None:
    t = h.get("t")
    if not isinstance(t, str):
        return None
    try:
        return datetime.fromisoformat(t).strftime("%H:%M")
    except ValueError:
        return None
