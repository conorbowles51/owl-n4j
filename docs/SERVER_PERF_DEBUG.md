# Server-side performance debugging — runbook for Claude on the deploy box

**Audience:** the Claude session running on the GCP `investigation-platform`
deploy box (or anyone debugging owl-backend perf there).

**When to use:** users report the platform "feeling slow", a request
hangs, the backend gets restarted by systemd, OOM events show up in
dmesg, or response times balloon on a specific case (especially
multi-phone Cellebrite cases).

**Posture:** measure first, change nothing. The Phase A–D Cellebrite
work (commits `33d7c76` … `d9b0e91`, see `git log --oneline -25`) is
all tab-scoped and only fires when a user opens the relevant
Cellebrite tab — it is **not** the cause of "case open is slow"
unless explicitly proven. The most recent fix `d9b0e91` removes the
eager case-wide timeline fetch, which was the previous culprit.

---

## Tier 0 — verify the deploy state (always run first)

```bash
cd <owl-n4j checkout>          # e.g. /home/conorbowles51/app_v2
git log --oneline -3
# Expect d9b0e91 or newer at HEAD if the timeline lazy-load fix is deployed.

sudo systemctl status owl-backend --no-pager
sudo systemctl status owl-frontend --no-pager 2>/dev/null || true
sudo systemctl status neo4j --no-pager 2>/dev/null \
  || docker ps --format '{{.Names}} {{.Status}}' | grep -i neo4j

free -h
df -h | head -5
uptime
```

Report back:
- HEAD commit
- Whether owl-backend / neo4j are `active (running)`
- Memory used vs. available
- Disk space (Cellebrite extractions can fill `/var` fast)
- Load average (a sustained `>1.0` per core means you're CPU-bound)

If owl-backend is **not** running, restart it and capture the journal:

```bash
sudo journalctl -u owl-backend --since "30 minutes ago" --no-pager | tail -200
sudo systemctl restart owl-backend
sleep 5
sudo systemctl status owl-backend --no-pager
```

Look in the captured journal for:
- `Killed` (likely OOM — confirm via `dmesg | tail -50 | grep -i kill`)
- Python tracebacks (uncaught exceptions in a worker)
- HTTP `5xx` responses
- `geocoder` warnings logged at startup

---

## Tier 1 — identify the slow request

### From the user's browser (cheapest signal)

Ask the user to:

1. Open Chrome devtools → **Network** tab
2. Trigger the slow flow
3. Sort by **Time** descending
4. Screenshot the top 5 requests + their `time` and `size` columns

That tells you which endpoint is slow without touching the server.

### From the server (when you don't have the user)

If uvicorn is logging request times (check the systemd unit / config),
just grep:

```bash
sudo journalctl -u owl-backend --since "10 minutes ago" --no-pager \
  | grep -E "POST|GET" \
  | awk '{print $NF, $0}' \
  | sort -rn | head -20
```

If it isn't, fall back to direct timing with `curl -w`:

```bash
TOK="<bearer token from a logged-in browser session>"
CASE="<case-id-of-interest>"

for path in \
  "/api/cases/$CASE" \
  "/api/cellebrite/reports?case_id=$CASE" \
  "/api/cellebrite/comms/envelope?case_id=$CASE" \
  "/api/cellebrite/events?case_id=$CASE&event_types=location&only_geolocated=true&limit=100" \
  "/api/cellebrite/locations/tiles?case_id=$CASE&zoom=6" \
  "/api/timeline/events?case_id=$CASE" ; do
  echo "=== $path ==="
  curl -s -o /tmp/body \
    -H "Authorization: Bearer $TOK" \
    -w "  http=%{http_code}  total=%{time_total}s  ttfb=%{time_starttransfer}s  size=%{size_download}\n" \
    "http://localhost:8000$path"
done
```

Report back the times. Anything > 1s on first call deserves investigation;
anything > 5s is a bug.

---

## Tier 2 — slow endpoint is identified, narrow to the layer

Three layers can be slow: **Python projection** (CPU), **Neo4j Cypher**
(query plan / index), **JSON serialise + transit** (size).

### 2a. Python — is the projection itself slow?

Inside the backend venv, time the service function directly (skips
HTTP / FastAPI overhead):

```bash
PYTHONPATH=backend /home/conorbowles51/app_v2/venv/bin/python <<'PY'
import time
from services.neo4j_service import Neo4jService
svc = Neo4jService()
case_id = "<case-id>"

t = time.perf_counter()
res = svc.get_cellebrite_events(case_id=case_id, event_types=["location"], limit=100)
print(f"events fetch: {time.perf_counter() - t:.2f}s  -> {len(res.get('events', []))} rows")

t = time.perf_counter()
env = svc.get_cellebrite_comms_envelope(case_id=case_id)
print(f"envelope:     {time.perf_counter() - t:.2f}s  -> total={env.get('total')}")

t = time.perf_counter()
tiles = svc.get_cellebrite_location_tiles(case_id=case_id, zoom=6)
print(f"tiles:        {time.perf_counter() - t:.2f}s  -> {len(tiles.get('tiles', []))} tiles")
PY
```

If the Python timings match the HTTP timings, the slowness is in the
service or below it. If Python is fast and HTTP is slow, the bottleneck
is FastAPI overhead, auth middleware, or response serialisation.

### 2b. Neo4j — `EXPLAIN` and `PROFILE` the suspect Cypher

Find the Cypher in `backend/services/neo4j_service.py` for the relevant
function (use `grep -n "def get_cellebrite_<name>"` to locate it). Copy
the Cypher body, replace `$param` placeholders with real values, prefix
with `PROFILE` or `EXPLAIN`, and run via cypher-shell:

```bash
docker exec -i $(docker ps -qf name=neo4j) cypher-shell -u neo4j -p <password> <<'CYPHER'
PROFILE
MATCH (n:Location {case_id: 'CASE-ID-HERE', source_type: 'cellebrite'})
WHERE n.latitude IS NOT NULL AND n.longitude IS NOT NULL
RETURN count(n) AS total;
CYPHER
```

Read the plan output:
- Look for `AllNodesScan` — that's a full table scan, expensive
- Look for `NodeIndexSeek` / `NodeByLabelScan` — index hits, cheap
- The `db hits` column is the actual work done; lower is better
- `EagerAggregation` on a big input set is a memory red flag

If the query is slow because of a missing index, check what we already
have:

```bash
docker exec -i $(docker ps -qf name=neo4j) cypher-shell -u neo4j -p <password> <<'CYPHER'
SHOW INDEXES;
CYPHER
```

The Cellebrite indexes shipped in commit `fbe8df0` cover
`(case_id, cellebrite_report_key)` for hot labels. If the slow query
filters on a property not covered, that's the gap. Don't add the index
yourself — surface the finding back to the local Claude session and
ship it as a planned commit so the indexes stay version-controlled.

### 2c. Response size — is it just a lot of JSON?

```bash
curl -s -o /tmp/body -H "Authorization: Bearer $TOK" \
  "http://localhost:8000/api/<endpoint>?<params>"
wc -c /tmp/body
python3 -c "import json,sys; d=json.load(open('/tmp/body')); print({k: (len(v) if isinstance(v,(list,dict)) else type(v).__name__) for k,v in d.items()})"
```

Anything past **2 MB** of JSON is worth flagging. If it's a list field
with many thousand items, that's a candidate for either pagination or
an envelope/aggregate variant (look at the existing
`/comms/envelope` + `/comms/between?cursor=…` pattern from commits
`477685b` + `c764f03` for how we've already handled this).

---

## Tier 3 — memory-pressure diagnostics

If you see `Killed` in the journal or the backend silently dies:

```bash
# Confirm OOM
dmesg | tail -100 | grep -E "Killed process|out of memory" | tail

# Per-process memory (high water marks)
ps aux --sort=-%mem | head -10

# Backend RSS over time (run this in a separate window for a minute
# while reproducing the slow flow)
PID=$(systemctl show owl-backend --property=MainPID --value)
while true; do
  echo "$(date +%T) $(ps -o rss= -p $PID | awk '{printf "%.1f MB", $1/1024}')"
  sleep 1
done
```

Memory shapes to watch for:
- Backend RSS climbing monotonically during a single request → that
  request is loading too much in memory. Likely candidate: a Cypher
  that pulls every event in the case into a Python list before
  filtering. Fix is to push the filter into Cypher.
- Sudden RSS jump on first geocode call → reverse_geocoder lazy-loads
  ~50 MB of city data on first use. That's expected once per process
  lifetime, not a bug.
- Steady RSS growth across many requests → real leak. Restart
  unblocks; finding the leak is a longer task.

---

## Tier 4 — Cellebrite-specific quick checks

For OPDMD28 (or any case with multiple phones / 50K+ events):

### Reconciliation report (does the data look sane?)

```bash
curl -s -H "Authorization: Bearer $TOK" \
  "http://localhost:8000/api/cellebrite/reports?case_id=$CASE" | jq '
    .reports[] | {
      device: .device_model,
      report_key,
      stats,
      reconciliation_summary: .reconciliation.summary
    }'
```

Look for `types_under > 0` — that means the parser dropped rows on
ingestion. Worth flagging back even if not the perf issue.

### Geocoder status

```bash
curl -s -H "Authorization: Bearer $TOK" \
  "http://localhost:8000/api/cellebrite/geocoder/status" | jq .
```

If `primary_ready: false` while the env vars say it should be
configured, check `journalctl -u owl-backend | grep -i geocoder` for
the startup warning.

### Per-phone event counts

```bash
docker exec -i $(docker ps -qf name=neo4j) cypher-shell -u neo4j -p <password> <<CYPHER
MATCH (r:PhoneReport {case_id: 'CASE-ID-HERE'})
OPTIONAL MATCH (n {case_id: 'CASE-ID-HERE', cellebrite_report_key: r.key})
WHERE n:Location OR n:Communication OR n:PhoneCall OR n:Email
RETURN r.name AS phone, labels(n)[0] AS label, count(n) AS n
ORDER BY n DESC;
CYPHER
```

A single phone with hundreds of thousands of one type is a hint that
ingestion didn't cap something it should have, or that the case
genuinely is that big and a fix needs server-side aggregation rather
than client filtering.

---

## Tier 5 — escalation rules

These signals warrant **stopping and reporting back**, not changing
anything:

1. **OOM kills more than once in a day** — the platform is mis-sized
   for the data; needs a coordinated decision on memory cap or
   architectural change.
2. **A `PROFILE` shows db-hits > 10M for a single query** — needs an
   index or a Cypher rewrite, version-controlled.
3. **A response is > 50 MB** — needs server-side aggregation or
   pagination, not just a faster network.
4. **Neo4j itself is unhealthy** (heap exhausted, page-cache evictions
   sustained) — needs neo4j.conf changes which should also be
   version-controlled.

Don't paper over these by restarting the service or bumping a memory
limit silently. Capture the evidence, push it into a comment / commit
message, and ship a real fix with someone reviewing.

---

## Quick reference: what the Phase A–D commits do (so you don't blame
the wrong thing)

| Commit | What | Triggered by |
|---|---|---|
| `33d7c76` | A1 — reconciliation report | New ingestion only |
| `56d9776` | A2 — date filter normalization | All Cellebrite date queries |
| `7079bb6` | A3 — search input sanitisation | Any Cellebrite tab search |
| `ab4fc5f` | A4 — persistent status bar | Any Cellebrite tab open |
| `bd348c2` | A5+A6 — geo accuracy/confidence + map state | New ingestion + Events tab open |
| `477685b` | B1 — comms envelope endpoint | Comms Center tab open |
| `c780946` | B5 — honest scrubber | Comms Center tab open |
| `6eaf073` | B3 — single-tx wrap | Comms Center between fetch |
| `c764f03` | B2 — cursor pagination | Comms Center between fetch |
| `071820a–ad3527a` | B6 — universal collapsible right-rail | Item click in any Cellebrite tab |
| `cad63fd` | C1 — Locations tab | Locations tab open |
| `b31af52` | C2 — tile aggregation endpoint | Locations tab open in tiles mode |
| `78a47eb` | C3 — tile-click rail | Tile click in Locations tab |
| `e8acbee` | D1 (G4) — pluggable reverse-geocoding | New Cellebrite ingestion only |
| `8550415` | D2 (G5) — place: + near: search operators | Search input |
| `d9b0e91` | App: lazy-load case-wide timeline | Replaces eager fetch on case open |

None of these run on case open by themselves (after `d9b0e91`).

If a perf issue is reproducibly tied to one of them, narrow with
Tier 2 and report back with the EXPLAIN/PROFILE output rather than
disabling the feature. The fixes have been measured cheap on
isolated test cases — when they're slow on a specific real case it's
usually a missing index or an unexpectedly large input, not the
endpoint logic.
