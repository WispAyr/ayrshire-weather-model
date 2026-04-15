# Ayrshire Weather Model

Plan for building a hyper-local weather model for Ayrshire, Scotland, using existing edge infrastructure (siphon ingress, prism fusion, bravo M4 Pro MPS compute) plus open foundation models and locally-assimilated observations.

The differentiator is **local observation assimilation**: nobody else is ingesting Ayrshire ADS-B MRAR winds, UniFi AP temps, camera-derived cloud cover, and ayrweather station data into a forecast loop.

---

## What's already available

- **Observations**: ayrweather stations, ayrshire-hub, lightning feeds, power outages (as severe-weather proxy), traffic/train disruption signals
- **PiAware ADS-B** at `10.2.97.188` — aircraft MRAR messages yield derived winds aloft
- **UniFi estate** — AP / camera temperature telemetry across sites
- **Iris cameras** — sky imagery usable for cloud-cover inference
- **Compute**: bravo (M4 Pro, MPS), pu2, small-server, Hailo Pi
- **Pipeline**: Siphon as ingress, Prism for fusion/correlation, Dispatch for alerting

---

## Stage 1 — Nowcasting (0–6 h)

Cheapest win, highest Ayrshire-local value.

**Siphon sources to add**
- Met Office DataHub (free tier)
- ECMWF Open Data (IFS 0.25°, free)
- NOAA GFS 0.25°
- UKV radar composite
- EUMETSAT MSG satellite
- Lightning (already ingested)

**Prism lens**: `nowcast_fusion`
- Optical-flow extrapolation on UKV radar frame pairs
- Blended with ayrweather obs + lightning strike density
- Output: 0–6 h precip / wind at 1 km Ayrshire grid

**Model**: simple U-Net (or DenseNet) on bravo MPS, trained on radar frame pairs. ~500 MB, sub-second inference per frame.

---

## Stage 2 — Short-range numerical (6 h – 10 day)

Don't build WRF/UM from scratch — use a pretrained foundation model.

**Candidates**
- **GraphCast** (DeepMind, open weights)
- **Pangu-Weather** (Huawei, open)
- **FourCastNet** (NVIDIA)

All run inference in seconds on MPS/CUDA from ERA5-shaped initial conditions.

**Flow**
1. Pull GFS 0.25° analysis (free, NOAA)
2. Run 10-day forecast locally on bravo
3. Publish as siphon source `local_nwp`
4. Downscale 0.25° → 1 km Ayrshire with a CNN trained on historical UKV vs local-obs residuals
5. Consumed by egpk.info, ayrweather, ayrpavilion, events-engine

---

## Stage 3 — Local data assimilation (the differentiator)

Collect and nudge model initial conditions toward local truth.

**Obs ingested**
- ayrweather stations (temp / humidity / pressure / wind)
- UniFi AP & camera internal temperatures (bias-corrected)
- Aircraft MRAR winds from PiAware (upper-air winds)
- Camera-derived cloud cover (Iris vision pipeline)

**Method**: 3DVAR-lite — nudge GraphCast initial conditions toward local obs before forecast run.

**Storage**: TimescaleDB on pu2 Postgres. Every obs + every forecast frame archived, becomes training set for Stage 4.

---

## Stage 4 — Verification and retraining

- Every forecast logged, every obs logged, diff computed → skill scores per lead time (1 h / 3 h / 6 h / 24 h / 72 h)
- Monthly fine-tune of downscaler on bravo
- Public skill-score dashboard on live.wispayr.online

---

## Roadmap

| Stage | Scope | Compute | Time |
|-------|-------|---------|------|
| 1 | Radar nowcast + obs fusion | bravo MPS | 1–2 weeks |
| 2 | GraphCast / Pangu inference + downscale | bravo MPS | 3–4 weeks |
| 3 | Local obs assimilation | pu2 + bravo | 4–6 weeks |
| 4 | Verification loop + retraining | bravo | ongoing |

---

## Why this works

- Radar + local obs already beat Met Office point forecasts for 0–2 h Ayrshire-local
- Optical-flow nowcasting is ~200 lines of Python
- Plugs directly into existing surfaces: egpk.info, ayrweather, ayrpavilion, events-engine (airshow go/no-go)
- Stage 1 proves the pipeline before committing to foundation-model inference infra

---

## Architecture

```
 ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
 │ External     │    │ Local obs    │    │ Foundation   │
 │ (GFS, UKV,   │    │ (ayrweather, │    │ model        │
 │  ECMWF,      │───▶│  PiAware,    │───▶│ (GraphCast)  │
 │  EUMETSAT)   │    │  UniFi, Iris)│    │  on bravo    │
 └──────────────┘    └──────────────┘    └──────┬───────┘
        │                    │                   │
        ▼                    ▼                   ▼
 ┌─────────────────────────────────────────────────────┐
 │                      Siphon                         │
 └──────────────────────────┬──────────────────────────┘
                            ▼
 ┌─────────────────────────────────────────────────────┐
 │            Prism — nowcast_fusion lens              │
 │            Prism — downscale lens                   │
 │            Prism — verification lens                │
 └──────────────────────────┬──────────────────────────┘
                            ▼
 ┌─────────────────────────────────────────────────────┐
 │  Consumers: egpk · ayrweather · ayrpavilion ·       │
 │             events-engine · live.wispayr.online     │
 └─────────────────────────────────────────────────────┘
```

---

## License

MIT
