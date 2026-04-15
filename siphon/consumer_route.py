"""Stormfront consumer route injection for siphon.

This snippet is appended to /root/siphon/siphon/api/consumer.py so that prism
lenses can read the stormfront_convective source through a semantic endpoint
(`/api/stormfront/convective/{location_key}`) rather than the internal
source-id cache key.

Kept here in the stormfront repo as the authoritative source; the deploy
process appends it to siphon's consumer.py once.
"""

# ruff: noqa: E501

ROUTE_SNIPPET = '''

# ─── Stormfront ──────────────────────────────────────────────
@router.get("/api/stormfront/convective/{location_key}")
async def get_stormfront_convective(location_key: str):
    """Stormfront convective parameters (CAPE/shear/precip/cloud) for a grid point."""
    data = cache.get(f"stormfront_convective:{location_key}")
    if not data or not data.get("data"):
        raise HTTPException(503, "Stormfront convective data not yet available")
    return JSONResponse(data["data"])
'''
