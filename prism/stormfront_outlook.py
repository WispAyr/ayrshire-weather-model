"""Stormfront outlook lens — 5-day SPC-style categorical risk.

Reads the `stormfront_convective` siphon source (Open-Meteo CAPE + shear +
lifted index + precip over a south-UK point) and derives a day-by-day
categorical severe-weather risk.

Categorical thresholds (rough SPC analogues, tuned for UK CAPE ceilings):

    NONE   — peak CAPE  <   100 J/kg
    MRGL   — peak CAPE  >=  100 J/kg
    SLGT   — peak CAPE  >=  300 J/kg  AND peak shear >=  12 m/s
    ENH    — peak CAPE  >=  600 J/kg  AND peak shear >=  15 m/s
    MDT    — peak CAPE  >= 1000 J/kg  AND peak shear >=  18 m/s
    HIGH   — peak CAPE  >= 1500 J/kg  AND peak shear >=  22 m/s

Also produces a short headline per day based on the dominant hazard mix:

    high CAPE, high shear       → discrete supercell risk
    high CAPE, low shear        → pulse storms / heavy rain
    moderate CAPE, high shear   → squall line / cluster
    low CAPE                    → no significant convection

Output shape:

    {
        "updated": "2026-04-15T21:00:00Z",
        "location": "south_uk",
        "days": [
            {
                "date": "2026-04-16",
                "day_label": "Tomorrow",
                "level": "slgt",
                "headline": "Discrete storms possible along triple point",
                "peak_cape": 760.0,
                "peak_shear": 18.2,
                "peak_hour": "15:00",
                "hazards": ["hail", "wind"]
            },
            ...
        ]
    }
"""
from __future__ import annotations

from datetime import datetime, date, time, timezone, timedelta

from .base import BaseLens, register


@register("stormfront_outlook")
class StormfrontOutlookLens(BaseLens):
    LENS_TYPE = "stormfront_outlook"
    INPUTS = ["stormfront/convective/south_uk"]
    INTERVAL = 900  # 15 min
    TTL = 1200
    LOCATION_AWARE = False
    COMPUTE_CLASS = "light"
    AUTO_SEED = False

    async def compute(self, data: dict) -> dict:
        conv = data.get("stormfront/convective/south_uk") or {}
        hourly = conv.get("hourly") or []

        by_day: dict[str, list[dict]] = {}
        for h in hourly:
            t = h.get("t")
            if not isinstance(t, str):
                continue
            try:
                dt = datetime.fromisoformat(t)
            except ValueError:
                continue
            day_key = dt.date().isoformat()
            by_day.setdefault(day_key, []).append({**h, "_dt": dt})

        out_days: list[dict] = []
        today = datetime.now(timezone.utc).date()
        for day_key in sorted(by_day.keys())[:5]:
            rows = by_day[day_key]
            peak_cape, peak_shear, peak_row = 0.0, 0.0, None
            total_precip = 0.0
            max_cloud = 0
            for r in rows:
                c = r.get("cape_j_kg") or 0.0
                s = r.get("shear_0_6km_ms") or 0.0
                if c > peak_cape:
                    peak_cape = c
                    peak_row = r
                if s > peak_shear:
                    peak_shear = s
                total_precip += float(r.get("precip_mm") or 0.0)
                if (r.get("cloud_cover_pct") or 0) > max_cloud:
                    max_cloud = int(r.get("cloud_cover_pct") or 0)

            level = _categorical(peak_cape, peak_shear)
            hazards = _hazards(peak_cape, peak_shear, total_precip)
            headline = _headline(level, peak_cape, peak_shear, total_precip)

            d = date.fromisoformat(day_key)
            if d == today:
                day_label = "Today"
            elif d == today + timedelta(days=1):
                day_label = "Tomorrow"
            else:
                day_label = d.strftime("%A")

            peak_hour = None
            if peak_row and isinstance(peak_row.get("_dt"), datetime):
                peak_hour = peak_row["_dt"].strftime("%H:%M")

            out_days.append(
                {
                    "date": day_key,
                    "day_label": day_label,
                    "level": level,
                    "headline": headline,
                    "peak_cape": round(peak_cape, 0),
                    "peak_shear": round(peak_shear, 1),
                    "peak_hour": peak_hour,
                    "precip_mm": round(total_precip, 1),
                    "max_cloud_pct": max_cloud,
                    "hazards": hazards,
                }
            )

        return {
            "updated": datetime.now(timezone.utc).isoformat(),
            "location": "south_uk",
            "domain_bbox": {
                "west": -6.5,
                "east": 2.5,
                "south": 49.8,
                "north": 53.2,
            },
            "source": "open-meteo via siphon.stormfront_convective",
            "days": out_days,
            "upstream_ok": bool(hourly),
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


def _hazards(cape: float, shear: float, precip: float) -> list[str]:
    h: list[str] = []
    if cape >= 600:
        h.append("hail")
    if cape >= 300 and shear >= 15:
        h.append("wind")
    if cape >= 1000 and shear >= 18:
        h.append("tornado")
    if precip >= 10:
        h.append("flood")
    if cape >= 100:
        h.append("lightning")
    return h


def _headline(level: str, cape: float, shear: float, precip: float) -> str:
    if level == "none":
        return "No significant convection expected."
    if level == "mrgl":
        return f"Isolated showers / weak storms possible (CAPE ~{cape:.0f} J/kg)."
    if level == "slgt":
        if shear >= 15:
            return f"Organised storms possible — CAPE {cape:.0f}, 0-6km shear {shear:.0f} m/s."
        return f"Slow-moving multicells / pulse storms (CAPE {cape:.0f})."
    if level == "enh":
        return (
            f"Enhanced risk — discrete/clustered storms, hail and wind."
            f" CAPE {cape:.0f}, shear {shear:.0f} m/s."
        )
    if level == "mdt":
        return (
            f"Moderate risk — supercell potential, severe hail and wind likely."
            f" CAPE {cape:.0f}, shear {shear:.0f} m/s."
        )
    if level == "high":
        return (
            f"High risk — significant severe weather, tornado threat."
            f" CAPE {cape:.0f}, shear {shear:.0f} m/s."
        )
    return "Convective risk TBD."
