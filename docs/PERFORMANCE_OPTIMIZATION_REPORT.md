# OWL-N4J Performance Optimization Report

**Date:** 2026-03-15

This report evaluates performance optimizations for the OWL investigation console (frontend-v2). Each idea includes a feasibility assessment, estimated impact, and implementation approach.

---

## Table of Contents

1. [Lightweight Graph Loading (Neo4j Only)](#1-lightweight-graph-loading-neo4j-only)
2. [Semantic Zoom with Community Aggregation](#2-semantic-zoom-with-community-aggregation)
3. [Universal Pagination](#3-universal-pagination)
4. [Additional Ideas](#4-additional-ideas)
   - 4a. Virtual Scrolling
   - 4b. Web Worker for Force Simulation
   - 4c. LOD Rendering Tiers
   - 4d. Backend Response Compression
   - 4e. Incremental Graph Updates
   - 4f. Pre-computed Graph Layouts

---

## Current State Summary

| Metric | Current Behavior |
|--------|-----------------|
| **Graph loading** | `GET /api/graph` → `get_full_graph()` Cypher returns `properties(n)` on every node, including summary, verified_facts, ai_insights, notes, and all custom properties |
| **Estimated payload per node** | 1–15 KB depending on fact/insight count |
| **10,000-node case** | Estimated 10–150 MB payload, all loaded at once |
| **Pagination** | Table and Financial views have client-side pagination only; Timeline, Evidence, and Graph have none |
| **Graph rendering** | react-force-graph-2d renders all nodes in a single canvas with D3 force simulation. No LOD, no virtualization, no clustering |
| **Node details** | Already loaded on-demand via `useNodeDetails()` — but the same data also arrives in the initial graph payload |
| **Community detection** | Louvain algorithm already implemented at `/api/graph/communities`. Community IDs already stored on nodes |

---

## 1. Lightweight Graph Loading (Neo4j Only)

### The Problem

The current `get_full_graph()` method in `neo4j_service.py` uses this Cypher:

```cypher
MATCH (n)
WHERE n.case_id = $case_id
RETURN
  id(n) AS neo4j_id, n.id AS id, n.key AS key, n.name AS name,
  labels(n)[0] AS type, n.summary AS summary, n.notes AS notes,
  properties(n) AS properties
```

The `properties(n)` call dumps **every property** on every node — including `verified_facts` (JSON arrays of 10+ facts), `ai_insights` (JSON arrays), and any custom properties. For rendering the graph, the frontend only needs: `key`, `name`, `type`, `confidence`, `community_id`, and `mentioned`. Everything else is dead weight on initial load.

### The Solution: Selective Cypher Projection

**No Postgres needed.** Neo4j can return exactly the fields we need — we just need to stop using `properties(n)` and select specific fields instead. Everything stays in Neo4j; we just change what we ask for.

**New lightweight Cypher query:**

```cypher
MATCH (n)
WHERE n.case_id = $case_id
RETURN
  n.key AS key,
  n.name AS name,
  labels(n)[0] AS type,
  n.confidence AS confidence,
  n.community_id AS community_id,
  n.mentioned AS mentioned
```

When a user clicks a node, `useNodeDetails()` already calls `GET /api/graph/node/{key}` which runs a separate query that returns the full node with all properties and connections. **This on-demand loading path already exists and works.**

### Payload Impact

| Field | Size per node | 10,000 nodes |
|-------|--------------|--------------|
| key | ~20 bytes | 200 KB |
| name | ~30 bytes | 300 KB |
| type | ~15 bytes | 150 KB |
| confidence | ~4 bytes | 40 KB |
| community_id | ~4 bytes | 40 KB |
| mentioned | ~5 bytes | 50 KB |
| **Total** | **~78 bytes** | **~780 KB** |

**Reduction: 10–150 MB → ~1 MB (graph nodes). Edges add ~500 KB–1 MB. Total graph payload under 2 MB.**

### Implementation

This is a **backend-only change** with minimal frontend adjustment:

1. **Backend:** Add a new method `get_graph_structure()` to `neo4j_service.py` (or add a `fields=minimal` parameter to the existing endpoint) that uses the selective Cypher query above
2. **Backend:** Similarly trim the edge query — return only `source`, `target`, `type`, and `weight` (drop `properties(r)`)
3. **Frontend:** Remove `summary`, `notes`, `verified_facts`, `ai_insights` from the `toGraphData()` transform since they won't be in the response. The `GraphNode` type already marks these as optional
4. **Frontend:** Ensure the detail panel uses `useNodeDetails()` for all rich data (it already does)

### Why Not Postgres?

The previous version of this report suggested moving heavy text to Postgres. That approach:
- Introduces a second database to deploy, backup, and maintain
- Requires a data migration from Neo4j properties to Postgres rows
- Requires updating the ingestion pipeline to write to both stores
- Requires a new service layer for Postgres CRUD operations
- Provides the **same payload reduction** as simply not requesting those fields from Neo4j

The only scenario where Postgres would add value is if you need **full-text search across entity summaries** or **complex SQL aggregations** on entity metadata. Neo4j's full-text indexes (`db.index.fulltext.createNodeIndex`) handle basic text search, but Postgres would be better for advanced search features (faceted search, trigram matching, etc.). If that need arises later, consider it then.

### Complexity

**Low.** This is a few lines of Cypher changes and removing unused fields from the frontend transform. No new dependencies, no migrations, no architectural changes.

### Priority: **P0 — Do first**

---

## 2. Semantic Zoom with Community Aggregation

### The Problem

Loading all 10,000 nodes into a D3 force simulation is the core rendering bottleneck. The force simulation uses Barnes-Hut approximation (O(n log n) per tick, not O(n²)), but even with that optimization, 10,000 nodes with 20,000 edges at 60fps is heavy:

- **Force ticks:** ~10,000 nodes × log(10,000) × ~300 warmup ticks = ~120M force calculations
- **Canvas draws:** 10,000 circles + 20,000 lines + labels per frame at 60fps
- **Memory:** Position, velocity, force vectors per node = ~200 bytes × 10,000 = 2 MB simulation state

Simply capping at 500 nodes (the previous suggestion) works but loses the "full picture" — investigators can't see the shape of their entire case.

### The Solution: Semantic Zoom with Community Clusters

Instead of hiding nodes, **aggregate them into community super-nodes** that expand as the user zooms in. This is how mapping applications work — you see country outlines until you zoom in to see cities, then streets.

**How it works:**

1. **Zoomed out (default view):** Each Louvain community becomes a single "super-node." A case with 10,000 nodes across 25 communities renders as ~25 super-nodes + cross-community edges. The force simulation runs on 25 nodes — instant.

2. **Zoom into a region:** When the user zooms past a threshold, communities in the viewport expand into their individual nodes. A community of 200 nodes expands in-place. The force simulation now handles ~200 individual nodes + the remaining ~24 collapsed super-nodes = ~224 nodes. Still fast.

3. **Full zoom:** In the deepest zoom level within a region, full node detail with labels, glows, and selection rings. This is the current rendering behavior, but only for the ~50–200 nodes in the viewport.

**Why this is better than a hard cap:**

| Approach | Visible nodes | Full graph visible? | Exploration model |
|----------|--------------|--------------------|--------------------|
| Top-500 cap | 500 | No — 9,500 hidden | Click to expand neighbors |
| Semantic zoom | All (aggregated) | Yes — all communities visible | Zoom to expand naturally |

The investigator always sees the full graph structure. High-degree hub communities are visually larger. Cross-community relationships are preserved. But the simulation never handles more than a few hundred individual nodes at once.

### Implementation Approach

#### Backend: Community-Aggregated Graph Endpoint

Add a `GET /api/graph/clustered` endpoint (or a `?clustered=true` parameter) that returns two levels:

```json
{
  "communities": [
    {
      "community_id": 0,
      "node_count": 342,
      "top_nodes": ["node_key_1", "node_key_2", "node_key_3"],
      "label": "Financial Network",
      "types": {"person": 120, "organization": 89, "account": 133},
      "avg_confidence": 0.72
    }
  ],
  "community_edges": [
    { "source": 0, "target": 3, "count": 47, "types": ["TRANSACTED", "OWNS"] }
  ],
  "nodes": [
    { "key": "...", "name": "...", "type": "...", "community_id": 0, "confidence": 0.85, "mentioned": true }
  ],
  "edges": [
    { "source": "...", "target": "...", "type": "...", "weight": 1 }
  ]
}
```

The `communities` and `community_edges` arrays power the zoomed-out view. The full `nodes` and `edges` arrays (with lightweight fields per Section 1) are included so the frontend can expand communities client-side without additional API calls.

**Cypher for community aggregation:**

```cypher
// Community summaries
MATCH (n) WHERE n.case_id = $case_id AND n.community_id IS NOT NULL
WITH n.community_id AS cid, collect(n) AS members
RETURN cid AS community_id,
       size(members) AS node_count,
       [m IN members | labels(m)[0]] AS types,
       avg([m IN members | m.confidence]) AS avg_confidence,
       [m IN members | m.key][..3] AS top_nodes

// Cross-community edges
MATCH (a)-[r]->(b)
WHERE a.case_id = $case_id AND b.case_id = $case_id
  AND a.community_id <> b.community_id
WITH a.community_id AS src, b.community_id AS tgt,
     count(r) AS cnt, collect(DISTINCT type(r)) AS types
RETURN src AS source, tgt AS target, cnt AS count, types
```

#### Frontend: Two-Layer Graph Rendering

**Layer 1 — Clustered view (default):**
- Render community super-nodes sized by `node_count` (e.g., radius = sqrt(node_count) * 2)
- Color by dominant entity type or use a distinct cluster palette
- Label with community name or top node names
- Edges between communities sized by cross-community relationship count
- Force simulation runs on ~10–50 super-nodes — effectively instant

**Layer 2 — Expanded communities:**
- Track which communities are "expanded" in the graph store
- When the user zooms in past a threshold (e.g., `globalScale > 1.5`) or double-clicks a community, expand it
- Replace the super-node with individual nodes, positioned around the super-node's coordinates
- Run a local force simulation only on the expanded community's nodes (constrained to a bounding box)
- Keep other communities collapsed

**Key implementation details:**
- The `graphStore` gets a new `expandedCommunities: Set<number>` state field
- `paintNode` checks if a node's community is expanded → render individual node or contribute to super-node
- Use `d3.forceSimulation` with a custom `forceCluster` to keep expanded nodes near their community center
- The existing `useGraphData` hook loads the clustered endpoint once; expansions are purely client-side since all nodes are already in memory (they're lightweight per Section 1)

#### Zoom-Based Auto-Expansion

Rather than requiring clicks, communities can auto-expand based on viewport:

```typescript
// In GraphCanvas onZoom handler
const handleZoom = useCallback(({ k, x, y }) => {
  if (k > EXPAND_THRESHOLD) {
    // Find communities whose super-node center is within the viewport
    const viewportCommunities = communities.filter(c =>
      isInViewport(c.x, c.y, canvasWidth / k, canvasHeight / k, x, y)
    );
    // Expand those communities, collapse others
    graphStore.setExpandedCommunities(new Set(viewportCommunities.map(c => c.id)));
  } else {
    graphStore.setExpandedCommunities(new Set());
  }
}, [communities]);
```

### Fallback: Top-N Loading

For cases where community detection hasn't been run or produces poor results, fall back to the simpler top-N approach:

- Load the top 500 nodes by degree centrality (fast single Cypher query)
- Show "load more" or expand-on-demand using existing `expandNodes` endpoint
- This is the safety net, not the primary strategy

### Complexity

**Medium-High.** The backend community aggregation is straightforward (Cypher queries above). The frontend two-layer rendering is the main effort — it requires changes to:

- `GraphCanvas.tsx`: Super-node rendering, zoom-based expansion
- `graph.store.ts`: `expandedCommunities` state
- `use-graph-data.ts`: Call clustered endpoint, manage two-layer data
- `paintNode`: Conditional rendering based on expansion state

Estimated effort: 3–5 days for a working implementation, plus 2–3 days for polish (animations, edge bundling between clusters, expand/collapse transitions).

### Priority: **P1 — Do after lightweight loading**

---

## 3. Universal Pagination

### The Problem

Even where pagination UI exists (Table, Financial views), it's **client-side only** — the backend sends the entire dataset and the frontend slices it in memory. For non-graph views with large datasets, this means unnecessary network transfer and memory allocation.

### Current Pagination Status

| View | Frontend Pagination | Backend Pagination |
|------|-------------------|-------------------|
| Table View | Client-side (25/50/100/250/All) | None |
| Financial View | Client-side (25/50/100/250/All) | None |
| Timeline View | None | None |
| Evidence List | None | None |
| Graph View | None (addressed by Sections 1 & 2) | None |
| System Logs | None (renders all) | Yes (limit/offset) |

### Solution

Add `SKIP`/`LIMIT` to backend Cypher and SQL queries, pass `limit`/`offset` parameters from the frontend.

**Priority order:**
1. **Timeline** — can have thousands of events. Server-side pagination with date-range windowing. Consider `useInfiniteQuery` for scroll-based loading.
2. **Financial** — thousands of transactions. The pagination UI component already exists.
3. **Table View** — loads same data as graph view. With lightweight loading (Section 1), this is less critical but still good practice.
4. **Evidence** — usually tens to low hundreds. Lowest priority.

**Estimated impact for 10,000-event timeline:** Loading 50 events instead of 10,000 = **200x reduction** in initial payload.

### Complexity

**Medium.** Well-understood pattern. The `TablePagination` component already exists. Backend changes are adding `SKIP`/`LIMIT` to queries.

### Priority: **P1 — Do alongside graph optimizations**

---

## 4. Additional Ideas

### 4a. Virtual Scrolling for List Views

**Problem:** Timeline, Evidence, and Table views render all items in the DOM even if only 20 are visible on screen.

**Solution:** Use `@tanstack/react-virtual` (already in the TanStack ecosystem) to only render DOM elements for visible items.

**Impact:** Medium. DOM node count drops from thousands to ~30–50 regardless of dataset size. Most impactful for Timeline view.

**Complexity:** Low–Medium.

### 4b. Web Worker for Force Simulation

**Problem:** D3 force simulation runs on the main thread, blocking UI interactions during layout computation.

**Solution:** Offload force calculations to a Web Worker. `react-force-graph` supports worker-based computation, or use `ngraph.forcelayout` which is designed for workers.

**Impact:** Medium. UI stays responsive during initial layout. Does NOT reduce total computation time — just moves it off the main thread. With semantic zoom (Section 2), the node count per simulation is already low enough that this becomes less critical.

**Complexity:** Medium.

### 4c. LOD Rendering Tiers

**Problem:** At high zoom levels, all nodes render with full detail (labels, glow effects, selection rings). At zoomed-out views, most of this detail is wasted.

**Solution:** Implement LOD tiers in `paintNode`:
- **`globalScale < 0.3`:** Simple dots, no labels, no glow effects
- **`globalScale 0.3–1.0`:** Labels only for high-degree nodes or selected nodes
- **`globalScale > 1.0`:** Full detail (current behavior)

The codebase already has `globalScale`-aware font sizing — this extends that pattern.

**Impact:** Low–Medium. Reduces per-frame canvas draw calls. Most valuable when combined with semantic zoom where you may have ~200 expanded nodes in view.

**Complexity:** Low. Changes only in `paintNode` and `paintLink` callbacks.

### 4d. Backend Response Compression

**Problem:** Large JSON payloads may be transferred without optimal compression.

**Solution:** Ensure gzip/brotli compression is enabled on the FastAPI server (via `GZipMiddleware` or nginx config). Brotli typically achieves 70–80% compression on JSON.

**Impact:** Medium for current payloads. After lightweight loading (Section 1), payloads are already small (~2 MB) so compression has diminishing returns. Still worth enabling as a baseline.

**Complexity:** Very Low. Single middleware addition.

**Action:** Check if this is already configured. If not, add it.

### 4e. Incremental Graph Updates via WebSocket

**Problem:** When new evidence is processed, the entire graph must be re-fetched.

**Solution:** Push incremental node/edge additions via WebSocket or SSE.

**Impact:** Low for initial load. Improves UX during active investigation sessions.

**Complexity:** High. Requires WebSocket infrastructure, incremental update protocol, conflict resolution.

**Priority:** Defer until other optimizations are in place.

### 4f. Pre-computed Graph Layouts

**Problem:** Force simulation runs every time the graph is loaded, even if the graph data hasn't changed.

**Solution:** Cache computed node positions (x, y coordinates) after the first simulation run. On subsequent loads, skip the simulation and render nodes at their cached positions. Positions can be stored:
- **Client-side:** In IndexedDB or localStorage, keyed by case_id + graph hash
- **Server-side:** As properties on Neo4j nodes (`n.layout_x`, `n.layout_y`), updated when graph structure changes

**Impact:** Medium. Eliminates the 1–3 second warmup period on repeat visits. The simulation only runs when the graph structure changes (new nodes/edges added).

**Complexity:** Low–Medium. Client-side caching is straightforward. Server-side requires a layout computation step after ingestion.

---

## Priority Matrix

| # | Optimization | Impact | Complexity | Priority |
|---|-------------|--------|-----------|----------|
| 1 | Lightweight Graph Loading (Neo4j only) | Very High | Low | **P0 — Do first** |
| 4d | Response Compression | Medium | Very Low | **P0 — Do first** |
| 2 | Semantic Zoom + Community Aggregation | Very High | Medium-High | **P1 — Do second** |
| 3 | Universal Pagination | High | Medium | **P1 — Do second** |
| 4c | LOD Rendering Tiers | Medium | Low | **P2 — Quick follow-up** |
| 4a | Virtual Scrolling | Medium | Low–Medium | **P2 — Quick follow-up** |
| 4f | Pre-computed Layouts | Medium | Low–Medium | **P2 — Quick follow-up** |
| 4b | Web Worker for Force Sim | Medium | Medium | **P3 — Nice to have** |
| 4e | Incremental WebSocket Updates | Low | High | **P4 — Future** |

---

## Suggested Implementation Order

### Phase 1: Quick Wins (1–2 days)
- **Section 1:** Modify `get_full_graph()` Cypher to return only `key`, `name`, `type`, `confidence`, `community_id`, `mentioned`. Drop `properties(n)`, `summary`, `notes`. Similarly trim edge queries to drop `properties(r)`.
- **4d:** Verify/enable gzip or brotli compression on API responses.

### Phase 2: Semantic Zoom (3–5 days)
- **Section 2:** Add community aggregation endpoint. Implement two-layer rendering in `GraphCanvas.tsx` — super-nodes for collapsed communities, individual nodes for expanded ones. Add zoom-based auto-expansion.
- **Fallback:** Implement top-N by degree as fallback for cases without community detection.

### Phase 3: List View Performance (2–3 days)
- **Section 3:** Add server-side pagination to Timeline and Financial endpoints.
- **4a:** Add virtual scrolling to Timeline and Evidence views.
- **4c:** Add LOD tiers to `paintNode`/`paintLink`.

### Phase 4: Polish
- **4f:** Cache layout positions client-side in IndexedDB for instant re-renders.
- **4b:** Web Worker offloading if force simulation jank persists after node count reduction.
- **4e:** WebSocket updates for real-time collaboration scenarios.
