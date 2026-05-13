# Cellebrite Geocoder — Server Deploy Instructions

**Audience:** server-side Claude (and any human operator) on the
investigation-platform deploy box.
**What this enables:** the G4 + G5 Phase D work — Location nodes
ingested from Cellebrite reports get an `address` / `place_name` /
`country` / `admin1` / `admin2` stamped on them at ingestion time, and
the new `place:london` and `near:51.5,-0.1,5km` search operators
become useful.

The code is already on `origin/main` (commits `e8acbee` G4 +
`8550415` G5). It's **default-OFF** — until the server is configured
the operators are a no-op and Location nodes carry no geocode metadata.
Nothing breaks; it just doesn't activate.

---

## Choose your install path

There are three valid deploy postures. Pick one.

| Path | Detail level | Disk | Setup time | Ongoing cost |
|---|---|---|---|---|
| **A. Off** | None — no geocoding | 0 | 0 | None |
| **B. GeoNames only** | City + country, no street | ~50 MB | ~5 min | None |
| **C. Nominatim + GeoNames fallback** | Full street-level + city fallback | ~5–150 GB depending on region | 30 min – 12 hours | None |

**Recommended starter:** path B today, path C as a follow-up.

---

## Path B — GeoNames only (recommended starter)

Gives you city + country level reverse-geocoding, in-process, no
external services. Good enough for ~80% of investigative geo
filtering ("messages from Spain", "calls in London").

### Steps on the deploy box

1. **Install the optional Python package** into the backend's venv:

   ```bash
   sudo /home/conorbowles51/app_v2/venv/bin/pip install reverse-geocoder
   ```

   This pulls `numpy` + `scipy` as transitive deps (~50 MB total).
   First import lazy-loads a ~50 MB lookup tree into RAM; cached
   thereafter for the lifetime of the backend process.

2. **Set the env var** for the backend service:

   ```bash
   sudo systemctl edit owl-backend
   ```

   In the editor, add (or merge into existing `[Service]` block):

   ```
   [Service]
   Environment="GEOCODER=geonames"
   ```

   Save + exit. systemd writes this to a drop-in override (so
   `systemctl cat owl-backend` will show it merged with the unit).

3. **Restart the backend:**

   ```bash
   sudo systemctl restart owl-backend
   sudo systemctl status owl-backend --no-pager
   ```

4. **Verify** the geocoder is loaded:

   ```bash
   curl -s http://localhost:8000/api/cellebrite/geocoder/status \
        -H "Authorization: Bearer <YOUR_TOKEN>" | jq .
   ```

   Expected output:

   ```json
   {
     "primary": "geonames",
     "primary_ready": true,
     "fallback": null,
     "fallback_ready": false,
     "url": null
   }
   ```

   If `primary_ready` is `false`, the `pip install` didn't take —
   check `journalctl -u owl-backend | grep -i geocoder` for the
   warning the geocoder module logs at startup.

5. **Re-ingest at least one Cellebrite case** so new Location nodes
   start carrying the geocoded fields. Existing nodes from before the
   re-ingest stay un-geocoded (a backfill pass can be added later if
   needed). Confirm via the Locations tab — clicking a row should show
   `place_name` + `country` in the rail; the bottom-right of the row
   in the table should display `via geonames` chip.

---

## Path C — Nominatim primary + GeoNames fallback (production)

Adds a self-hosted Nominatim service for full street-level addresses.
GeoNames stays as the fallback so points the Nominatim install
doesn't cover (e.g. outside an Europe-only import) still resolve to
city/country level.

### Prerequisites

- Path B already done (you want the GeoNames fallback)
- Docker installed and running on the deploy box
- ~5 GB free disk for Europe-only, more for wider region (see table)
- Decision: **what region scope?**

| Region | OSM dump URL | Disk | Import time |
|---|---|---|---|
| Europe only | `https://download.geofabrik.de/europe-latest.osm.pbf` | ~5 GB | ~30 min |
| North America | `https://download.geofabrik.de/north-america-latest.osm.pbf` | ~10 GB | ~1 hour |
| Worldwide | `https://download.geofabrik.de/planet-latest.osm.pbf` | ~150 GB | ~12+ hours |

**The Nominatim instance can only resolve points inside the imported
region.** Points outside fall through to GeoNames (city-level only).

### Steps on the deploy box

1. **Pull and run the Nominatim Docker image:**

   ```bash
   docker run -d --name nominatim --restart=unless-stopped \
     -e PBF_URL=https://download.geofabrik.de/europe-latest.osm.pbf \
     -e IMPORT_WIKIPEDIA=false \
     -p 8080:8080 \
     -v nominatim-data:/var/lib/postgresql/14/main \
     -v nominatim-flatnode:/nominatim/flatnode \
     mediagis/nominatim:4.4
   ```

   Substitute the `PBF_URL` for your chosen region. Setting
   `IMPORT_WIKIPEDIA=false` skips ~5 GB of Wikipedia importance
   data; the trade-off is slightly worse ranking when multiple
   places share a name.

2. **Watch the import finish.** This takes a while:

   ```bash
   docker logs -f nominatim
   ```

   Look for `Setup finished.` followed by the HTTP server starting.
   Until then, the container is busy importing the OSM dump into
   PostgreSQL.

3. **Sanity-check Nominatim is serving:**

   ```bash
   curl -s 'http://localhost:8080/reverse?lat=51.5074&lon=-0.1278&format=jsonv2' | jq '.display_name'
   ```

   Expected: a real address string for Westminster, London (or
   wherever your test point is). If `null` or empty, the import
   probably hasn't finished or the region doesn't cover that point.

4. **Update the backend env vars:**

   ```bash
   sudo systemctl edit owl-backend
   ```

   Replace any existing `GEOCODER=...` line with:

   ```
   [Service]
   Environment="GEOCODER=nominatim"
   Environment="GEOCODER_URL=http://localhost:8080"
   Environment="GEOCODER_FALLBACK=geonames"
   ```

   Optional tuning:

   ```
   Environment="GEOCODER_TIMEOUT_S=2.0"           # default 2s; bump if slow
   Environment="GEOCODER_USER_AGENT=owl-cbm/1.0"  # default; sent to Nominatim
   ```

5. **Restart + verify:**

   ```bash
   sudo systemctl restart owl-backend
   curl -s http://localhost:8000/api/cellebrite/geocoder/status \
        -H "Authorization: Bearer <YOUR_TOKEN>" | jq .
   ```

   Expected output:

   ```json
   {
     "primary": "nominatim",
     "primary_ready": true,
     "fallback": "geonames",
     "fallback_ready": true,
     "url": "http://localhost:8080"
   }
   ```

6. **Re-ingest a case** to populate `address` (street-level) on its
   Location nodes. The Locations tab should now show full addresses,
   not just city/country.

---

## Per-case backfill of existing locations (optional, defer-friendly)

Locations ingested **before** the geocoder was switched on have no
address fields. They still render fine — the UI just shows `—` for
those rows. There's no automated backfill yet; add this only if a
specific case needs it.

Ad-hoc script (run on the deploy box, in the backend venv):

```bash
PYTHONPATH=backend /home/conorbowles51/app_v2/venv/bin/python -c "
from services.geocoder import reverse_geocode
from services.neo4j_service import Neo4jService

case_id = 'CASE_ID_HERE'
svc = Neo4jService()
with svc._driver.session() as s:
    rows = list(s.run('''
        MATCH (n:Location {case_id: \$cid, source_type: \"cellebrite\"})
        WHERE n.latitude IS NOT NULL AND n.longitude IS NOT NULL
          AND coalesce(n.address, '') = ''
          AND coalesce(n.geocode_source, '') = ''
        RETURN n.key AS k, n.latitude AS lat, n.longitude AS lon
    ''', cid=case_id))
    print(f'Backfilling {len(rows)} locations…')
    for i, r in enumerate(rows):
        geo = reverse_geocode(r['lat'], r['lon'])
        if not geo or geo['geocode_source'] == 'none':
            continue
        s.run('''
            MATCH (n:Location {case_id: \$cid, key: \$k})
            SET n += \$props
        ''', cid=case_id, k=r['k'],
             props={k: v for k, v in geo.items() if v is not None})
        if (i + 1) % 100 == 0:
            print(f'  {i+1}/{len(rows)}')
print('Done.')
"
```

Replace `CASE_ID_HERE` with the actual case ID. Throttle (or batch +
sleep) if hammering Nominatim — a 50K-point case at 50ms/call is
~40 minutes wall time.

---

## Diagnostics + troubleshooting

### `primary_ready: false` after install

The geocoder module logged a warning at backend startup. Check it:

```bash
sudo journalctl -u owl-backend --since "5 minutes ago" | grep -i geocoder
```

Common causes:
- `Geocoder=nominatim configured but GEOCODER_URL is unset` — set the
  env var and restart.
- `Geocoder=geonames configured but reverse_geocoder is not installed` —
  run `pip install reverse-geocoder` into the backend venv (not the
  system Python).
- `Failed to construct Nominatim backend: …` — the URL doesn't reach
  Nominatim. `curl http://localhost:8080/status.php` from the deploy
  box; check the Docker container is running.

### Locations have no `address` after re-ingest

Two checks:

1. **Geocoder is wired:** `GET /api/cellebrite/geocoder/status` shows
   `primary_ready: true`.
2. **The ingestion ran with the env var set:** if the backend was
   restarted after the case finished ingesting, the env var change
   only affects the **next** ingestion, not retroactively. Re-ingest
   the case.

### Nominatim is up but slow

Default `GEOCODER_TIMEOUT_S=2.0`. On a large Nominatim import the
first lookup of a point sometimes takes longer (cold caches). If you
see ingestion warnings about timeouts:

- Bump `GEOCODER_TIMEOUT_S=5.0` and restart.
- Pre-warm by hitting `/reverse` with a few points before kicking off
  big ingestions.

### Cellebrite-provided addresses

Cellebrite XML sometimes carries its own `<PositionAddress>` block.
The writer respects that — those rows are tagged
`geocode_source: "cellebrite"` and the geocoder is **not** called.
The "via …" chip in the UI distinguishes Cellebrite-provided vs.
inferred addresses for audit purposes.

---

## Quick reference: env vars

| Var | Required for | Default | Notes |
|---|---|---|---|
| `GEOCODER` | All paths | unset | One of `nominatim` / `geonames` / unset |
| `GEOCODER_URL` | Nominatim only | unset | e.g. `http://localhost:8080` |
| `GEOCODER_FALLBACK` | Optional | unset | One of `nominatim` / `geonames` / unset |
| `GEOCODER_TIMEOUT_S` | Optional | `2.0` | Per-request HTTP timeout (seconds) |
| `GEOCODER_USER_AGENT` | Optional | `owl-cbm/1.0` | Sent to Nominatim's HTTP API |
| `GEOCODER_AUTH` | Optional | unset | `Bearer:xyz` style — for fronted Nominatim |

Env vars are read **once at backend import**. Every change requires
`sudo systemctl restart owl-backend`.

---

## After this is done

The team can use the new search operators (G5):

- `place:london` — substring match on geocoded address / place_name /
  country / admin levels. Items without geocode info are excluded.
- `near:51.5,-0.1,5km` — within radius of a centre point. Unit km|m,
  default km. Items without coordinates are excluded.

These work in:
- The **Locations tab** search bar
- The **Comms Center** search bar (filters comms-events that have
  geocoded `nearest_location_*` fields)
- The **Events Center** search bar
- Server-side via the `/api/cellebrite/events?place=…&near=…` query
  params — useful for LLM-driven workflows.

Once a case has been re-ingested with the geocoder on, `place:` and
`near:` filter the rail's per-row drill-in too.
