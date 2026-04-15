# Stormfront — Southern UK Convective Weather Model

Regional storm-chaser-focused convective intelligence for the **United Kingdom
and near-Europe**, with the **southern UK convective belt as the primary
domain**. Built on open foundation models (GraphCast / Pangu), high-cadence
radar + satellite + lightning ingest, and a diagnostics layer designed for
chase planning, intercept routing, and live nowcasting during severe weather.

Built on existing edge infrastructure: **Siphon** ingress, **Prism** fusion,
**bravo** (M4 Pro, MPS) compute, **Dispatch** for alerting, **Chaseit**
(`chase.wispayr.online`) as the public + ops surface.

---

## Who it's for

The southern UK chaser group working anything from the south coast up to a
Cambridge-ish latitude line — SW England, South Wales, the Midlands corridor,
SE England, East Anglia. Met Office / KNMI / DWD public forecasts aren't
optimised for *"where should I stage at 1400 for the best intercept on today's
line?"* — Stormfront is.

Chase questions it answers:

- Where will initiation happen, and when?
- What mode? Discrete supercell, cluster, QLCS, pulse?
- What's the hazard mix — hail, tornado, damaging wind, CG density?
- What's the road network and light situation at target time?
- Where do I stage, and what's my bail route?

---

## Coverage

**Primary domain**: Southern UK + Wales at **1 km** grid
Bounding box: `W -6.5° · E +2.5° · S 49.8° · N 53.2°`

**Secondary domain**: NW Europe (49°N–55°N, 8°W–10°E) at **4 km** grid

**Update cadence**:

- Radar nowcast: **5 min**
- Convective diagnostics: **15 min**
- Foundation-model run: **1 h** (on fresh GFS / IFS analysis)
- Chase-day mesoscale: **hourly, 6-hourly deep dive**

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  EXTERNAL FEEDS                                            │
│  IFS · GFS · ICON-EU · AROME · UKV                         │
│  OPERA radar · UK/IE radar · MSG · MTG                     │
│  Open-Meteo (convective) · Blitzortung · ATDnet            │
│  WOW · MIDAS · SYNOP · raobs · OSM                         │
└─────────────────────────┬──────────────────────────────────┘
                          ▼
┌────────────────────────────────────────────────────────────┐
│                        SIPHON                              │
│           (ingress, normalisation, sharding)               │
│                                                            │
│  stormfront_convective    (open-meteo CAPE/shear grid)     │
│  open_meteo_forecast      (existing)                       │
│  met_office_warnings      (existing)                       │
│  rainviewer               (existing)                       │
│  metar                    (existing)                       │
│  …further feeds as Stormfront grows                        │
└─────────────────────────┬──────────────────────────────────┘
                          ▼
┌────────────────────────────────────────────────────────────┐
│                        PRISM LENSES                        │
│                                                            │
│  stormfront_outlook      ← first real lens (this commit)   │
│  radar_nowcast           ← optical flow + U-Net            │
│  storm_objects           ← TITAN-style tracker             │
│  lightning_jump          ← 2σ rate detector                │
│  convective_diags        ← CAPE/CIN/SRH/SCP/STP            │
│  mode_classifier         ← discrete/cluster/QLCS/pulse     │
│  outlook_spc             ← MRGL/SLGT/ENH/MDT/HIGH          │
│  hodograph               ← cell-relative                   │
│  downscale_1km           ← residual CNN downscaling        │
└─────────────────────────┬──────────────────────────────────┘
                          ▼
┌────────────────────────────────────────────────────────────┐
│  CONSUMERS                                                 │
│  chase.wispayr.online   ·  mobile chase view               │
│  Dispatch alerts        ·  API for 3rd-party chasers       │
│  case archive           ·  live.wispayr.online overlay     │
└────────────────────────────────────────────────────────────┘
```

---

## What's wired right now (Phase 1)

- `stormfront_convective` siphon source — queries Open-Meteo for CAPE, CIN,
  lifted index, wind shear at 10m/925/700/500 hPa, precip, cloud cover over a
  southern-UK sample point. Pinned to `big-server` node.
- `stormfront_outlook` prism lens — reads the convective source, computes a
  5-day SPC-style categorical risk (NONE / MRGL / SLGT / ENH / MDT / HIGH)
  from CAPE × shear thresholds, plus a short headline, peak hour, and
  dominant hazard mix per day.
- Consumer route `GET /api/stormfront/outlook` on Prism serves the lens data.
- `chase.wispayr.online/outlook` page hits this through a proxy with
  graceful fallback to the static stub when the lens hasn't computed yet.

## What's next (Phase 2+)

- **Radar nowcast** — optical-flow tile extrapolation from RainViewer frames,
  then U-Net once training data is cached.
- **Lightning jump** — siphon Blitzortung source + prism lens detecting 2σ
  flash-rate increases (supercell maturation flag).
- **Foundation NWP on bravo** — GraphCast / Pangu inference from fresh GFS
  analyses, downscaled to 1 km UK / 4 km NW Europe with a residual CNN.
- **Storm-object tracker** — TITAN-style cell tracking on the radar composite.
- **Mode classifier** — trained on historical ESWD reports and model
  soundings, outputs discrete / cluster / QLCS / pulse labels.
- **Chase-planning layer inside chaseit** — target-box generator fed by
  initiation probability × mode × hazard × road density × sightlines.
- **Verification + case archive** — every chase day logged, every forecast
  frame persisted, skill scored vs ESWD reports.

---

## Layout

```
stormfront/
├── README.md                ← this file (the spec)
├── siphon/
│   └── stormfront_convective.py   ← deployed to /root/siphon/siphon/sources/
├── prism/
│   └── stormfront_outlook.py      ← deployed to /root/prism/prism/lenses/
└── docs/
    └── categorical-risk.md         ← CAPE × shear thresholds (to be added)
```

The files under `siphon/` and `prism/` in this repo are the authoritative
source of Stormfront's modules. Changes get rsynced to big-server's running
services. Eventually this repo will grow its own CI/CD and the copy-deploy
dance will be replaced with a proper module registry.

---

## License

MIT
