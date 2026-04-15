"""Stormfront Met Office warnings — multi-region aggregator.

The existing `met_office_warnings` source is hardcoded to Strathclyde (RSS
region 'st'). Stormfront operates across southern UK, so this source fetches
every south-UK Met Office region's warnings RSS in parallel and aggregates
into a single south_uk view, preserving per-warning region label.

Met Office RSS region codes:
    se — South East England
    sw — South West England
    wl — Wales
    he — East of England
    mi — Midlands
    (we skip Northern regions — chasers working south of Cambridge)

Config:
    regions        (list, optional)  — override region list
    location_key   (str, optional)   — cache key suffix, default "south_uk"

Output shape:
    {
        "location": "south_uk",
        "source": "Met Office RSS",
        "updated": "2026-04-15T22:30:00Z",
        "regions": ["se", "sw", "wl", "he", "mi"],
        "warnings": [
            {
                "region": "se",
                "region_name": "South East England",
                "title": "Yellow warning of thunderstorms",
                "severity": "yellow",
                "hazard": "Thunder",
                "valid_from": "...",
                "valid_to": "...",
                "areas": ["Kent", "East Sussex"],
                "link": "https://www.metoffice.gov.uk/...",
                "icon_url": "...",
            },
            ...
        ],
        "count_by_severity": {"red": 0, "amber": 0, "yellow": 2}
    }
"""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from .base import BaseSource, register


REGION_URL = (
    "https://www.metoffice.gov.uk/public/data/PWSCache/WarningsRSS/Region/{code}"
)

REGION_NAMES = {
    "se": "South East England",
    "sw": "South West England",
    "wl": "Wales",
    "he": "East of England",
    "mi": "Midlands",
    "st": "Strathclyde",
    "nw": "North West England",
    "ne": "North East England",
    "ye": "Yorkshire & Humber",
}

SOUTH_UK_DEFAULT = ["se", "sw", "wl", "he", "mi"]


def _parse_validity(desc: str) -> tuple[str | None, str | None]:
    m = re.search(
        r"Valid\s+from\s+(\d{4}\s+\w+\s+\w+\s+\d+\s+\w+\s+\d{4})\s+to\s+"
        r"(\d{4}\s+\w+\s+\w+\s+\d+\s+\w+\s+\d{4})",
        desc,
        re.IGNORECASE,
    )
    if m:
        return m.group(1), m.group(2)
    m2 = re.search(
        r"(\d{4}\s+\w+\s+\d+\s+\w+)\s+to\s+(\d{4}\s+\w+\s+\d+\s+\w+)",
        desc,
        re.IGNORECASE,
    )
    if m2:
        return m2.group(1), m2.group(2)
    return None, None


def _parse_areas(desc: str) -> list[str]:
    m = re.search(r"(?:affecting|for)\s*:?\s*(.+?)(?:\.|$)", desc, re.IGNORECASE)
    if m:
        raw = m.group(1)
        areas = [a.strip() for a in re.split(r",\s*|\s+and\s+", raw) if a.strip()]
        return [a for a in areas if len(a) > 2]
    return []


def _severity(title: str) -> str:
    t = title.lower()
    if "red" in t:
        return "red"
    if "amber" in t:
        return "amber"
    return "yellow"


def _hazard(title: str) -> str:
    t = title.lower()
    for h in (
        "Thunder",
        "Lightning",
        "Wind",
        "Rain",
        "Snow",
        "Ice",
        "Fog",
        "Extreme heat",
        "Flooding",
    ):
        if h.lower() in t:
            return h
    return "Unknown"


def _parse_rss(region: str, text: str) -> list[dict]:
    out: list[dict] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return out
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        desc = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title:
            continue
        valid_from, valid_to = _parse_validity(desc)
        areas = _parse_areas(desc)
        enclosure = item.find("enclosure")
        icon_url = enclosure.get("url") if enclosure is not None else None
        out.append(
            {
                "region": region,
                "region_name": REGION_NAMES.get(region, region.upper()),
                "title": title,
                "description": desc,
                "severity": _severity(title),
                "hazard": _hazard(title),
                "valid_from": valid_from,
                "valid_to": valid_to,
                "areas": areas,
                "link": link,
                "icon_url": icon_url,
            }
        )
    return out


@register("stormfront_warnings")
class StormfrontWarningsSource(BaseSource):
    """Aggregated Met Office warnings for southern UK."""

    CONFIG_SCHEMA = {
        "regions": {
            "type": "array",
            "label": "Region codes",
            "required": False,
        },
        "location_key": {
            "type": "string",
            "label": "Cache key suffix",
            "required": False,
        },
    }

    async def fetch(self, client: httpx.AsyncClient) -> dict:
        regions = self.config.get("regions") or SOUTH_UK_DEFAULT
        if not isinstance(regions, list):
            regions = SOUTH_UK_DEFAULT

        async def one(region: str) -> tuple[str, str | None]:
            url = REGION_URL.format(code=region)
            try:
                resp = await client.get(url, timeout=12.0)
                resp.raise_for_status()
                return region, resp.text
            except Exception:
                return region, None

        results = await asyncio.gather(*(one(r) for r in regions))
        return {
            "regions": regions,
            "rss": {region: text for region, text in results if text},
        }

    def parse(self, raw_data: dict) -> dict:
        regions = raw_data.get("regions") or SOUTH_UK_DEFAULT
        rss_map = raw_data.get("rss") or {}
        warnings: list[dict] = []
        for region in regions:
            text = rss_map.get(region)
            if not text:
                continue
            warnings.extend(_parse_rss(region, text))

        counts = {"red": 0, "amber": 0, "yellow": 0}
        for w in warnings:
            sev = w.get("severity", "yellow")
            if sev in counts:
                counts[sev] += 1

        loc_key = self.config.get("location_key", "south_uk")
        return {
            "location": loc_key,
            "source": "Met Office RSS",
            "updated": datetime.now(timezone.utc).isoformat(),
            "regions": regions,
            "warnings": warnings,
            "count_by_severity": counts,
            "count": len(warnings),
        }

    def cache_key(self) -> str:
        return f"stormfront_warnings:{self.config.get('location_key', 'south_uk')}"
