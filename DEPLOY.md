# Stormfront deployment

Stormfront is a set of Python modules that plug into the running **Siphon**
and **Prism** services. There's no separate Stormfront process — it's a
vendor-in package of sources + lenses + consumer routes.

## Layout → target

| Stormfront file                               | Target on big-server                               |
| --------------------------------------------- | -------------------------------------------------- |
| `siphon/stormfront_convective.py`             | `/root/siphon/siphon/sources/stormfront_convective.py` |
| `siphon/consumer_route.py` (`ROUTE_SNIPPET`)  | appended once to `/root/siphon/siphon/api/consumer.py` |
| `prism/stormfront_outlook.py`                 | `/root/prism/prism/lenses/stormfront_outlook.py`   |
| *(plus import lines in two `__init__` files)* |                                                    |

## Wiring steps (done during initial deploy)

1. `scp siphon/stormfront_convective.py big-server:/root/siphon/siphon/sources/`
2. Append import to `/root/siphon/siphon/sources/__init__.py`:
   ```python
   from .stormfront_convective import StormfrontConvectiveSource  # noqa: F401  # stormfront
   ```
3. Append `ROUTE_SNIPPET` from `siphon/consumer_route.py` to the end of
   `/root/siphon/siphon/api/consumer.py`.
4. `scp prism/stormfront_outlook.py big-server:/root/prism/prism/lenses/`
5. Append import to `/root/prism/prism/lenses/registry.py`:
   ```python
       stormfront_outlook,  # stormfront
   ```
6. Add consumer route to `/root/prism/prism/api/consumer.py`:
   ```python
   @router.get("/stormfront/outlook")
   def get_stormfront_outlook():
       """Stormfront 5-day southern-UK convective outlook."""
       return _serve("stormfront_outlook")
   ```
7. Seed source + lens rows in the SQLite databases:
   ```sql
   -- siphon.db
   INSERT INTO sources
     (id, source_type, name, grp, config, poll_interval_s, ttl_s, enabled, owner_node_id)
   VALUES (
     'stormfront_convective_south_uk',
     'stormfront_convective',
     'Stormfront convective params — southern UK',
     'weather',
     '{"lat": 52.0, "lon": -1.0, "location_key": "south_uk", "forecast_days": 7}',
     900, 1200, 1, 'big'
   );

   -- prism.db
   INSERT INTO lenses
     (id, lens_type, name, config, interval_s, ttl_s, enabled)
   VALUES (
     'stormfront_outlook', 'stormfront_outlook',
     'Stormfront 5-day southern UK outlook', '{}', 900, 1200, 1
   );
   ```
8. `pm2 reload siphon && pm2 reload prism`

## Verify

```sh
# Raw siphon data (168 hours)
curl -s http://127.0.0.1:3883/api/stormfront/convective/south_uk | head -c 400

# Derived prism lens output
curl -s http://127.0.0.1:3885/api/stormfront/outlook | head -c 600

# Chaseit public outlook (hits /api/outlook proxy which hits prism)
curl -s https://chase.wispayr.online/api/outlook | head -c 400
```

## Node pinning

The source is pinned to `big` (the siphon node id of big-server). If sharding
is ever re-enabled across pu2 / bravo / big, deploy the same module files to
those nodes before unpinning.
