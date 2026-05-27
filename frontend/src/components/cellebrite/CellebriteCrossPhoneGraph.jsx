import React, { useState, useEffect, useCallback, useRef, useMemo, useLayoutEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import {
  Loader2, ZoomIn, ZoomOut, Maximize2,
  Phone, MessageSquare, Mail, MapPin, Wifi, Radio, Users as UsersIcon, X,
  Globe, Search as SearchIcon, Bookmark, Key, ShieldCheck, DollarSign,
  Bluetooth, Filter as FilterIcon, ChevronRight, Tag, Clock,
  FolderTree, UserCheck, Move, MousePointerSquareDashed,
} from 'lucide-react';
import { cellebriteAPI } from '../../services/api';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import { usePerspective } from '../../context/PerspectiveContext';
import PhoneIdentityChip from './shared/PhoneIdentityChip';
import CellebriteSearchInput from './shared/CellebriteSearchInput';
import { requestCellebriteTabSwitch, setCommsHandoff } from '../../utils/commsHandoff';
import { useCellebriteSelection } from './shared/CellebriteSelectionContext';

/**
 * Convert a `#rrggbb` hex string to `rgba()` with the supplied alpha.
 * Used by linkColor so the edge-type colours can sit at <1 opacity
 * without doubling the GRAPH_EVENT_TYPES table. Tolerates short hex
 * (`#abc`) and bypasses unknown formats (returns the input as-is so
 * named colours / rgb() values still work).
 */
function withAlpha(hex, alpha) {
  if (typeof hex !== 'string' || !hex.startsWith('#')) return hex;
  let h = hex.slice(1);
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  if (h.length !== 6) return hex;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  if ([r, g, b].some((v) => Number.isNaN(v))) return hex;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Tokenise the graph search input. Same quoted-phrase support as the
 * shared parseQuery (so "Sender Lemus" stays one token) but no
 * operator handling — graph nodes don't have from/to/app/etc fields
 * that map cleanly. Free-text-only is honest to what the graph
 * actually carries.
 */
function tokeniseGraphSearch(input) {
  const tokens = [];
  let buf = '';
  let inQuotes = false;
  for (let i = 0; i < input.length; i++) {
    const ch = input[i];
    if (ch === '"') { inQuotes = !inQuotes; continue; }
    if (!inQuotes && /\s/.test(ch)) {
      if (buf) tokens.push(buf.toLowerCase());
      buf = '';
      continue;
    }
    buf += ch;
  }
  if (buf) tokens.push(buf.toLowerCase());
  return tokens.filter(Boolean);
}

// Available edge types — chips that toggle on/off in the legend strip.
// Comms types default ON (the legacy "shared contacts" view); web /
// identity / financial / pairing types are OFF by default because
// they introduce dense edge sets that overwhelm the comms picture on
// first look. Persisted per case in localStorage.
//
// Each entry maps 1:1 onto a backend EDGE_PATTERNS key.
// Each entry corresponds 1:1 to a backend EDGE_PATTERNS key. Toggles
// just show or hide nodes of that type on the canvas — they don't do
// any clever cross-phone matching. Connectivity between phones is a
// natural side effect when a resource (e.g. WiFi SSID, Account) is
// owned by more than one phone.
//
// Comms toggles (call/message/email) light up direct Person↔Person
// edges. Resource toggles add small Resource nodes (diamonds) that
// each phone connects to via a Phone→Resource edge.
//
// Default state: only calls + messages on. The user explicitly asked
// to see "where possible the whole graph but by default only have
// messages and calls visible. The rest can be toggled on or off."
//
// Each toggle is a true add/remove: deselecting a type causes the
// backend to omit Persons / Resources whose only edges were of that
// type, so the canvas stays meaningful at every toggle state.
const GRAPH_EVENT_TYPES = [
  // Defaults are intentionally light. The user asked for "mostly
  // deselected so the graph doesn't start too chaotic" + "all the
  // phone data" — every Person is now eligible (sanity-cap raised
  // to 2,000 in the backend), so leaving Messages default-on would
  // pull thousands of nodes in on first load. Calls alone gives a
  // legible comms baseline the user can build on by toggling.
  { key: 'call',       label: 'Calls',       icon: Phone,         color: '#10b981', defaultOn: true,  group: 'comms' },
  { key: 'message',    label: 'Messages',    icon: MessageSquare, color: '#2563eb', defaultOn: false, group: 'comms' },
  { key: 'email',      label: 'Emails',      icon: Mail,          color: '#f59e0b', defaultOn: false, group: 'comms' },
  // Movement / proximity
  { key: 'location',   label: 'Locations',   icon: MapPin,        color: '#06b6d4', defaultOn: false, group: 'movement' },
  { key: 'wifi',       label: 'WiFi',        icon: Wifi,          color: '#22c55e', defaultOn: false, group: 'movement' },
  { key: 'cell_tower', label: 'Cell tower',  icon: Radio,         color: '#8b5cf6', defaultOn: false, group: 'movement' },
  { key: 'meeting',    label: 'Meetings',    icon: UsersIcon,     color: '#f97316', defaultOn: false, group: 'movement' },
  // Web activity
  { key: 'visit',      label: 'Web domains', icon: Globe,         color: '#a855f7', defaultOn: false, group: 'web' },
  { key: 'search',     label: 'Searches',    icon: SearchIcon,    color: '#ec4899', defaultOn: false, group: 'web' },
  { key: 'bookmark',   label: 'Bookmarks',   icon: Bookmark,      color: '#d946ef', defaultOn: false, group: 'web' },
  // Identity
  { key: 'account',    label: 'Accounts',    icon: ShieldCheck,   color: '#0ea5e9', defaultOn: false, group: 'identity' },
  { key: 'credential', label: 'Credentials', icon: Key,           color: '#eab308', defaultOn: false, group: 'identity' },
  // Other
  { key: 'financial',  label: 'Financial',   icon: DollarSign,    color: '#16a34a', defaultOn: false, group: 'other' },
  { key: 'pairing',    label: 'Pairings',    icon: Bluetooth,     color: '#6366f1', defaultOn: false, group: 'other' },
];

const NODE_COLORS = {
  PhoneReport: '#059669',  // emerald-600 (fallback when no phone identity)
  Person: '#3b82f6',       // blue-500
  PersonShared: '#f59e0b', // amber-500
};

/**
 * Cross-phone graph visualization showing shared contacts across devices.
 */
export default function CellebriteCrossPhoneGraph({ caseId }) {
  const phoneCtx = usePhoneReports();
  const perspective = usePerspective();
  const { selectEntity } = useCellebriteSelection();

  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [hoveredNode, setHoveredNode] = useState(null);
  // Per-case localStorage so the user's preferred event-type toggle
  // state persists across visits. Keyed off case so different cases
  // don't bleed settings.
  // localStorage key bumped to v3. v2 stored stale chip keys that
  // no longer exist in EDGE_PATTERNS (e.g. 'wifi_ssid' was folded
  // into 'wifi') — those were still being sent to the backend on
  // each refetch and silently ignored. v3 reseeds from defaultOn
  // and filters out any key that isn't in the current registry on
  // load, so previously-cached state can never leak unknown keys.
  const eventTypesKey = `cb.graph.eventTypes.v4.${caseId || 'unknown'}`;
  const knownKeys = useMemo(
    () => new Set(GRAPH_EVENT_TYPES.map((t) => t.key)),
    [],
  );
  const [activeEventTypes, setActiveEventTypes] = useState(() => {
    if (typeof window === 'undefined') {
      return new Set(GRAPH_EVENT_TYPES.filter(t => t.defaultOn).map(t => t.key));
    }
    try {
      const raw = window.localStorage.getItem(eventTypesKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          // Filter out any key that's no longer in EDGE_PATTERNS —
          // 'wifi_ssid' etc. would otherwise survive a code change
          // that removed them and still get sent to the backend.
          const known = new Set(GRAPH_EVENT_TYPES.map((t) => t.key));
          const sanitised = parsed.filter((k) => known.has(k));
          if (sanitised.length > 0) return new Set(sanitised);
        }
      }
    } catch { /* ignore */ }
    return new Set(GRAPH_EVENT_TYPES.filter(t => t.defaultOn).map(t => t.key));
  });
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(eventTypesKey, JSON.stringify([...activeEventTypes]));
    } catch { /* full / disabled */ }
  }, [activeEventTypes, eventTypesKey]);

  // Camera preservation + position carry-over across refetches.
  //
  // Every event-type toggle now triggers a backend refetch so the new
  // node set actually changes (Persons whose only edges were the
  // deselected type disappear, resources of newly-selected types
  // appear). Without these refs we'd lose the user's pan/zoom and the
  // unchanged nodes would teleport to fresh random positions.
  //
  // Strategy:
  //   - cameraSnapshotRef:   captured just BEFORE a refetch, restored
  //                          via centerAt+zoom inside onEngineStop
  //                          once the new simulation settles.
  //   - lastNodePosRef:      maintained from whatever's currently on
  //                          screen. Used to seed new nodes with the
  //                          previous node's x/y/vx/vy when their ids
  //                          match — so anything that's still on the
  //                          canvas stays put.
  const cameraSnapshotRef = useRef(null);
  const lastNodePosRef = useRef(new Map());
  // Continuously maintain the position cache so the next refetch
  // always has the freshest layout to seed from.
  useEffect(() => {
    const m = lastNodePosRef.current;
    for (const n of graphData.nodes) {
      if (n.id == null) continue;
      if (Number.isFinite(n.x) && Number.isFinite(n.y)) {
        m.set(n.id, { x: n.x, y: n.y, vx: n.vx, vy: n.vy });
      }
    }
  });

  // Pre-paint camera clamp.
  //
  // The library auto-fits the moment a new graphData reference lands.
  // onEngineTick + onEngineStop both run AFTER the first paint —
  // which means the user sees one frame of the lib's auto-fit before
  // we yank the camera back. That single frame is the "snap to
  // neutral" the user reported.
  //
  // Fix: useLayoutEffect runs synchronously after React commits but
  // BEFORE the browser paints. We slam the camera back here so the
  // very first painted frame already has the user's view restored.
  // Pair with onEngineTick (every-frame clamp during warm-up) and
  // onEngineStop (final release) for a zero-flicker handover.
  useLayoutEffect(() => {
    const snap = cameraSnapshotRef.current;
    if (!snap || !fgRef.current) return;
    try {
      fgRef.current.centerAt(snap.x, snap.y, 0);
      fgRef.current.zoom(snap.z, 0);
    } catch { /* ref not ready */ }
  }, [graphData]);
  // Depth toggle — 1 (anchors + direct contacts) is the safer default;
  // 2 hops off-anchor and is best for "find connections-of-connections"
  // exploration. Only meaningful when a perspective is active.
  const [depth, setDepth] = useState(1);

  const fgRef = useRef();
  const containerRef = useRef();

  // Total Persons in the case (regardless of any filter or cap).
  // Surfaced by the backend so the UI can show "X of N people in
  // case" and offer search to reach those outside the rendered set.
  const [totalPersons, setTotalPersons] = useState(0);
  // True ONLY when the backend hit a hard 2,000-node cap. Drives
  // the "capped" badge; the gap between rendered and total Persons
  // is otherwise just the active-edge filter, which is honest
  // behaviour and shouldn't surface a warning.
  const [hitCap, setHitCap] = useState(false);

  // Per-edge-type edge counts (from the backend). The chip strip
  // renders these as small badges so the user sees "Visits 0" and
  // understands an empty toggle is "no data" rather than "broken".
  // Keys match GRAPH_EVENT_TYPES.key.
  const [edgeCountsByType, setEdgeCountsByType] = useState({});

  // Search vs Filter mode. Filter = narrow what's drawn (matches +
  // their neighbours). Search = highlight matches and surface them
  // in a results panel; the underlying graph is not narrowed. Search
  // mode also hits the backend so the user can find Persons that
  // aren't in the rendered subset at all.
  const [searchMode, setSearchMode] = useState('filter'); // 'filter' | 'search'

  // Master "labels all on" toggle.
  //   true  (default) → every node renders a compact label;
  //                     hovered node enlarges it; search matches
  //                     get cyan colour + slight bump.
  //   false           → labels suppressed except hover / search
  //                     match / Phones. For dense graphs.
  const [labelsAllOn, setLabelsAllOn] = useState(true);

  // Selection rubber-band state.
  // Trigger: right-click + drag anywhere on the canvas. Mouse button
  // 2 starts the box; we suppress the browser context-menu so the
  // gesture feels natural. Left-click drag still moves single nodes
  // OR translates the whole multi-selection (see onNodeDrag below).
  const [selectionBox, setSelectionBox] = useState(null);
  const selectionBoxStartRef = useRef(null);
  // Persistent multi-selection (node ids). Survives canvas redraws
  // so the user can pivot on the selection from the perspective bar.
  const [multiSelection, setMultiSelection] = useState(new Set());

  // Group-drag state.
  // When the user starts dragging a node that's part of the
  // multi-selection, every selected node moves by the same delta.
  // We snapshot starting positions for every selected node so we
  // can compute the delta on each onNodeDrag frame.
  const groupDragRef = useRef(null);

  // Pending centre-and-fan focus id. When the user clicks a Person
  // search result we both rebuild the graph (via setPerspective)
  // AND want to centre+fan the result. The rebuild is async; this
  // ref stores the focus id until the next graphData arrival, at
  // which point the effect below runs the layout.
  const pendingFanRef = useRef(null);

  // Same pattern but for Resources. The resource graph id is
  // computed by the backend's safe_bucket sanitisation which we
  // don't reproduce client-side; instead we store the matchable
  // (resource_type, bucket) tuple and resolve it once graphData
  // lands.
  const pendingResourceFanRef = useRef(null);

  // Pivot the active perspective (or the multi-selection if it's
  // non-empty) into another Cellebrite tab. Each target tab has a
  // slightly different intake contract:
  //
  //   - 'comms'           — Comms Center reads _filter_intent: 'comms'
  //                          from the selection rail and pre-fills the
  //                          participants chip with the person keys.
  //   - 'communications'  — Same person-keys handoff; Communications
  //                          uses the perspective context directly so
  //                          we just leave the perspective active.
  //   - 'timeline' / 'events' / 'locations' / 'files' / 'unified' —
  //                          Backed by the perspective context which
  //                          they read on mount. We just switch tabs;
  //                          they pick the lens up from there.
  //
  // Selection sourcing:
  //   - If the user has multi-selected nodes, derive person keys from
  //     those (Person ids → strip 'person-' prefix) and use as the
  //     pivot lens.
  //   - Otherwise fall back to the active perspective.
  const pivotTo = useCallback((tabId) => {
    // Resolve the lens — multi-selection wins if non-empty
    let personKeys = null;
    let label = null;
    if (multiSelection.size > 0) {
      const ids = [...multiSelection];
      const persons = ids
        .map((id) => graphData.nodes.find((n) => n.id === id))
        .filter((n) => n && n.type !== 'Resource' && n.type !== 'PhoneReport');
      personKeys = persons
        .map((n) => (n.id || '').replace(/^person-/, ''))
        .filter(Boolean);
      label = persons.length === 1
        ? (persons[0].name || personKeys[0])
        : `${persons.length} people`;
      // Replace the perspective with this multi-selection so other
      // tabs read a coherent lens too.
      if (perspective && personKeys.length > 0) {
        perspective.setPerspective(personKeys, label, 'graph.multi-select-pivot');
      }
    } else if (perspective?.hasPerspective) {
      personKeys = [...(perspective.activeKeys || [])];
      label = perspective.active?.label;
    }

    // Always publish a _filter_intent so the Comms Center can pre-fill
    // its participants chip from the rail event, even if it hasn't
    // read the perspective context yet.
    if (personKeys && personKeys.length > 0) {
      selectEntity({
        type: 'name-action',
        id: `graph-pivot-${tabId}-${Date.now()}`,
        caseId,
        payload: { _filter_intent: 'comms', person_keys: personKeys },
        source: 'graph.pivot',
      });
    }

    // Some tabs also want the canonical phone-keys handoff. Pass
    // every report_key the lens touches; downstream filters narrow
    // the device set when the user is anchored on a single phone.
    const reportKeys = phoneCtx?.reports?.map((r) => r.report_key)
      .filter(Boolean) || [];
    if (tabId === 'comms' || tabId === 'communications') {
      setCommsHandoff({
        caseId,
        startTs: null,
        endTs: null,
        reportKeys,
        source: 'graph.pivot',
      });
    }

    requestCellebriteTabSwitch(tabId);
  }, [caseId, graphData.nodes, multiSelection, perspective, phoneCtx, selectEntity]);

  // centreAndFan: pin a node at origin, arrange its neighbours in
  // a circle around it, zoom to fit. Implements the user's "move
  // that node out of the cluster and circle the cluster around it"
  // request. Pins released ~1.2s later so the user can continue
  // to drag if they want.
  const centreAndFan = useCallback((focusId, nodes, links) => {
    if (!fgRef.current) return;
    const focus = nodes.find((n) => n.id === focusId);
    if (!focus) return;
    const neighbourIds = new Set();
    for (const l of links) {
      const s = typeof l.source === 'object' ? l.source.id : l.source;
      const t = typeof l.target === 'object' ? l.target.id : l.target;
      if (s === focusId) neighbourIds.add(t);
      else if (t === focusId) neighbourIds.add(s);
    }
    focus.fx = 0; focus.fy = 0; focus.x = 0; focus.y = 0;
    const ring = [...neighbourIds]
      .map((id) => nodes.find((n) => n.id === id))
      .filter(Boolean);
    const R = Math.max(140, 22 * Math.sqrt(ring.length));
    ring.forEach((n, i) => {
      const theta = (2 * Math.PI * i) / Math.max(1, ring.length);
      n.fx = Math.cos(theta) * R;
      n.fy = Math.sin(theta) * R;
      n.x = n.fx;
      n.y = n.fy;
    });
    try { fgRef.current.d3ReheatSimulation?.(); } catch { /* ignore */ }
    fgRef.current.centerAt(0, 0, 600);
    fgRef.current.zoom(Math.min(2.2, 700 / (R * 2 + 120)), 600);
    setTimeout(() => {
      if (focus) { delete focus.fx; delete focus.fy; }
      ring.forEach((n) => { delete n.fx; delete n.fy; });
    }, 1200);
  }, []);

  // Run the pending centre-and-fan once the rebuilt graphData
  // contains the target focus id. Person path uses an exact id;
  // resource path uses (resource_type, bucket) since the backend
  // generates safe_bucket sanitisation we don't reproduce here.
  useEffect(() => {
    const focusId = pendingFanRef.current;
    if (focusId && graphData.nodes.some((n) => n.id === focusId)) {
      setMultiSelection(new Set([focusId]));
      centreAndFan(focusId, graphData.nodes, graphData.links);
      pendingFanRef.current = null;
    }
    const pr = pendingResourceFanRef.current;
    if (pr) {
      const match = graphData.nodes.find((n) =>
        n.type === 'Resource'
        && n.resource_type === pr.resource_type
        && (n.bucket === pr.bucket || n.name === pr.bucket));
      if (match) {
        setMultiSelection(new Set([match.id]));
        centreAndFan(match.id, graphData.nodes, graphData.links);
        pendingResourceFanRef.current = null;
      }
    }
  }, [graphData, centreAndFan]);
  const [searchResults, setSearchResults] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);

  // Active perspective anchors (or null = full case)
  const personKeys = useMemo(() => {
    if (!perspective?.hasPerspective) return null;
    return [...perspective.activeKeys];
  }, [perspective?.hasPerspective, perspective?.activeKeys]);

  // ---- Fetch policy --------------------------------------------------
  // Refetch on any change that affects which nodes belong on the
  // canvas: perspective anchors, depth, AND the active event-type set.
  // The backend produces a graph containing ONLY Persons / Resources
  // reachable via active edges, so toggling a chip both adds and
  // removes nodes (not just edges).
  //
  // Camera + node positions are preserved across the refetch — we
  // snapshot centerAt+zoom just BEFORE the call and restore them in
  // onEngineStop once the new simulation settles, and we copy x/y/
  // vx/vy from matching old nodes onto the new ones so unchanged
  // nodes don't teleport.
  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;

    // Snapshot the current camera BEFORE issuing the fetch so the
    // post-fetch onEngineStop has something to restore. Initial load
    // skips the snapshot (graph hasn't rendered yet) and the library's
    // default first-render fit applies normally.
    if (fgRef.current && graphData.nodes.length > 0) {
      try {
        const centre = fgRef.current.centerAt();
        const z = fgRef.current.zoom();
        if (centre && Number.isFinite(centre.x) && Number.isFinite(centre.y)) {
          cameraSnapshotRef.current = { x: centre.x, y: centre.y, z };
        }
      } catch {
        cameraSnapshotRef.current = null;
      }
    }

    setLoading(true);
    cellebriteAPI.getCrossPhoneGraph(caseId, {
      personKeys: personKeys || undefined,
      // Send the user's active set so the backend includes/excludes
      // the matching Persons + Resources. Empty set = no event types.
      eventTypes: [...activeEventTypes],
      depth,
    }).then(data => {
      if (cancelled) return;
      const nextNodes = (data && data.nodes) || [];
      // Seed positions from the existing layout so unchanged nodes
      // don't move. Library treats x/y on a node as a placement hint;
      // the new sim relaxes around them.
      if (lastNodePosRef.current.size > 0) {
        for (const n of nextNodes) {
          const prev = lastNodePosRef.current.get(n.id);
          if (prev) {
            n.x = prev.x;
            n.y = prev.y;
            n.vx = prev.vx || 0;
            n.vy = prev.vy || 0;
          }
        }
      }
      setGraphData({
        nodes: nextNodes,
        links: (data && data.links) || [],
      });
      setTotalPersons((data && Number(data.total_persons)) || 0);
      setEdgeCountsByType((data && data.edge_counts_by_type) || {});
      setHitCap(!!(data && data.hit_cap));
      setLoading(false);
    }).catch(() => {
      if (!cancelled) {
        setGraphData({ nodes: [], links: [] });
        setTotalPersons(0);
        setEdgeCountsByType({});
        setHitCap(false);
        setLoading(false);
      }
    });

    return () => { cancelled = true; };
    // Use STABLE string fingerprints in the deps. Arrays/Sets compare
    // by reference, and the perspective context creates new instances
    // even when contents are unchanged — that previously caused both
    // unwanted refetches AND (more recently) missed refetches when
    // the array reference happened to be stable across a render. The
    // join() of sorted keys is a content-keyed hash that fires
    // exactly when the user's perspective truly changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    caseId,
    (personKeys || []).join('|'),
    depth,
    [...activeEventTypes].sort().join(','),
  ]);

  // Build a per-node search haystack ONCE per graph data load so the
  // per-keystroke filter is O(n) string-contains, not O(n × field
  // count). Every string on the node ends up in the haystack — name,
  // phone, type, owner, device_model, report_key, plus the phone
  // identity's short label ("P1") so the search bar matches what the
  // node renders to the user.
  const haystackByNodeId = useMemo(() => {
    const map = new Map();
    for (const n of graphData.nodes) {
      const phoneKey = n.report_key || n.cellebrite_report_key;
      const phoneIdentity = phoneCtx && phoneKey ? phoneCtx.getIdentityByKey(phoneKey) : null;
      const parts = [
        n.name, n.phone, n.type, n.phone_owner,
        n.report_key, n.cellebrite_report_key,
        phoneIdentity?.short, phoneIdentity?.model, phoneIdentity?.owner,
        // device + comm counts as text so "shared 3" / "comms 12" hit.
        n.device_count != null ? `devices:${n.device_count}` : null,
        n.comm_count != null ? `comms:${n.comm_count}` : null,
        n.shared ? 'shared' : null,
      ]
        .filter(Boolean)
        .map((v) => String(v).toLowerCase());
      map.set(n.id, parts.join(' '));
    }
    return map;
  }, [graphData.nodes, phoneCtx]);

  // Edge haystack lets `link.label` / count match too (e.g. "calls").
  const haystackByLink = useMemo(() => {
    const out = new Map();
    graphData.links.forEach((l, i) => {
      const parts = [l.label, l.count != null ? String(l.count) : null]
        .filter(Boolean)
        .map((v) => String(v).toLowerCase());
      out.set(i, parts.join(' '));
    });
    return out;
  }, [graphData.links]);

  // Backend search effect — only runs in Search mode (Filter mode
  // narrows the rendered subgraph client-side and is per-keystroke
  // synchronous). A 250 ms debounce keeps roundtrips down.
  useEffect(() => {
    if (searchMode !== 'search') {
      setSearchResults(null);
      setSearchLoading(false);
      return undefined;
    }
    const q = (searchTerm || '').trim();
    if (!q) {
      setSearchResults(null);
      setSearchLoading(false);
      return undefined;
    }
    let cancelled = false;
    setSearchLoading(true);
    const t = setTimeout(() => {
      cellebriteAPI
        .searchCrossPhoneGraph(caseId, q, { limit: 50 })
        .then((data) => {
          if (cancelled) return;
          setSearchResults(data || { results: [], total: 0, limited: false });
          setSearchLoading(false);
        })
        .catch(() => {
          if (cancelled) return;
          setSearchResults({ results: [], total: 0, limited: false });
          setSearchLoading(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [caseId, searchMode, searchTerm]);

  // First stage of the client-side filter pipeline: drop every link
  // whose event type is currently toggled OFF. PhoneReport-to-Person
  // structural links (label = 'CONTAINS_CONTACT' or 'BELONGS_TO')
  // always stay so the case skeleton remains visible. Nodes are kept
  // as-is — a Person whose only edges are now hidden still renders,
  // they just appear unconnected at this scope. That's honest: the
  // person IS in the case, they just don't participate in any of the
  // edge types you have switched on.
  const edgeTypeFiltered = useMemo(() => {
    if (graphData.links.length === 0) return graphData;
    const isStructural = (label) => {
      const l = (label || '').toLowerCase();
      return l === 'contains_contact' || l === 'belongs_to';
    };
    const visibleLinks = graphData.links.filter((l) => {
      if (isStructural(l.label)) return true;
      const t = (l.label || '').toLowerCase();
      return activeEventTypes.has(t);
    });
    return { nodes: graphData.nodes, links: visibleLinks };
  }, [graphData, activeEventTypes]);

  // Second stage: free-text *filter* narrowing (only active in Filter
  // mode). Search mode hits the backend instead and leaves the rendered
  // subgraph untouched — matches are highlighted on the canvas and
  // surfaced in the results panel.
  const filteredData = useMemo(() => {
    if (searchMode !== 'filter') return edgeTypeFiltered;
    const raw = (searchTerm || '').trim();
    if (!raw) return edgeTypeFiltered;

    const terms = tokeniseGraphSearch(raw);
    if (terms.length === 0) return edgeTypeFiltered;

    const matchesHaystack = (h) => terms.every((t) => h.includes(t));

    const matchingNodeIds = new Set();
    for (const n of edgeTypeFiltered.nodes) {
      if (matchesHaystack(haystackByNodeId.get(n.id) || '')) {
        matchingNodeIds.add(n.id);
      }
    }

    // Include any node connected by a link whose label/count itself
    // matches (so "calls" surfaces the call edges + both endpoints).
    edgeTypeFiltered.links.forEach((l, i) => {
      const linkHay = haystackByLink.get(i) || '';
      const srcId = typeof l.source === 'object' ? l.source.id : l.source;
      const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
      if (matchesHaystack(linkHay)) {
        matchingNodeIds.add(srcId);
        matchingNodeIds.add(tgtId);
      }
    });

    // Direct-neighbour expansion.
    const neighbourIds = new Set(matchingNodeIds);
    edgeTypeFiltered.links.forEach((l) => {
      const srcId = typeof l.source === 'object' ? l.source.id : l.source;
      const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
      if (matchingNodeIds.has(srcId)) neighbourIds.add(tgtId);
      if (matchingNodeIds.has(tgtId)) neighbourIds.add(srcId);
    });

    return {
      nodes: edgeTypeFiltered.nodes.filter((n) => neighbourIds.has(n.id)),
      links: edgeTypeFiltered.links.filter((l) => {
        const srcId = typeof l.source === 'object' ? l.source.id : l.source;
        const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
        return neighbourIds.has(srcId) && neighbourIds.has(tgtId);
      }),
    };
  }, [searchMode, edgeTypeFiltered, searchTerm, haystackByNodeId, haystackByLink]);

  // In Search mode we also compute a set of matched node ids so the
  // paint can highlight them (slight outline glow). The canvas data
  // itself is unfiltered in search mode — we want to SEE the matches
  // in context, not narrow to just them.
  const searchHighlightIds = useMemo(() => {
    if (searchMode !== 'search') return null;
    const raw = (searchTerm || '').trim();
    if (!raw) return null;
    const terms = tokeniseGraphSearch(raw);
    if (terms.length === 0) return null;
    const matches = new Set();
    for (const n of edgeTypeFiltered.nodes) {
      const h = haystackByNodeId.get(n.id) || '';
      if (terms.every((t) => h.includes(t))) matches.add(n.id);
    }
    return matches;
  }, [searchMode, searchTerm, edgeTypeFiltered.nodes, haystackByNodeId]);

  // Per-edge-type colour lookup. The backend tags each link's
  // `label` with the event-type key ('call', 'message', 'email',
  // 'location', 'wifi', 'cell_tower', 'meeting'); we map it to the
  // same colour the toggle chip uses so the graph reads visually
  // consistent with the chip strip. Unknown labels fall back to
  // neutral grey so we never crash on a stray relationship.
  const edgeColorByType = useMemo(() => {
    const m = new Map();
    for (const t of GRAPH_EVENT_TYPES) m.set(t.key, t.color);
    return m;
  }, []);

  // For each visible Person node, compute the set of active edge
  // types that node participates in (so we can paint small coloured
  // indicator dots around its circumference). PhoneReport nodes
  // skip the analysis — their colour already encodes phone identity.
  const nodeEdgeTypes = useMemo(() => {
    const map = new Map(); // nodeId -> Set<event-type-key>
    for (const l of filteredData.links) {
      const t = (l.label || '').toLowerCase();
      if (!edgeColorByType.has(t)) continue;
      const srcId = typeof l.source === 'object' ? l.source.id : l.source;
      const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
      if (!map.has(srcId)) map.set(srcId, new Set());
      if (!map.has(tgtId)) map.set(tgtId, new Set());
      map.get(srcId).add(t);
      map.get(tgtId).add(t);
    }
    return map;
  }, [filteredData.links, edgeColorByType]);

  // Node renderer — concentric-ring encoding.
  //
  // Person nodes are drawn as three nested shapes:
  //   1. INNER DISC   = phone identity colour (which device they're on)
  //   2. OUTER RING   = segmented pie of edge-type colours, one slice
  //                     per type the person participates in across the
  //                     visible edges. Single-type = solid ring; multi-
  //                     type = donut wedges (alphabetical by type-key
  //                     for stable ordering across renders).
  //   3. SHARED HALO  = bold gold stroke outside the outer ring, drawn
  //                     only when the contact is shared across phones.
  //
  // PhoneReport nodes keep the existing rounded-square treatment in
  // their phone identity colour — they ARE phones, not participants in
  // a communication graph, so the ring encoding doesn't apply.
  //
  // Sizes scale with comm_count so heavily-active people draw bigger,
  // matching the original behaviour.
  const paintNode = useCallback((node, ctx, globalScale) => {
    const isReport = node.type === 'PhoneReport';
    const isShared = !!node.shared;

    const phoneKey = node.report_key || node.cellebrite_report_key;
    const phoneIdentity = phoneCtx && phoneKey
      ? phoneCtx.getIdentityByKey(phoneKey)
      : null;

    // Per-node label state. We render one of:
    //   - 'hidden'  — no label
    //   - 'small'   — compact label (default visible state)
    //   - 'hover'   — bigger label on the hovered node
    //   - 'match'   — coloured label for search matches
    //   - 'pinned'  — bold label for Phones (always shown)
    // Callers pass the state to drawLabel which picks size + colour.
    const isHovered = hoveredNode && hoveredNode.id === node.id;
    const isMatch = searchHighlightIds && searchHighlightIds.has(node.id);

    // What label state does this node get?
    //   - Phones: always 'pinned'
    //   - Hovered node: 'hover' (overrides others)
    //   - Search matches: 'match'
    //   - All-labels-on master toggle: 'small'
    //   - Otherwise: 'hidden'
    let labelState;
    if (isReport) labelState = 'pinned';
    else if (isHovered) labelState = 'hover';
    else if (isMatch) labelState = 'match';
    else if (labelsAllOn) labelState = 'small';
    else labelState = 'hidden';

    const drawLabel = (text, atY) => {
      if (!text || labelState === 'hidden') return;
      // Smaller defaults — the previous 12-14px range overwhelmed
      // dense graphs. Default labels sit at 8px; hover bumps to 12
      // (the user asked specifically for "enlarge on hover"); search
      // matches get a colour pop + a slight size boost so they're
      // still legible without dominating the canvas; Phones stay
      // bold at 11.
      const TARGETS = { small: 8, hover: 12, match: 10, pinned: 11 };
      const COLORS = {
        small: '#475569',
        hover: '#0f172a',
        match: '#0e7490', // cyan-700 — pairs with the cyan halo
        pinned: '#1f2937',
      };
      const BOLD = { small: false, hover: true, match: true, pinned: true };
      const targetPx = TARGETS[labelState];
      const fontSize = Math.max(4, targetPx / globalScale);
      const bold = BOLD[labelState];
      ctx.font = `${bold ? 'bold ' : ''}${fontSize}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      const metrics = ctx.measureText(text);
      const padX = 3.5 / globalScale;
      const padY = 1.8 / globalScale;
      const w = metrics.width + padX * 2;
      const h = fontSize + padY * 2;
      const x = node.x - w / 2;
      const y = atY - h / 2;

      // White pill background
      ctx.fillStyle = labelState === 'match'
        ? 'rgba(236, 254, 255, 0.95)' // cyan-50
        : 'rgba(255, 255, 255, 0.92)';
      ctx.beginPath();
      const radius = Math.min(3.5 / globalScale, h / 2);
      ctx.moveTo(x + radius, y);
      ctx.lineTo(x + w - radius, y);
      ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
      ctx.lineTo(x + w, y + h - radius);
      ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
      ctx.lineTo(x + radius, y + h);
      ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
      ctx.lineTo(x, y + radius);
      ctx.quadraticCurveTo(x, y, x + radius, y);
      ctx.closePath();
      ctx.fill();

      // Subtle ring — slightly stronger for match labels so they
      // pop against neighbouring un-coloured pills.
      ctx.lineWidth = Math.max(0.35, (labelState === 'match' ? 0.8 : 0.5) / globalScale);
      ctx.strokeStyle = labelState === 'match'
        ? 'rgba(34, 211, 238, 0.7)'
        : 'rgba(148, 163, 184, 0.45)';
      ctx.stroke();

      // Text
      ctx.fillStyle = COLORS[labelState];
      ctx.fillText(text, node.x, atY);
    };

    // PhoneReport: unchanged rounded-square in phone colour.
    if (isReport) {
      const r = 8;
      ctx.beginPath();
      const size = r * 2;
      ctx.roundRect(node.x - r, node.y - r, size, size, 3);
      ctx.fillStyle = phoneIdentity ? phoneIdentity.hex : NODE_COLORS.PhoneReport;
      ctx.fill();

      let label = (node.name || '').substring(0, 28);
      if (phoneIdentity) label = `${phoneIdentity.short} · ${label}`;
      drawLabel(label, node.y + r + (10 / globalScale), { bold: true });
      return;
    }

    // Resource — small diamond in the resource type's colour. Stands
    // visually apart from the round Person rings + square Phones so
    // the three concepts (people, phones, resources) read at a glance.
    // A phone-count > 1 (resource owned by more than one phone) gets
    // a gold halo because it's a natural cross-phone connector.
    if (node.type === 'Resource') {
      const resType = node.resource_type;
      const fill = edgeColorByType.get(resType) || '#94a3b8';
      const r = 5 + Math.min(node.hits || 0, 60) * 0.04;
      // Draw diamond (square rotated 45°).
      ctx.beginPath();
      ctx.moveTo(node.x, node.y - r);
      ctx.lineTo(node.x + r, node.y);
      ctx.lineTo(node.x, node.y + r);
      ctx.lineTo(node.x - r, node.y);
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.lineWidth = Math.max(0.5, 0.8 / globalScale);
      ctx.strokeStyle = '#ffffff';
      ctx.stroke();

      // Multi-phone resource → gold halo (same gold as a shared
      // Person, signalling "connector across phones").
      if (node.phone_count && node.phone_count > 1) {
        ctx.beginPath();
        ctx.moveTo(node.x, node.y - r - 2);
        ctx.lineTo(node.x + r + 2, node.y);
        ctx.lineTo(node.x, node.y + r + 2);
        ctx.lineTo(node.x - r - 2, node.y);
        ctx.closePath();
        ctx.lineWidth = Math.max(1.4, 1.6 / globalScale);
        ctx.strokeStyle = '#d97706';
        ctx.stroke();
      }

      // Search highlight ring.
      if (searchHighlightIds && searchHighlightIds.has(node.id)) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI);
        ctx.lineWidth = Math.max(1.5, 2 / globalScale);
        ctx.strokeStyle = '#22d3ee';
        ctx.stroke();
      }

      // Multi-select ring (drag-box selection)
      if (multiSelection.has(node.id)) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + 6, 0, 2 * Math.PI);
        ctx.lineWidth = Math.max(1.8, 2.4 / globalScale);
        ctx.strokeStyle = '#10b981'; // emerald-500 — distinct from cyan/gold
        ctx.setLineDash([4 / globalScale, 3 / globalScale]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Label — visible by default labels are off; hover/match/all-on
      // controls visibility per labelState.
      const label = (node.name || '').substring(0, 28);
      drawLabel(label, node.y + r + (8 / globalScale));
      return;
    }

    // Person — concentric rings.
    // Base radius scales gently with comm volume.
    const rOuter = 6 + Math.min(node.comm_count || 0, 10) * 0.45;
    const rInner = rOuter * 0.55; // inner disc roughly half the diameter

    const phoneHex = phoneIdentity ? phoneIdentity.hex : '#94a3b8';

    // The edge-type set this person participates in among visible edges.
    const types = [...(nodeEdgeTypes.get(node.id) || [])].sort();

    // --- 1. Outer ring (edge-type pie) ---
    // If the person has no visible edges (e.g. user toggled everything
    // off, or they're an isolate in the current filter), the outer ring
    // becomes a neutral grey so the node still reads as "a person, just
    // not currently linked".
    if (types.length === 0) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, rOuter, 0, 2 * Math.PI);
      ctx.fillStyle = '#cbd5e1'; // light-300
      ctx.fill();
    } else if (types.length === 1) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, rOuter, 0, 2 * Math.PI);
      ctx.fillStyle = edgeColorByType.get(types[0]) || '#94a3b8';
      ctx.fill();
    } else {
      // Pie slices — start at -90° (12 o'clock) and go clockwise.
      const sliceArc = (2 * Math.PI) / types.length;
      for (let i = 0; i < types.length; i++) {
        const start = -Math.PI / 2 + i * sliceArc;
        const end = start + sliceArc;
        ctx.beginPath();
        ctx.moveTo(node.x, node.y);
        ctx.arc(node.x, node.y, rOuter, start, end);
        ctx.closePath();
        ctx.fillStyle = edgeColorByType.get(types[i]) || '#94a3b8';
        ctx.fill();
      }
    }

    // --- 2. Thin white gap so the inner phone disc reads cleanly ---
    ctx.beginPath();
    ctx.arc(node.x, node.y, rInner + 0.7, 0, 2 * Math.PI);
    ctx.fillStyle = '#ffffff';
    ctx.fill();

    // --- 3. Inner phone-colour disc ---
    ctx.beginPath();
    ctx.arc(node.x, node.y, rInner, 0, 2 * Math.PI);
    ctx.fillStyle = phoneHex;
    ctx.fill();

    // --- 4. Shared halo (drawn LAST so it sits on top) ---
    if (isShared) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, rOuter + 1.2, 0, 2 * Math.PI);
      ctx.lineWidth = Math.max(1.6, 1.8 / globalScale);
      ctx.strokeStyle = '#d97706'; // amber-600
      ctx.stroke();
    }

    // --- 5. Search highlight ring (Search mode, matched nodes) ---
    // Drawn even further out than the shared halo so the two signals
    // can co-exist. A bright cyan glow reads off both light and dark
    // edge colours; we also fade the unmatched nodes slightly via the
    // alpha on the outer ring (handled implicitly — search mode keeps
    // every node rendered, the highlight just makes matches POP).
    if (searchHighlightIds && searchHighlightIds.has(node.id)) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, rOuter + 3.5, 0, 2 * Math.PI);
      ctx.lineWidth = Math.max(2, 2.4 / globalScale);
      ctx.strokeStyle = '#22d3ee'; // cyan-400 — distinct from the
                                   // amber shared halo and from every
                                   // edge-type colour.
      ctx.stroke();
    }

    // Multi-select dashed ring
    if (multiSelection.has(node.id)) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, rOuter + 5.5, 0, 2 * Math.PI);
      ctx.lineWidth = Math.max(1.8, 2.4 / globalScale);
      ctx.strokeStyle = '#10b981';
      ctx.setLineDash([4 / globalScale, 3 / globalScale]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Label — white pill background keeps Person names readable
    // against any backdrop, including dense clusters.
    const label = (node.name || '').substring(0, 28);
    drawLabel(label, node.y + rOuter + (10 / globalScale));
  }, [phoneCtx, nodeEdgeTypes, edgeColorByType, searchHighlightIds, hoveredNode, labelsAllOn, multiSelection]);

  const handleZoomIn = () => fgRef.current?.zoom(fgRef.current.zoom() * 1.5, 300);
  const handleZoomOut = () => fgRef.current?.zoom(fgRef.current.zoom() / 1.5, 300);
  const handleFit = () => fgRef.current?.zoomToFit(400, 40);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-light-400" />
      </div>
    );
  }

  if (graphData.nodes.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-light-500 text-sm">
        No cross-phone data available
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col" ref={containerRef}>
      {/* Controls */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
        {/* Filter | Search mode toggle */}
        <div className="inline-flex border border-light-300 rounded overflow-hidden text-[11px] flex-shrink-0">
          <button
            type="button"
            onClick={() => setSearchMode('filter')}
            className={`px-2 py-1 inline-flex items-center gap-1 ${
              searchMode === 'filter'
                ? 'bg-owl-blue-100 text-owl-blue-900'
                : 'text-light-700 hover:bg-light-100'
            }`}
            title="Filter mode — narrow the rendered subgraph to matches + neighbours"
          >
            <FilterIcon className="w-3 h-3" />
            Filter
          </button>
          <button
            type="button"
            onClick={() => setSearchMode('search')}
            className={`px-2 py-1 inline-flex items-center gap-1 border-l border-light-200 ${
              searchMode === 'search'
                ? 'bg-owl-blue-100 text-owl-blue-900'
                : 'text-light-700 hover:bg-light-100'
            }`}
            title="Search mode — highlight matches in context + search the full case via the results panel"
          >
            <SearchIcon className="w-3 h-3" />
            Search
          </button>
        </div>

        <div className="flex-1 max-w-xl">
          {/* Filter mode: per-keystroke client-side narrow.
              Search mode: highlight matches + hit the backend for the
              full Person set (results panel below the toolbar). */}
          <CellebriteSearchInput
            value={searchTerm}
            onChange={setSearchTerm}
            placeholder={
              searchMode === 'filter'
                ? 'Filter the rendered graph — name, phone, app, device, "exact phrase"…'
                : 'Search the entire case — Persons not in the rendered 200 will appear in the results panel'
            }
            matchCount={
              searchMode === 'filter'
                ? filteredData.nodes.length
                : (searchHighlightIds ? searchHighlightIds.size : graphData.nodes.length)
            }
            totalCount={graphData.nodes.length}
            itemNoun={searchMode === 'filter' ? 'node' : 'match'}
            compact
          />
        </div>
        <button onClick={handleZoomIn} className="p-1.5 hover:bg-light-200 rounded" title="Zoom in">
          <ZoomIn className="w-4 h-4 text-light-600" />
        </button>
        <button onClick={handleZoomOut} className="p-1.5 hover:bg-light-200 rounded" title="Zoom out">
          <ZoomOut className="w-4 h-4 text-light-600" />
        </button>
        <button onClick={handleFit} className="p-1.5 hover:bg-light-200 rounded" title="Fit to view">
          <Maximize2 className="w-4 h-4 text-light-600" />
        </button>
        {/* Counter — shows what's on canvas vs what's in the case.
            The "capped" badge ONLY appears when the backend hit a
            hard 2,000-node ceiling. The gap between rendered and
            total Persons usually comes from the active-edge filter,
            not a cap, so reading "643 of 1,763" without the badge
            means "the other 1,120 don't participate in any of the
            currently active edge types — toggle more chips on to
            bring them in." */}
        <div className="text-xs text-light-500 ml-2 whitespace-nowrap">
          {filteredData.nodes.length.toLocaleString()} of {totalPersons > 0 ? totalPersons.toLocaleString() : graphData.nodes.length.toLocaleString()} nodes
          {hitCap && (
            <span className="ml-1 text-amber-600 font-medium" title="Backend hit the 2,000-node ceiling. Anchor on a Person via search to drill into a smaller neighbourhood, or use Search mode to find any node in the case.">
              · capped at 2,000
            </span>
          )}
          {!hitCap && totalPersons > 0 && filteredData.nodes.length < totalPersons && (
            <span className="ml-1 text-light-400" title="The rest don't participate in any of the currently active edge types. Toggle more chips on (Messages, Emails, Visits, etc.) to bring them in.">
              · {(totalPersons - filteredData.nodes.length).toLocaleString()} hidden by filters
            </span>
          )}
          {' · '}
          {filteredData.links.length.toLocaleString()} edges
        </div>
      </div>

      {/* Legend — explains the concentric-ring encoding:
            inner disc  = phone identity (which device the contact is on)
            outer ring  = edge-type pie (one slice per type they're in)
            gold halo   = shared across multiple phones                */}
      <div className="flex items-center gap-3 px-4 py-1.5 border-b border-light-100 text-xs text-light-600 flex-shrink-0 flex-wrap">
        {/* Inline SVG sample so the user can see the exact encoding
            the graph paints — phone-coloured inner, multi-coloured
            outer ring (using up to 3 edge-type colours), gold halo. */}
        <svg viewBox="-12 -12 24 24" className="w-5 h-5 flex-shrink-0">
          {/* Outer ring sample = three quarters in three different
              edge-type colours — calls / messages / locations — so
              the user immediately reads "outer = comm types". */}
          <path d="M 0 -9 A 9 9 0 0 1 9 0 L 0 0 Z" fill={GRAPH_EVENT_TYPES[1].color} />
          <path d="M 9 0 A 9 9 0 0 1 0 9 L 0 0 Z" fill={GRAPH_EVENT_TYPES[0].color} />
          <path d="M 0 9 A 9 9 0 1 1 0 -9 L 0 0 Z" fill={GRAPH_EVENT_TYPES[3].color} />
          <circle cx="0" cy="0" r="5" fill="#ffffff" />
          <circle cx="0" cy="0" r="4.3" fill="#3b82f6" />
          <circle cx="0" cy="0" r="10.5" fill="none" stroke="#d97706" strokeWidth="1.4" />
        </svg>
        <span className="text-light-700">
          <span className="font-medium">Inner</span> = phone ·
          <span className="font-medium ml-1">outer slices</span> = edge types ·
          <span className="font-medium ml-1 text-amber-700">gold halo</span> = shared
        </span>

        {/* Edge-type swatches — only the ACTIVE event types so the
            legend mirrors what the user can actually see right now. */}
        <span className="h-4 w-px bg-light-300" />
        <span className="text-light-500 font-medium">Active edges:</span>
        {GRAPH_EVENT_TYPES.filter((t) => activeEventTypes.has(t.key)).map((t) => (
          <span key={t.key} className="flex items-center gap-1" title={`${t.label} edges`}>
            <span
              className="inline-block w-3 h-0.5 rounded"
              style={{ backgroundColor: t.color }}
            />
            <span>{t.label}</span>
          </span>
        ))}
        {activeEventTypes.size === 0 && (
          <span className="text-light-400 italic">no edge types selected</span>
        )}

        {phoneCtx?.hasMultiple && (
          <>
            <span className="h-4 w-px bg-light-300" />
            <span className="text-light-500 font-medium">Phones:</span>
            {phoneCtx.reports.map((r) => (
              <PhoneIdentityChip
                key={r.report_key}
                reportKey={r.report_key}
                variant="default"
              />
            ))}
          </>
        )}
      </div>

      {/* Event-type toggle strip — same data, more connections.
          Calls/messages/emails on by default; locations/wifi/cell/etc.
          opt-in because they create dense edges fast. Each chip carries
          a small count badge so the user can tell whether toggling it
          will actually surface anything (0 = no cross-Person edges
          exist for this type on the current dataset). */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-light-100 bg-light-50 text-xs flex-shrink-0 flex-wrap">
        <span className="text-light-500 font-medium">Show edges:</span>
        {GRAPH_EVENT_TYPES.map((t) => {
          const Icon = t.icon;
          const on = activeEventTypes.has(t.key);
          const cnt = Number(edgeCountsByType?.[t.key]) || 0;
          const empty = cnt === 0;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => {
                setActiveEventTypes((prev) => {
                  const next = new Set(prev);
                  if (next.has(t.key)) next.delete(t.key);
                  else next.add(t.key);
                  return next;
                });
              }}
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-[11px] rounded border transition-colors ${
                on
                  ? 'border-owl-blue-300 bg-owl-blue-50 text-owl-blue-900'
                  : 'border-light-300 bg-white text-light-500 hover:bg-light-100'
              } ${empty ? 'opacity-60' : ''}`}
              title={
                empty
                  ? `${t.label}: no cross-Person edges in this dataset (needs ≥2 phones sharing the same value)`
                  : `Toggle ${t.label} edges (${cnt} in dataset)`
              }
            >
              <Icon className="w-3 h-3" style={{ color: on ? t.color : undefined }} />
              {t.label}
              <span
                className={`ml-0.5 text-[10px] tabular-nums ${
                  empty ? 'text-light-400' : on ? 'text-owl-blue-700' : 'text-light-500'
                }`}
              >
                {cnt}
              </span>
            </button>
          );
        })}

        {perspective?.hasPerspective && (
          <>
            <span className="h-4 w-px bg-light-300 mx-1" />
            <span className="text-light-500 font-medium">Depth:</span>
            <div className="inline-flex border border-light-300 rounded overflow-hidden">
              {[1, 2].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDepth(d)}
                  className={`px-1.5 py-0.5 text-[11px] ${depth === d ? 'bg-owl-blue-100 text-owl-blue-900' : 'bg-white text-light-600 hover:bg-light-100'}`}
                  title={d === 1 ? 'Anchors + direct contacts' : 'Anchors + friends-of-friends'}
                >
                  {d}
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Perspective + multi-selection banner. Surfaces either:
            - The currently-anchored perspective (Anchored on …)
            - The drag-box multi-selection (N nodes selected)
          Either source produces a lens the user can pivot into
          another tab via the right-hand button group.
       */}
      {(perspective?.hasPerspective || multiSelection.size > 0) && (
        <div className="flex items-center gap-2 px-4 py-1 border-b border-amber-200 bg-amber-50 text-[11px] text-amber-900 flex-shrink-0 flex-wrap">
          {multiSelection.size > 0 ? (
            <>
              <span className="font-semibold uppercase tracking-wide text-[10px] text-amber-700">
                Selected:
              </span>
              <span>{multiSelection.size} node{multiSelection.size === 1 ? '' : 's'}</span>
              <button
                type="button"
                onClick={() => setMultiSelection(new Set())}
                className="text-[10px] text-amber-800 hover:bg-amber-100 px-1.5 py-0.5 rounded inline-flex items-center gap-1"
                title="Clear selection"
              >
                <X className="w-2.5 h-2.5" />
                Clear
              </button>
            </>
          ) : (
            <>
              <span className="font-semibold uppercase tracking-wide text-[10px] text-amber-700">
                Anchored on:
              </span>
              <span className="truncate">
                {perspective.active?.label}
                {perspective.active?.personKeys?.length > 1 && (
                  <span className="ml-1 text-amber-600">
                    ({perspective.active.personKeys.length})
                  </span>
                )}
              </span>
              <button
                type="button"
                onClick={() => perspective.clear()}
                className="text-[10px] text-amber-800 hover:bg-amber-100 px-1.5 py-0.5 rounded inline-flex items-center gap-1"
                title="Clear perspective and show the whole case"
              >
                <X className="w-2.5 h-2.5" />
                Show whole case
              </button>
            </>
          )}

          {/* Cross-tab pivot bar — open the active lens in any other
              Cellebrite surface. Each button fires pivotTo() which
              publishes the Person-keys handoff + requests a tab
              switch. */}
          <span className="ml-auto inline-flex items-center gap-1 flex-wrap">
            <span className="text-[9px] uppercase tracking-wide text-amber-700">View in</span>
            <PivotBtn icon={MessageSquare} label="Comms"        onClick={() => pivotTo('comms')} />
            <PivotBtn icon={UsersIcon}     label="Communications" onClick={() => pivotTo('communications')} />
            <PivotBtn icon={Clock}         label="Timeline"     onClick={() => pivotTo('timeline')} />
            <PivotBtn icon={MapPin}        label="Locations"    onClick={() => pivotTo('locations')} />
            <PivotBtn icon={Tag}           label="Events"       onClick={() => pivotTo('events')} />
            <PivotBtn icon={FolderTree}    label="Files"        onClick={() => pivotTo('files')} />
            <PivotBtn icon={UserCheck}     label="Unified"      onClick={() => pivotTo('unified')} />
          </span>
        </div>
      )}

      {/* Mode hint bar — small instructions for the right-click
          multi-select gesture + the labels toggle. */}
      <div className="flex items-center gap-2 px-4 py-1 border-b border-light-100 bg-light-50 text-[10px] text-light-600 flex-shrink-0">
        <MousePointerSquareDashed className="w-3 h-3 text-light-500" />
        <span className="text-light-500">
          Right-click + drag to select a group · drag any selected node to move the whole group · click empty space to clear
        </span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setLabelsAllOn((v) => !v)}
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] ${
            labelsAllOn
              ? 'border-owl-blue-300 bg-owl-blue-50 text-owl-blue-900'
              : 'border-light-300 bg-white text-light-700 hover:bg-light-100'
          }`}
          title={labelsAllOn ? 'Hide labels (show only on hover + search matches + phones)' : 'Show every node label'}
        >
          <Tag className="w-2.5 h-2.5" />
          {labelsAllOn ? 'Labels on' : 'Labels off'}
        </button>
      </div>

      {/* Graph */}
      <div
        className="flex-1 min-h-0 relative"
        // Right-click engages the rubber-band selection. We suppress
        // the browser's default context menu on this surface so the
        // gesture feels natural; the lib already uses right-click
        // for its own thing on nodes via onNodeRightClick (currently
        // unused after this refactor).
        onContextMenu={(e) => e.preventDefault()}
        onMouseDown={(e) => {
          // mouse button 2 = right click
          if (e.button !== 2) return;
          if (e.target.closest('[data-graph-overlay]')) return;
          const rect = e.currentTarget.getBoundingClientRect();
          const x = e.clientX - rect.left;
          const y = e.clientY - rect.top;
          selectionBoxStartRef.current = { x, y };
          setSelectionBox({ x1: x, y1: y, x2: x, y2: y });
        }}
        onMouseMove={(e) => {
          if (!selectionBoxStartRef.current) return;
          const rect = e.currentTarget.getBoundingClientRect();
          const x = e.clientX - rect.left;
          const y = e.clientY - rect.top;
          setSelectionBox({
            x1: selectionBoxStartRef.current.x,
            y1: selectionBoxStartRef.current.y,
            x2: x,
            y2: y,
          });
        }}
        onMouseUp={(e) => {
          // Only commit a selection if THIS was a right-click drag.
          // Left-click drags are handled by the lib's own node-drag.
          if (!selectionBoxStartRef.current || !selectionBox || !fgRef.current) {
            selectionBoxStartRef.current = null;
            setSelectionBox(null);
            return;
          }
          // Convert the box's screen coords to graph coords and
          // collect every node inside.
          const { x1, y1, x2, y2 } = selectionBox;
          const xMin = Math.min(x1, x2);
          const xMax = Math.max(x1, x2);
          const yMin = Math.min(y1, y2);
          const yMax = Math.max(y1, y2);
          // Ignore tiny clicks — treat <4px as a misclick.
          if (xMax - xMin < 4 || yMax - yMin < 4) {
            selectionBoxStartRef.current = null;
            setSelectionBox(null);
            return;
          }
          try {
            const a = fgRef.current.screen2GraphCoords(xMin, yMin);
            const b = fgRef.current.screen2GraphCoords(xMax, yMax);
            const gxMin = Math.min(a.x, b.x);
            const gxMax = Math.max(a.x, b.x);
            const gyMin = Math.min(a.y, b.y);
            const gyMax = Math.max(a.y, b.y);
            const next = new Set();
            const selectedNodes = [];
            for (const n of graphData.nodes) {
              if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) continue;
              if (n.x >= gxMin && n.x <= gxMax && n.y >= gyMin && n.y <= gyMax) {
                next.add(n.id);
                selectedNodes.push(n);
              }
            }
            setMultiSelection(next);

            // Publish the full selection to the rail so the user sees
            // one rich info card per node (GraphSelectionAccordion
            // handles the type-aware rendering). We pass the actual
            // node payloads via the buildNodePayload helper — gives
            // the rail everything it needs without an extra fetch.
            if (selectEntity && selectedNodes.length > 0) {
              const nodePayloads = selectedNodes
                .map((n) => buildNodePayload(n, graphData.links))
                .filter(Boolean);
              // Cap at 200 so a huge box drag doesn't ship 1k items
              // into the rail (which would freeze the panel render).
              const capped = nodePayloads.slice(0, 200);
              selectEntity({
                type: 'graph-selection',
                id: `graph-selection-${Date.now()}`,
                caseId,
                payload: {
                  total: nodePayloads.length,
                  truncated: nodePayloads.length > capped.length,
                  nodes: capped,
                },
                source: 'graph.rubber-band',
              });
            }
          } catch { /* ref not ready */ }
          selectionBoxStartRef.current = null;
          setSelectionBox(null);
        }}
      >
        <ForceGraph2D
          /* ref assigned below in a callback so we can also tune
             the live d3-force objects on mount */
          graphData={filteredData}
          nodeCanvasObject={paintNode}
          nodePointerAreaPaint={(node, color, ctx) => {
            const r = node.type === 'PhoneReport' ? 8 : 6;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
            ctx.fill();
          }}
          linkColor={(l) => {
            // Edge tint = the edge-type colour at moderate opacity. Hex
            // colours don't take a built-in alpha argument here, so we
            // emit `rgba()` via a tiny adapter. Unknown labels fall
            // through to a near-grey so we never crash on stray data.
            const c = edgeColorByType.get((l.label || '').toLowerCase());
            return c ? withAlpha(c, 0.55) : '#cbd5e1';
          }}
          linkWidth={l => l.count ? Math.min(l.count / 5, 3) : 0.5}
          linkDirectionalArrowLength={0}
          onNodeHover={setHoveredNode}
          warmupTicks={50}
          cooldownTicks={100}
          d3AlphaDecay={0.05}
          d3VelocityDecay={0.3}
          // Spread the layout so nodes don't sit on top of each other.
          // The library exposes the live d3-force objects via dForce
          // accessors on the props themselves — these widen the
          // baseline link distance and increase the repulsion charge,
          // producing more breathing room without redesigning the
          // simulation.
          //
          // Numbers picked to put a typical 1-hop neighbourhood at
          // ~80-120 canvas units between connected nodes, vs. ~30
          // before which is what made labels crowd into each other.
          ref={(el) => {
            fgRef.current = el;
            if (el && el.d3Force) {
              try {
                const linkF = el.d3Force('link');
                if (linkF && linkF.distance) linkF.distance(80);
                const chargeF = el.d3Force('charge');
                if (chargeF && chargeF.strength) chargeF.strength(-180);
              } catch { /* ignore — lib will fall back to defaults */ }
            }
          }}
          // Sticky drag — when the user drops a node we leave its
          // fx/fy set so the simulation can't pull it back to the
          // force equilibrium. The library's default behaviour clears
          // them on dragend, which let nodes snap home and frustrated
          // the user. They can un-pin by double-clicking (handler
          // below) or by toggling chips (which refetches and seeds
          // positions from this same x/y, then releases).
          // Drag start — if the user grabs a node that's in the
          // multi-selection, snapshot every selected node's starting
          // position so we can translate the whole group as the drag
          // progresses.
          onNodeDragStart={(node) => {
            if (!node || !multiSelection.has(node.id)) {
              groupDragRef.current = null;
              return;
            }
            const positions = new Map();
            for (const id of multiSelection) {
              const n = graphData.nodes.find((m) => m.id === id);
              if (n && Number.isFinite(n.x) && Number.isFinite(n.y)) {
                positions.set(id, { x: n.x, y: n.y });
              }
            }
            groupDragRef.current = {
              anchorId: node.id,
              anchorStart: { x: node.x, y: node.y },
              positions,
            };
          }}
          // During drag — translate every other selected node by the
          // same delta as the dragged anchor. Use fx/fy so the lib
          // doesn't try to fight us; pins are made permanent on
          // dragend.
          onNodeDrag={(node) => {
            const gd = groupDragRef.current;
            if (!gd || !node || node.id !== gd.anchorId) return;
            const dx = node.x - gd.anchorStart.x;
            const dy = node.y - gd.anchorStart.y;
            for (const [id, start] of gd.positions) {
              if (id === gd.anchorId) continue;
              const n = graphData.nodes.find((m) => m.id === id);
              if (!n) continue;
              n.fx = start.x + dx;
              n.fy = start.y + dy;
              n.x = n.fx;
              n.y = n.fy;
            }
          }}
          // Drag end — pin every node we moved (the anchor + all
          // group members) so the sim can't yank them back. If this
          // wasn't a group drag, just pin the single node like before.
          onNodeDragEnd={(node) => {
            if (!node) return;
            node.fx = node.x;
            node.fy = node.y;
            const gd = groupDragRef.current;
            if (gd && node.id === gd.anchorId) {
              for (const id of gd.positions.keys()) {
                if (id === gd.anchorId) continue;
                const n = graphData.nodes.find((m) => m.id === id);
                if (!n) continue;
                n.fx = n.x;
                n.fy = n.y;
              }
            }
            groupDragRef.current = null;
          }}
          // Single-click a node → publish to the universal selection
          // rail so the user sees the full content (calls/messages
          // for a Person, list of accounts for a Phone, the actual
          // bucket value for a Resource). Also seeds the multi-
          // selection so the perspective banner's pivot bar can
          // hand off to other tabs immediately.
          onNodeClick={(node) => {
            if (!node) return;
            setMultiSelection(new Set([node.id]));
            if (selectEntity) {
              const payload = buildNodePayload(node, graphData.links);
              selectEntity({
                type: payload.type,
                id: payload.id,
                caseId,
                reportKey: payload.reportKey || null,
                payload,
                source: 'graph.node-click',
              });
            }
          }}
          // Right-click on a node is now the rubber-band-selection
          // gesture at the canvas level (handled by the wrapper's
          // onMouseDown). We DO want to forward the contextmenu
          // suppression — done on the wrapper.
          // Camera lock during post-refetch sim warm-up.
          //
          // The library auto-fits when graphData changes — that's the
          // visible "snap to neutral" the user pushed back on. We can't
          // disable the auto-fit, but we CAN overwrite the camera on
          // every tick while a snapshot is active so the user never
          // sees the auto-fit's intermediate state.
          //
          // onEngineTick fires every frame during warm-up; we slam
          // centerAt + zoom back to the snapshot value each frame.
          // The lib's own zoom mutations happen between ticks, so the
          // user sees only OUR camera position. Cheap (two setters per
          // frame for the ~100 cooldownTicks).
          //
          // Snapshot is cleared in onEngineStop so future user-driven
          // pan/zoom is never overwritten.
          onEngineTick={() => {
            const snap = cameraSnapshotRef.current;
            if (!snap || !fgRef.current) return;
            try {
              fgRef.current.centerAt(snap.x, snap.y, 0);
              fgRef.current.zoom(snap.z, 0);
            } catch { /* ref not ready */ }
          }}
          onEngineStop={() => {
            // Final clamp + release. Without this, the very last tick
            // might let the lib's auto-fit win.
            const snap = cameraSnapshotRef.current;
            if (snap && fgRef.current) {
              try {
                fgRef.current.centerAt(snap.x, snap.y, 0);
                fgRef.current.zoom(snap.z, 0);
              } catch { /* ref not ready */ }
            }
            cameraSnapshotRef.current = null;
          }}
        />

        {/* Rubber-band selection overlay — visible while the user is
            dragging in Select mode. Pointer-events disabled so it
            never swallows the mousemove/up events. */}
        {selectionBox && (
          <div
            data-graph-overlay="selection-box"
            className="absolute pointer-events-none border-2 border-emerald-500 bg-emerald-500/10 rounded-sm"
            style={{
              left: Math.min(selectionBox.x1, selectionBox.x2),
              top: Math.min(selectionBox.y1, selectionBox.y2),
              width: Math.abs(selectionBox.x2 - selectionBox.x1),
              height: Math.abs(selectionBox.y2 - selectionBox.y1),
            }}
          />
        )}

        {/* Search results panel — overlays the canvas in Search mode.
            Lists every Person in the case matching the query (not
            just the 200 rendered). Each row clicks to anchor the
            graph on that person via the perspective context. */}
        {searchMode === 'search' && (searchTerm || '').trim() && (
          <div data-graph-overlay="search-results" className="absolute top-3 right-3 w-72 max-h-[60vh] bg-white border border-light-300 shadow-lg rounded-lg overflow-hidden z-20 flex flex-col">
            <div className="px-3 py-2 border-b border-light-200 bg-light-50 flex items-center gap-2 flex-shrink-0">
              <SearchIcon className="w-3.5 h-3.5 text-owl-blue-600" />
              <span className="text-xs font-semibold text-owl-blue-900 flex-1 truncate">
                Search results
              </span>
              {searchLoading && <Loader2 className="w-3 h-3 animate-spin text-light-400" />}
              {searchResults && (
                <span className="text-[10px] text-light-500">
                  {searchResults.total.toLocaleString()}
                  {searchResults.limited ? ' (top 50)' : ''}
                </span>
              )}
            </div>
            <div className="flex-1 overflow-y-auto">
              {searchResults && searchResults.results.length === 0 && !searchLoading && (
                <div className="text-xs italic text-light-500 px-3 py-4 text-center">
                  No Persons match "{searchTerm}".
                </div>
              )}
              {searchResults && searchResults.results.map((r, idx) => {
                const isResource = r.entity === 'resource';
                // Person id format = `person-{key}`. Resource id
                // format = `res-{type}-{safe-bucket}`. The backend
                // search now returns each Resource's rolled-up
                // `bucket` (host for visits/bookmarks, raw value
                // otherwise) — exactly the key the graph's resource
                // pass used. We match by (resource_type, bucket).
                const candidateId = isResource
                  ? graphData.nodes.find((n) =>
                      n.type === 'Resource'
                      && n.resource_type === r.resource_type
                      && (n.bucket === r.bucket
                          || n.name === r.bucket
                          || n.bucket === r.name
                          || n.name === r.name))?.id
                  : `person-${r.key}`;
                const inRendered = !!candidateId
                  && graphData.nodes.some((n) => n.id === candidateId);
                const ResIcon = isResource
                  ? GRAPH_EVENT_TYPES.find((t) => t.key === r.resource_type)?.icon
                  : null;
                const resColor = isResource
                  ? GRAPH_EVENT_TYPES.find((t) => t.key === r.resource_type)?.color
                  : null;
                return (
                  <button
                    key={`${r.entity}-${r.key || r.name}-${idx}`}
                    type="button"
                    onClick={() => {
                      if (isResource) {
                        // Make sure the chip for this resource type
                        // is ON — clicking a "Meetings" search result
                        // makes no sense if Meetings is toggled off.
                        if (r.resource_type
                            && !activeEventTypes.has(r.resource_type)) {
                          setActiveEventTypes((prev) => {
                            const next = new Set(prev);
                            next.add(r.resource_type);
                            return next;
                          });
                          // The chip toggle triggers a refetch. Queue
                          // the centre-and-fan for once the new data
                          // lands — the same pending-fan ref the
                          // Person path uses, but keyed by bucket
                          // since the resource id isn't computable
                          // here without the backend's safe_bucket
                          // sanitisation. We resolve it inside the
                          // effect using (resource_type, bucket).
                          pendingResourceFanRef.current = {
                            resource_type: r.resource_type,
                            bucket: r.bucket || r.name,
                          };
                          return;
                        }
                        // Chip is already on — if the node is in the
                        // rendered set, centre + fan immediately.
                        if (candidateId) {
                          // Persist a search highlight on this id so
                          // the cyan ring + label pop appear.
                          setMultiSelection(new Set([candidateId]));
                          centreAndFan(candidateId, graphData.nodes, graphData.links);
                        } else {
                          // Not in the current rendered subgraph —
                          // queue a pending resource fan so once the
                          // chip-driven refetch lands the node gets
                          // centred.
                          pendingResourceFanRef.current = {
                            resource_type: r.resource_type,
                            bucket: r.bucket || r.name,
                          };
                        }
                        return;
                      }
                      // Person path: rebuild via perspective AND then
                      // centre+fan the result on the rebuilt graph.
                      // pendingFanRef is consumed by the graphData
                      // effect above once the rebuild arrives.
                      pendingFanRef.current = `person-${r.key}`;
                      if (perspective) {
                        perspective.setPerspective(
                          [r.key],
                          r.name || r.key,
                          'graph.search-panel',
                        );
                      } else {
                        // No perspective context — still centre + fan
                        // on the existing graph if the node's already
                        // there.
                        if (candidateId) {
                          centreAndFan(candidateId, graphData.nodes, graphData.links);
                        }
                      }
                    }}
                    className="w-full text-left px-3 py-2 border-b border-light-100 hover:bg-light-50 last:border-b-0 flex items-start gap-2"
                  >
                    {isResource && ResIcon && (
                      <ResIcon
                        className="w-3 h-3 flex-shrink-0 mt-0.5"
                        style={{ color: resColor }}
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-owl-blue-900 truncate">
                        {r.name}
                      </div>
                      <div className="text-[10px] text-light-500 truncate flex items-center gap-1">
                        {isResource ? (
                          <span className="font-mono text-light-600">
                            {GRAPH_EVENT_TYPES.find((t) => t.key === r.resource_type)?.label || r.label}
                          </span>
                        ) : (
                          r.phone && <span className="font-mono">{r.phone}</span>
                        )}
                        {!isResource && r.comm_count > 0 && (
                          <>
                            <span>·</span>
                            <span>{r.comm_count.toLocaleString()} comms</span>
                          </>
                        )}
                        {!inRendered && (
                          <>
                            <span>·</span>
                            <span className="text-amber-600">off-canvas</span>
                          </>
                        )}
                      </div>
                    </div>
                    <ChevronRight className="w-3 h-3 text-light-400 mt-0.5 flex-shrink-0" />
                  </button>
                );
              })}
            </div>
            <div className="px-3 py-1.5 border-t border-light-100 bg-light-50 text-[10px] text-light-600 flex-shrink-0">
              Click a result to anchor the graph on that Person.
            </div>
          </div>
        )}
      </div>

      {/* Hover tooltip */}
      {hoveredNode && (
        <div className="absolute bottom-4 left-4 bg-white border border-light-300 rounded-lg shadow-lg p-3 text-xs max-w-xs pointer-events-none z-10">
          <div className="font-semibold text-owl-blue-900 flex items-center gap-1.5 flex-wrap">
            <span>{hoveredNode.name}</span>
            {hoveredNode.type === 'PhoneReport' && hoveredNode.report_key && (
              <PhoneIdentityChip reportKey={hoveredNode.report_key} variant="dense" />
            )}
          </div>
          {hoveredNode.type === 'PhoneReport' && hoveredNode.phone_owner && (
            <div className="text-light-600 mt-0.5">Owner: {hoveredNode.phone_owner}</div>
          )}
          {hoveredNode.phone && (
            <div className="text-light-600 mt-0.5">Phone: {hoveredNode.phone}</div>
          )}
          {hoveredNode.device_count > 1 && (
            <div className="text-amber-600 font-medium mt-0.5">
              Appears on {hoveredNode.device_count} devices
            </div>
          )}
          {hoveredNode.comm_count > 0 && (
            <div className="text-light-500 mt-0.5">{hoveredNode.comm_count} communications</div>
          )}
          {/* Person nodes can be linked to one or several phones — show
              every phone they appear on as a chip strip. */}
          {hoveredNode.type !== 'PhoneReport' && (
            (() => {
              const keys = Array.isArray(hoveredNode.report_keys)
                ? hoveredNode.report_keys
                : (hoveredNode.report_key ? [hoveredNode.report_key] : []);
              if (keys.length === 0) return null;
              return (
                <div className="mt-1 flex items-center gap-1 flex-wrap">
                  <span className="text-light-500">On:</span>
                  {keys.map((rk) => (
                    <PhoneIdentityChip key={rk} reportKey={rk} variant="dense" />
                  ))}
                </div>
              );
            })()
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Build a selection-rail payload for a graph node.
 *
 * The rail expects a `type` (used to pick the accordion renderer) and
 * a `payload.node_key` for the rail's GET /events/detail/{key} call.
 * Person nodes have a Cellebrite Person key under `n.id` = `person-{key}`.
 * PhoneReport nodes have a report_key. Resource nodes don't have a
 * single canonical lookup — we pass enough metadata that a future
 * Resource-aware accordion can render bucket + hits + phone count.
 */
function buildNodePayload(node, links) {
  if (!node) return null;
  if (node.type === 'PhoneReport') {
    return {
      kind: 'phone-report',
      type: 'phone-report',
      id: node.id,
      reportKey: node.report_key,
      node_key: node.report_key,
      name: node.name,
      device_model: node.name,
      phone_owner: node.phone_owner,
    };
  }
  if (node.type === 'Resource') {
    // Count incoming Phone→Resource edges so the rail can display
    // "owned by N phones" + list edge counterparts.
    const incomingPhones = [];
    for (const l of (links || [])) {
      const s = typeof l.source === 'object' ? l.source.id : l.source;
      const t = typeof l.target === 'object' ? l.target.id : l.target;
      if (t === node.id && typeof s === 'string' && s.startsWith('report-')) {
        incomingPhones.push(s.replace(/^report-/, ''));
      }
    }
    return {
      kind: 'resource',
      type: 'resource',
      id: node.id,
      node_key: node.id,
      resource_type: node.resource_type,
      bucket: node.bucket,
      name: node.name,
      hits: node.hits,
      phone_count: node.phone_count,
      phone_report_keys: incomingPhones,
    };
  }
  // Person
  const personKey = String(node.id || '').replace(/^person-/, '');
  return {
    kind: 'person',
    type: 'person',
    id: node.id,
    node_key: personKey,
    person_key: personKey,
    reportKey: node.report_key || node.cellebrite_report_key || null,
    report_key: node.report_key || node.cellebrite_report_key || null,
    name: node.name,
    phone: node.phone,
    device_count: node.device_count,
    comm_count: node.comm_count,
    shared: node.shared,
  };
}

/**
 * Small pivot button shown in the perspective banner. Uniform sizing
 * so the row reads as a single control strip rather than ad-hoc
 * buttons.
 */
function PivotBtn({ icon: Icon, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={`View this perspective in the ${label} tab`}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-amber-300 bg-white hover:bg-amber-100 text-amber-900 text-[10px]"
    >
      <Icon className="w-2.5 h-2.5" />
      {label}
    </button>
  );
}
