import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import {
  Loader2, ZoomIn, ZoomOut, Maximize2,
  Phone, MessageSquare, Mail, MapPin, Wifi, Radio, Users as UsersIcon, X,
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

// Available edge types — defaults match the backend's legacy comms-only
// behaviour. Persisted per case in localStorage via the toggle bar below.
const GRAPH_EVENT_TYPES = [
  { key: 'call',       label: 'Calls',     icon: Phone,         color: '#10b981', defaultOn: true  },
  { key: 'message',    label: 'Messages',  icon: MessageSquare, color: '#2563eb', defaultOn: true  },
  { key: 'email',      label: 'Emails',    icon: Mail,          color: '#f59e0b', defaultOn: true  },
  { key: 'location',   label: 'Locations', icon: MapPin,        color: '#06b6d4', defaultOn: false },
  { key: 'wifi',       label: 'WiFi',      icon: Wifi,          color: '#10b981', defaultOn: false },
  { key: 'cell_tower', label: 'Cell',      icon: Radio,         color: '#8b5cf6', defaultOn: false },
  { key: 'meeting',    label: 'Meetings',  icon: UsersIcon,     color: '#f97316', defaultOn: false },
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
  const eventTypesKey = `cb.graph.eventTypes.${caseId || 'unknown'}`;
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
  // Depth toggle — 1 (anchors + direct contacts) is the safer default;
  // 2 hops off-anchor and is best for "find connections-of-connections"
  // exploration. Only meaningful when a perspective is active.
  const [depth, setDepth] = useState(1);

  const fgRef = useRef();
  const containerRef = useRef();

  // Active perspective anchors (or null = full case)
  const personKeys = useMemo(() => {
    if (!perspective?.hasPerspective) return null;
    return [...perspective.activeKeys];
  }, [perspective?.hasPerspective, perspective?.activeKeys]);

  // Camera-preservation: when the user toggles an edge type or
  // changes depth, the new graphData triggers react-force-graph-2d
  // to re-run its simulation. Without intervention the simulated
  // positions land at fresh random coords AND the user's pan/zoom
  // is lost because the nodes they were looking at have moved.
  //
  // Fix: (a) carry x/y/vx/vy from the OLD nodes onto the new ones
  // whose `id` matches — so unchanged nodes don't budge — and
  // (b) snapshot the camera (centre + zoom) just before swapping
  // data and re-apply it once the new graph has settled.
  const lastNodePosRef = useRef(new Map());
  const cameraSnapshotRef = useRef(null);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setLoading(true);

    // Capture the current camera ONLY when we already have data
    // showing (i.e. this isn't the initial load — there's nothing
    // useful to preserve when the canvas is empty). Reading both
    // before the fetch avoids a race where the new data lands and
    // resets the camera before we sample it.
    if (fgRef.current && graphData.nodes.length > 0) {
      try {
        const centre = fgRef.current.centerAt();
        const z = fgRef.current.zoom();
        if (centre && Number.isFinite(centre.x) && Number.isFinite(centre.y)) {
          cameraSnapshotRef.current = { x: centre.x, y: centre.y, z };
        }
      } catch {
        // centerAt/zoom can throw before the canvas has a size — skip
        cameraSnapshotRef.current = null;
      }
    }

    cellebriteAPI.getCrossPhoneGraph(caseId, {
      personKeys: personKeys || undefined,
      eventTypes: [...activeEventTypes],
      depth,
    }).then(data => {
      if (cancelled) return;
      const next = data || { nodes: [], links: [] };

      // Stitch previous {x, y, vx, vy} onto the new nodes so the
      // simulation starts from the user's existing layout instead of
      // a fresh random seed. Library treats x/y already-present on a
      // node as a placement hint, not a hard pin, so the sim still
      // relaxes the new edges without yanking the whole graph.
      if (lastNodePosRef.current.size > 0) {
        for (const n of next.nodes) {
          const prev = lastNodePosRef.current.get(n.id);
          if (prev) {
            n.x = prev.x;
            n.y = prev.y;
            n.vx = prev.vx || 0;
            n.vy = prev.vy || 0;
          }
        }
      }
      setGraphData(next);
      setLoading(false);
    }).catch(() => {
      if (!cancelled) {
        setGraphData({ nodes: [], links: [] });
        setLoading(false);
      }
    });

    return () => { cancelled = true; };
  }, [caseId, personKeys, activeEventTypes, depth]);

  // Maintain the position cache from whatever's currently on screen.
  // Effect runs after every render, so by the time the user toggles
  // a filter the latest positions are already captured.
  useEffect(() => {
    const m = lastNodePosRef.current;
    for (const n of graphData.nodes) {
      if (n.id == null) continue;
      if (Number.isFinite(n.x) && Number.isFinite(n.y)) {
        m.set(n.id, { x: n.x, y: n.y, vx: n.vx, vy: n.vy });
      }
    }
  });

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

  // Free-text filter — each whitespace-separated term must match
  // SOMEWHERE in the node's full haystack. Quoted "exact phrases" are
  // kept intact. Same friendly tokenisation parseQuery uses for the
  // event/thread surfaces, but applied as plain substring (the graph
  // doesn't have a meaningful schema for from:/to:/app: operators).
  const filteredData = useMemo(() => {
    const raw = (searchTerm || '').trim();
    if (!raw) return graphData;

    const terms = tokeniseGraphSearch(raw);
    if (terms.length === 0) return graphData;

    const matchesHaystack = (h) => terms.every((t) => h.includes(t));

    const matchingNodeIds = new Set();
    for (const n of graphData.nodes) {
      if (matchesHaystack(haystackByNodeId.get(n.id) || '')) {
        matchingNodeIds.add(n.id);
      }
    }

    // Include any node connected by a link whose label/count itself
    // matches (so "calls" surfaces the call edges + both endpoints).
    graphData.links.forEach((l, i) => {
      const linkHay = haystackByLink.get(i) || '';
      const srcId = typeof l.source === 'object' ? l.source.id : l.source;
      const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
      if (matchesHaystack(linkHay)) {
        matchingNodeIds.add(srcId);
        matchingNodeIds.add(tgtId);
      }
    });

    // Include the immediate neighbours of every matched node so the
    // result remains a navigable subgraph — searching "Lemus" returns
    // Lemus AND the people connected to Lemus, not Lemus floating
    // alone.
    const neighbourIds = new Set(matchingNodeIds);
    graphData.links.forEach((l) => {
      const srcId = typeof l.source === 'object' ? l.source.id : l.source;
      const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
      if (matchingNodeIds.has(srcId)) neighbourIds.add(tgtId);
      if (matchingNodeIds.has(tgtId)) neighbourIds.add(srcId);
    });

    return {
      nodes: graphData.nodes.filter((n) => neighbourIds.has(n.id)),
      links: graphData.links.filter((l) => {
        const srcId = typeof l.source === 'object' ? l.source.id : l.source;
        const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
        return neighbourIds.has(srcId) && neighbourIds.has(tgtId);
      }),
    };
  }, [graphData, searchTerm, haystackByNodeId, haystackByLink]);

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

  const paintNode = useCallback((node, ctx, globalScale) => {
    const isReport = node.type === 'PhoneReport';
    const isShared = node.shared;

    // Phone identity colour: a PhoneReport node IS a phone, so it uses
    // its own report_key. A Person node carries one (or more) report_keys
    // depending on whether they appear on one or multiple phones.
    const phoneKey = node.report_key || node.cellebrite_report_key;
    const phoneIdentity = phoneCtx && phoneKey
      ? phoneCtx.getIdentityByKey(phoneKey)
      : null;

    // PhoneReport: fill with the phone's persistent palette colour so it
    // matches every chip / stripe / map ring elsewhere in the app.
    // Person: keep the existing semantic colours (default vs shared) but
    // add a coloured ring in the phone's identity colour to show which
    // phone owns the contact.
    const fillColor = isReport && phoneIdentity
      ? phoneIdentity.hex
      : isReport
      ? NODE_COLORS.PhoneReport
      : isShared
      ? NODE_COLORS.PersonShared
      : NODE_COLORS.Person;

    const r = isReport ? 8 : 4 + Math.min(node.comm_count || 0, 10) * 0.3;

    // Phone identity ring on Person nodes (non-report). Drawn first so
    // the node fill sits inside it.
    if (!isReport && phoneIdentity) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI);
      ctx.fillStyle = phoneIdentity.hex;
      ctx.fill();
    }

    // Draw node
    ctx.beginPath();
    if (isReport) {
      const size = r * 2;
      ctx.roundRect(node.x - r, node.y - r, size, size, 3);
    } else {
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    }
    ctx.fillStyle = fillColor;
    ctx.fill();

    if (isShared) {
      ctx.strokeStyle = '#d97706';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // Per-edge-type indicator dots — one small coloured satellite
    // per active edge type the node participates in. Placed evenly
    // around the upper hemisphere so the dots stay legible even
    // when the underlying node fill is monochrome.
    if (!isReport) {
      const edgeTypes = nodeEdgeTypes.get(node.id);
      if (edgeTypes && edgeTypes.size > 0) {
        // Stable order so the dots don't reshuffle on every paint
        // (Set iteration would be insertion-order anyway, but sort
        // by event-type-key for predictability across re-renders).
        const types = [...edgeTypes].sort();
        const dotR = Math.max(1.2, r * 0.35);
        const orbit = r + dotR + 0.5;
        const total = types.length;
        // Spread evenly across the top semicircle (−135° → −45°)
        const spanStart = -Math.PI * 0.75;
        const spanEnd = -Math.PI * 0.25;
        for (let i = 0; i < total; i++) {
          const t = total === 1
            ? (spanStart + spanEnd) / 2
            : spanStart + ((spanEnd - spanStart) * i) / (total - 1);
          const cx = node.x + orbit * Math.cos(t);
          const cy = node.y + orbit * Math.sin(t);
          ctx.beginPath();
          ctx.arc(cx, cy, dotR, 0, 2 * Math.PI);
          ctx.fillStyle = edgeColorByType.get(types[i]) || '#94a3b8';
          ctx.fill();
          // 1px white halo so the dot reads off any background.
          ctx.lineWidth = Math.max(0.25, 0.6 / globalScale);
          ctx.strokeStyle = '#ffffff';
          ctx.stroke();
        }
      }
    }

    // Label
    const fontSize = isReport ? 11 / globalScale : 9 / globalScale;
    ctx.font = `${isReport ? 'bold ' : ''}${fontSize}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = '#334155';
    let label = (node.name || '').substring(0, 20);
    if (isReport && phoneIdentity) {
      label = `${phoneIdentity.short} · ${label}`;
    }
    ctx.fillText(label, node.x, node.y + r + 2 / globalScale);
  }, [phoneCtx, nodeEdgeTypes, edgeColorByType]);

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
        <div className="flex-1 max-w-xl">
          {/* Full-text search across every visible string on every
              node + edge — name, phone, owner, device model, phone
              identity short label, edge label, edge count, "shared".
              Matched nodes' immediate neighbours are kept so the
              result stays a navigable subgraph. */}
          <CellebriteSearchInput
            value={searchTerm}
            onChange={setSearchTerm}
            placeholder='Search the graph — name, phone, app, device, "exact phrase"…'
            matchCount={filteredData.nodes.length}
            totalCount={graphData.nodes.length}
            itemNoun="node"
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
        <div className="text-xs text-light-500 ml-2">
          {filteredData.nodes.length} nodes, {filteredData.links.length} links
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 py-1.5 border-b border-light-100 text-xs text-light-600 flex-shrink-0 flex-wrap">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full" style={{ backgroundColor: NODE_COLORS.Person }} />
          Contact
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full border-2 border-amber-500" style={{ backgroundColor: NODE_COLORS.PersonShared }} />
          Shared Contact
        </span>

        {/* Edge-type swatches — only the ACTIVE event types so the
            legend mirrors what the user can actually see. The chip
            strip below still shows ALL types (active + inactive); this
            strip is the read-side key. */}
        <span className="h-4 w-px bg-light-300" />
        <span className="text-light-500 font-medium">Edges:</span>
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
          Calls/messages/emails on by default; locations/wifi/cell/meetings
          available as opt-ins because they create dense edges fast. */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-light-100 bg-light-50 text-xs flex-shrink-0 flex-wrap">
        <span className="text-light-500 font-medium">Show edges:</span>
        {GRAPH_EVENT_TYPES.map((t) => {
          const Icon = t.icon;
          const on = activeEventTypes.has(t.key);
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
              }`}
              title={`Toggle ${t.label} edges`}
            >
              <Icon className="w-3 h-3" style={{ color: on ? t.color : undefined }} />
              {t.label}
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
      <div className="flex-1 min-h-0">
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
          // Once the simulation settles after a refetch, restore the
          // camera the user was looking at. cameraSnapshotRef is only
          // populated when there WAS a prior view to preserve, so the
          // initial load is unaffected — it still auto-fits via the
          // library's default first-render behaviour.
          onEngineStop={() => {
            const snap = cameraSnapshotRef.current;
            if (!snap || !fgRef.current) return;
            try {
              fgRef.current.centerAt(snap.x, snap.y, 0);
              fgRef.current.zoom(snap.z, 0);
            } catch {
              /* ref not ready yet — skip silently */
            }
            cameraSnapshotRef.current = null;
          }}
        />
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
