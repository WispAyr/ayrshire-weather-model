"""Stormfront convective source — Open-Meteo CAPE / shear / convective params.

Queries the Open-Meteo forecast API for the fields a storm-chaser cares about
that the existing open_meteo_forecast source doesn't expose: CAPE, CIN, lifted
index, wind shear between pressure levels, surface wind, precipitation.

Config:
    lat            (float, required) — centre latitude
    lon            (float, required) — centre longitude
    location_key   (str, required)   — cache key suffix, e.g. "south_uk"
    forecast_days  (int, optional)   — default 7, max 16

Output shape:
    {
        "location": "south_uk",
        "lat": 52.3, "lon": -1.0,
        "updated": "2026-04-15T21:00:00Z",
        "hourly": [
            {
                "t": "2026-04-15T22:00",  # local time string
                "cape_j_kg": 18.0,
                "cin_j_kg": -35.0,
                "lifted_index": 3.2,
                "shear_0_6km_ms": 12.3,
                "wind_u_10m_ms": -4.1,
                "wind_v_10m_ms":  2.6,
                "precip_mm": 0.0,
                "cloud_cover_pct": 65
            },
            ...
        ]
    }
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

import httpx

from .base import BaseSource, register


@register("stormfront_convective")
class StormfrontConvectiveSource(BaseSource):
    """Open-Meteo convective parameters for a grid point."""

    CONFIG_SCHEMA = {
        "lat": {"type": "number", "label": "Latitude", "required": True},
        "lon": {"type": "number", "label": "Longitude", "required": True},
        "location_key": {
            "type": "string",
            "label": "Location Key",
            "required": True,
        },
        "forecast_days": {
            "type": "number",
            "label": "Forecast days",
            "required": False,
        },
    }

    async def fetch(self, client: httpx.AsyncClient) -> dict:
        lat = float(self.config["lat"])
        lon = float(self.config["lon"])
        days = int(self.config.get("forecast_days", 7))
        hourly_vars = ",".join(
            [
                "cape",
                "convective_inhibition",
                "lifted_index",
                "lightning_potential",
                "freezing_level_height",
                "boundary_layer_height",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "wind_speed_925hPa",
                "wind_direction_925hPa",
                "wind_speed_700hPa",
                "wind_direction_700hPa",
                "wind_speed_500hPa",
                "wind_direction_500hPa",
                "precipitation",
                "cloud_cover",
                "temperature_2m",
                "dew_point_2m",
            ]
        )
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly={hourly_vars}"
            "&wind_speed_unit=ms&temperature_unit=celsius"
            "&timezone=Europe%2FLondon"
            f"&forecast_days={days}"
        )
        resp = await client.get(url, timeout=20.0)
        resp.raise_for_status()
        return resp.json()

    def parse(self, raw_data: dict) -> dict:
        loc_key = self.config.get("location_key", self.source_id)
        lat = float(self.config["lat"])
        lon = float(self.config["lon"])

        h = raw_data.get("hourly") or {}
        times = h.get("time") or []
        cape = h.get("cape") or []
        cin = h.get("convective_inhibition") or []
        li = h.get("lifted_index") or []
        lpi = h.get("lightning_potential") or []
        fl = h.get("freezing_level_height") or []
        blh = h.get("boundary_layer_height") or []
        precip = h.get("precipitation") or []
        cloud = h.get("cloud_cover") or []
        t2m = h.get("temperature_2m") or []
        td2m = h.get("dew_point_2m") or []
        ws10 = h.get("wind_speed_10m") or []
        wd10 = h.get("wind_direction_10m") or []
        gust10 = h.get("wind_gusts_10m") or []
        ws925 = h.get("wind_speed_925hPa") or []
        wd925 = h.get("wind_direction_925hPa") or []
        ws700 = h.get("wind_speed_700hPa") or []
        wd700 = h.get("wind_direction_700hPa") or []
        ws500 = h.get("wind_speed_500hPa") or []
        wd500 = h.get("wind_direction_500hPa") or []

        out = []
        n = len(times)
        for i in range(n):
            # Compute 0-6 km shear magnitude as |V_500 − V_10|. 500 hPa is
            # ~5.5 km so this is a reasonable proxy without needing 6 km
            # interpolation. Both components in m/s.
            u10, v10 = _uv(ws10, wd10, i)
            u500, v500 = _uv(ws500, wd500, i)
            shear = (
                math.hypot(u500 - u10, v500 - v10)
                if None not in (u10, v10, u500, v500)
                else None
            )
            u925, v925 = _uv(ws925, wd925, i)
            u700, v700 = _uv(ws700, wd700, i)
            shear_lowmid = (
                math.hypot(u700 - u925, v700 - v925)
                if None not in (u925, v925, u700, v700)
                else None
            )

            out.append(
                {
                    "t": _safe(times, i),
                    "cape_j_kg": _fnum(cape, i),
                    "cin_j_kg": _fnum(cin, i),
                    "lifted_index": _fnum(li, i),
                    "lightning_potential": _fnum(lpi, i),
                    "freezing_level_m": _fnum(fl, i),
                    "boundary_layer_m": _fnum(blh, i),
                    "shear_0_6km_ms": shear,
                    "shear_lowmid_ms": shear_lowmid,
                    "wind_u_10m_ms": u10,
                    "wind_v_10m_ms": v10,
                    "gust_10m_ms": _fnum(gust10, i),
                    "precip_mm": _fnum(precip, i),
                    "cloud_cover_pct": _inum(cloud, i),
                    "temp_c": _fnum(t2m, i),
                    "dew_c": _fnum(td2m, i),
                }
            )

        return {
            "location": loc_key,
            "lat": lat,
            "lon": lon,
            "updated": datetime.now(timezone.utc).isoformat(),
            "hourly": out,
        }

    def cache_key(self) -> str:
        return f"stormfront_convective:{self.config.get('location_key', self.source_id)}"


def _fnum(arr, i):
    v = _safe(arr, i)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _inum(arr, i):
    v = _safe(arr, i)
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe(arr, i):
    return arr[i] if i < len(arr) else None


def _uv(speed_arr, dir_arr, i):
    """Convert (speed, dir_from) to (u, v). Dir is meteorological
    'from' direction in degrees."""
    s = _fnum(speed_arr, i)
    d = _fnum(dir_arr, i)
    if s is None or d is None:
        return None, None
    # 'from' direction → convert to 'to' vector
    rad = math.radians((d + 180) % 360)
    u = s * math.sin(rad)
    v = s * math.cos(rad)
    return u, v
