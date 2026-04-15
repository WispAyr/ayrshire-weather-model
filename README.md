# Stormfront — Regional Convective Weather Model

A regional, storm-chaser-focused weather model for the UK and near-Europe. Built on open foundation models (GraphCast / Pangu), high-cadence radar + satellite + lightning ingest, and a convective diagnostics layer designed for chase planning, intercept routing, and live nowcasting during severe weather.

Built on existing edge infrastructure: **Siphon** ingress, **Prism** fusion, **bravo** (M4 Pro, MPS) compute, **Dispatch** for alerting.

---

## Who this is for

Storm chasers, spotters, and severe-weather photographers operating across the UK, Ireland, and the near Continent (Benelux, N France, N Germany). The gap: Met Office / KNMI / DWD forecasts are optimised for public warnings, not for *"where should I stage at 1400 for the best intercept on today's line?"*

This model answers chase questions:

- **Where will initiation happen, and when?**
- **What mode? Discrete supercell, cluster, QLCS, pulse?**
- **What's the hazard mix — hail, tornado, damaging wind, CG density?**
- **What's the road network and light situation at target time?**
- **Where do I stage, and what's my bail route?**

---

## Coverage

**Primary domain**: UK + Ireland at **1 km** grid
**Secondary domain**: NW Europe (50°N–60°N, 10°W–15°E) at **4 km** grid
**Update cadence**:
- Radar nowcast: **5 min**
- Convective diagnostics: **15 min**
- Foundation-model run: **1 h** (on fresh GFS / IFS analysis)
- Chase-day mesoscale: **hourly, 6-hourly deep dive**

---

## Core outputs

### Nowcast (0–3 h)
- Composite radar extrapolation (optical flow + U-Net)
- Lightning jump detection (2σ rate increase → supercell maturation flag)
- Storm object tracking (TITAN-style) with motion vectors
- Hail size proxy from radar (MESH, VIL density, 50 dBZ echo top)
- Mesocyclone / TVS flags from dual-pol where available

### Convective outlook (3–24 h)
- CAPE / CIN / LCL / LFC / EL at surface, ML, MU
- 0–1 km & 0–6 km shear, SRH, effective bulk shear
- Supercell Composite Parameter, Significant Tornado Parameter, Significant Hail Parameter
- **SPC-style categorical outlook** (MRGL / SLGT / ENH / MDT / HIGH) on model grid
- Initiation probability surface (CIN erosion + convergence)
- Convective mode classification (discrete / cluster / QLCS / pulse)

### Chase-planning layer
- Target boxes with stage-point recommendations (high ground, road density, sightlines)
- Intercept-time ETA from chosen start point (road graph routing)
- Sun angle / golden hour overlay at target time
- Bail-route suggestion (opposite storm motion, nearest hardtop)
- Cell-relative hodographs clickable on map

### Hodographs & soundings
- Forecast sounding at any point, any lead time
- Cell-relative hodograph with critical angle, streamwise vorticity
- Observed raobs (Lerwick, Castor Bay, Herstmonceux, De Bilt, Essen) assimilated + delta-plotted

---

## Data sources (all via Siphon)

**Numerical**
- ECMWF IFS Open Data (0.25°, 4x daily)
- NOAA GFS (0.25°, 4x daily)
- Met Office DataHub (UKV where available)
- DWD ICON-EU (open data, 6.5 km)
- Météo-France AROME (1.3 km, where redistributable)

**Radar**
- UK composite (Met Office)
- Ireland (Met Éireann)
- KNMI DWD RADOLAN composite
- OPERA European radar composite
- Each ingested as raw frames for extrapolation — not just rendered tiles

**Lightning**
- Blitzortung (free network, raw strokes)
- MetOffice ATDnet (where licensed)
- ENTLN / Vaisala GLD360 (commercial, optional)

**Satellite**
- EUMETSAT MSG (15 min, IR / WV / VIS)
- EUMETSAT MTG-I (when operational, 10 min rapid scan)
- Convective mask from IR brightness temperature gradient

**Upper air**
- All UK/Ireland/NW-Europe raobs (00/12Z)
- PiAware-derived MRAR winds (local, continuous)

**Surface**
- WOW + Met Office MIDAS
- KNMI EDR, DWD SYNOP feeds
- Ayrweather + UniFi estate (local anchors)

**Road & logistics (chase layer)**
- OSM road graph (for routing and stage-point scoring)
- Highways England / Traffic Scotland / AA closures
- Solar ephemeris for light planning

---

## Stage plan

### Stage 1 — Radar + lightning nowcast core
Optical-flow + U-Net radar extrapolation, storm object tracker, lightning jump detector. Output: 0–3 h convective nowcast tiles + object database.

### Stage 2 — Foundation-model NWP
GraphCast / Pangu inference on bravo MPS from fresh GFS+IFS analyses. Output: 10-day global forecast → cropped to regional domains → downscaled to 1 km UK / 4 km NW Europe via residual CNN.

### Stage 3 — Convective diagnostics
Derive full parameter stack (CAPE/shear/helicity/composites) on the downscaled grid. Mode classifier trained on historical ESWD reports + model soundings. SPC-style categorical outlook generator.

### Stage 4 — Chase-planning layer
Target-box generator (initiation prob × mode × hazard × road density × sightlines). Intercept router. Hodograph explorer. Sounding sampler.

### Stage 5 — Verification & case archive
Every forecast frame + every ESWD / ESSL report logged. Skill scores by lead time, by parameter, by storm mode. Post-event case studies auto-generated (*"19 June 2026 Kent supercell — forecast vs obs"*).

### Stage 6 — Live ops surface
`stormfront.wispayr.online`:
- Real-time map with all layers toggleable
- Chase-day dashboard with target boxes and hodograph explorer
- Mobile-first intercept view (GPS-aware, single-cell focus)
- Dispatch-backed SMS / push alerts on trigger thresholds

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  EXTERNAL FEEDS                                            │
│  IFS · GFS · ICON-EU · AROME · UKV                         │
│  OPERA radar · UK/IE radar · MSG · MTG                     │
│  Blitzortung · ATDnet · ENTLN                              │
│  WOW · MIDAS · SYNOP · raobs · OSM                         │
└─────────────────────────┬──────────────────────────────────┘
                          ▼
┌────────────────────────────────────────────────────────────┐
│                        SIPHON                              │
│           (ingress, normalisation, sharding)               │
└─────────────────────────┬──────────────────────────────────┘
                          ▼
┌────────────────────────────────────────────────────────────┐
│                        PRISM LENSES                        │
│                                                            │
│  radar_nowcast   │  storm_objects  │  lightning_jump       │
│  foundation_nwp  │  downscale_1km  │  convective_diags     │
│  mode_classifier │  outlook_spc    │  chase_targets        │
│  hodograph       │  sounding       │  verification         │
└─────────────────────────┬──────────────────────────────────┘
                          ▼
┌────────────────────────────────────────────────────────────┐
│  CONSUMERS                                                 │
│  stormfront.wispayr.online  ·  mobile chase view           │
│  Dispatch alerts            ·  API for 3rd-party chasers   │
│  case archive               ·  live.wispayr.online overlay │
└────────────────────────────────────────────────────────────┘
```

---

## Compute profile

| Workload | Node | Notes |
|----------|------|-------|
| Radar nowcast U-Net | bravo MPS | 5-min cadence, <5 s inference |
| GraphCast / Pangu | bravo MPS | ~60 s per 10-day run, hourly |
| Downscale CNN | bravo MPS | 1 km UK + 4 km Europe, hourly |
| Diagnostics (CAPE/shear) | pu2 CPU | vectorised numpy, ~2 min |
| Object tracker | pu2 CPU | streaming, <1 s per frame |
| Storage (TimescaleDB) | pu2 Postgres | all obs + forecasts archived |
| Live surface | big-server | Next.js + tile cache |

---

## Why this works for chasers

1. **Chase-native outputs.** Not re-skinned public forecasts — target boxes, hodographs, intercept routing, bail routes.
2. **Local assimilation.** PiAware MRAR winds, WOW, and local stations nudge initial conditions — especially valuable for the UK where upper-air coverage is thin.
3. **Radar-first nowcast.** Five-minute cadence object tracking with lightning jump flags catches maturation faster than public products.
4. **Foundation-model NWP.** GraphCast-class skill at 0.25° beats most operational global models on medium range, free to run.
5. **Case-archived.** Every chase day becomes a training example — the model gets sharper over a UK/Europe convective season.
6. **Mobile-first live ops.** Built for being in the field, not at a desk.

---

## Roadmap

| Stage | Scope | Time |
|-------|-------|------|
| 1 | Radar + lightning nowcast core | 2–3 weeks |
| 2 | Foundation NWP + downscaling | 4–6 weeks |
| 3 | Convective diagnostics + mode classifier | 3–4 weeks |
| 4 | Chase-planning layer | 3–4 weeks |
| 5 | Verification + case archive | ongoing |
| 6 | Live ops surface + mobile | 4 weeks |

---

## License

MIT
