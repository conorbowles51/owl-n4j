import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import {
  Loader2, ZoomIn, ZoomOut, Maximize2,
  Phone, MessageSquare, Mail, MapPin, Wifi, Radio, Users as UsersIcon, X,
  Globe, Search as SearchIcon, Bookmark, Key, ShieldCheck, DollarSign,
  Bluetooth, Filter as FilterIcon, ChevronRight,
} from 'lucide-react';
import { cellebriteAPI } from '../../services/api';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import { usePerspective } from '../../context/PerspectiveContext';
import PhoneIdentityChip from './shared/PhoneIdentityChip';
import CellebriteSearchInput from './shared/CellebriteSearchInput';

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
  // Comms — on by default
  { key: 'call',       label: 'Calls',       icon: Phone,         color: '#10b981', defaultOn: true,  group: 'comms' },
  { key: 'message',    label: 'Messages',    icon: MessageSquare, color: '#2563eb', defaultOn: true,  group: 'comms' },
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

  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [hoveredNode, setHoveredNode] = useState(null);
  // Per-case localStorage so the user's preferred event-type toggle
  // state persists across visits. Keyed off case so different cases
  // don't bleed settings.
  // localStorage key bumped to v2 when toggle semantics changed from
  // "show/hide edges among an unchanging Person set" to "add/remove
  // Persons + Resources entirely". The old v1 selections (which were
  // mostly "all on" after the previous default-on rollout) would map
  // to a hairball under the new semantics — invalidating the cache
  // keeps the new default (calls + messages only) for everyone on
  // first open.
  const eventTypesKey = `cb.graph.eventTypes.v2.${caseId || 'unknown'}`;
  const [activeEventTypes, setActiveEventTypes] = useState(() => {
    if (typeof window === 'undefined') {
      return new Set(GRAPH_EVENT_TYPES.filter(t => t.defaultOn).map(t => t.key));
    }
    try {
      const raw = window.localStorage.getItem(eventTypesKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) return new Set(parsed);
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
  // Depth toggle — 1 (anchors + direct contacts) is the safer default;
  // 2 hops off-anchor and is best for "find connections-of-connections"
  // exploration. Only meaningful when a perspective is active.
  const [depth, setDepth] = useState(1);

  const fgRef = useRef();
  const containerRef = useRef();

  // Total Persons in the case (pre 200-cap). Surfaced by the
  // backend so the UI can show "200 of N" and offer search when N
  // exceeds the rendered set.
  const [totalPersons, setTotalPersons] = useState(0);

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
      setLoading(false);
    }).catch(() => {
      if (!cancelled) {
        setGraphData({ nodes: [], links: [] });
        setTotalPersons(0);
        setEdgeCountsByType({});
        setLoading(false);
      }
    });

    return () => { cancelled = true; };
    // graphData intentionally omitted — we read it inside but only
    // care about the moment-of-call snapshot; re-firing on every
    // graphData mutation would cause an infinite loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, personKeys, depth, [...activeEventTypes].sort().join(',')]);

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

    // PhoneReport: unchanged rounded-square in phone colour.
    if (isReport) {
      const r = 8;
      ctx.beginPath();
      const size = r * 2;
      ctx.roundRect(node.x - r, node.y - r, size, size, 3);
      ctx.fillStyle = phoneIdentity ? phoneIdentity.hex : NODE_COLORS.PhoneReport;
      ctx.fill();

      const fontSize = 11 / globalScale;
      ctx.font = `bold ${fontSize}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = '#334155';
      let label = (node.name || '').substring(0, 20);
      if (phoneIdentity) label = `${phoneIdentity.short} · ${label}`;
      ctx.fillText(label, node.x, node.y + r + 2 / globalScale);
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

      // Label — only render when zoomed in enough so dense resource
      // clusters don't turn into a wall of text.
      if (globalScale > 1.2) {
        const fontSize = 8 / globalScale;
        ctx.font = `${fontSize}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = '#475569';
        const label = (node.name || '').substring(0, 22);
        ctx.fillText(label, node.x, node.y + r + 2 / globalScale);
      }
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

    // Label
    const fontSize = 9 / globalScale;
    ctx.font = `${fontSize}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = '#334155';
    const label = (node.name || '').substring(0, 20);
    ctx.fillText(label, node.x, node.y + rOuter + 2 / globalScale);
  }, [phoneCtx, nodeEdgeTypes, edgeColorByType, searchHighlightIds]);

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
        {/* N-of-M counter — surfaces the 200-cap so the user knows
            when there's more case data than the canvas can show. */}
        <div className="text-xs text-light-500 ml-2 whitespace-nowrap">
          {filteredData.nodes.length} of {totalPersons > 0 ? totalPersons.toLocaleString() : graphData.nodes.length} nodes
          {totalPersons > graphData.nodes.length && (
            <span className="ml-1 text-amber-600 font-medium" title={`Render capped at ${graphData.nodes.length}; switch to Search mode to find Persons outside the rendered subset.`}>
              · capped
            </span>
          )}
          {' · '}
          {filteredData.links.length} edges
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

      {/* Perspective banner — when active, signals that the graph is
          rebuilt from a subset of the case. Single-click clear. */}
      {perspective?.hasPerspective && (
        <div className="flex items-center gap-2 px-4 py-1 border-b border-amber-200 bg-amber-50 text-[11px] text-amber-900 flex-shrink-0">
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
            className="ml-auto inline-flex items-center gap-1 text-[10px] text-amber-800 hover:bg-amber-100 px-1.5 py-0.5 rounded"
            title="Clear perspective and show the whole case"
          >
            <X className="w-2.5 h-2.5" />
            Show whole case
          </button>
        </div>
      )}

      {/* Graph */}
      <div className="flex-1 min-h-0 relative">
        <ForceGraph2D
          ref={fgRef}
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
          // Once the post-refetch simulation settles, restore the
          // camera the user was looking at before the toggle so they
          // never lose their place. Snapshot is only populated when
          // there was a prior view to preserve, so the initial load's
          // default fit-to-view behaviour is unaffected.
          onEngineStop={() => {
            const snap = cameraSnapshotRef.current;
            if (!snap || !fgRef.current) return;
            try {
              fgRef.current.centerAt(snap.x, snap.y, 0);
              fgRef.current.zoom(snap.z, 0);
            } catch {
              /* ref not ready yet — skip */
            }
            cameraSnapshotRef.current = null;
          }}
        />

        {/* Search results panel — overlays the canvas in Search mode.
            Lists every Person in the case matching the query (not
            just the 200 rendered). Each row clicks to anchor the
            graph on that person via the perspective context. */}
        {searchMode === 'search' && (searchTerm || '').trim() && (
          <div className="absolute top-3 right-3 w-72 max-h-[60vh] bg-white border border-light-300 shadow-lg rounded-lg overflow-hidden z-20 flex flex-col">
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
              {searchResults && searchResults.results.map((r) => {
                const inRendered = graphData.nodes.some((n) => n.id === `person-${r.key}`);
                return (
                  <button
                    key={r.key}
                    type="button"
                    onClick={() => {
                      if (perspective) {
                        perspective.setPerspective(
                          [r.key],
                          r.name || r.key,
                          'graph.search-panel',
                        );
                      }
                    }}
                    className="w-full text-left px-3 py-2 border-b border-light-100 hover:bg-light-50 last:border-b-0 flex items-start gap-2"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-owl-blue-900 truncate">
                        {r.name}
                      </div>
                      <div className="text-[10px] text-light-500 truncate flex items-center gap-1">
                        {r.phone && <span className="font-mono">{r.phone}</span>}
                        {r.comm_count > 0 && (
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
