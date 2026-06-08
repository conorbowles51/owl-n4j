import React, { useEffect, useMemo, useState } from 'react';
import { Phone, MessageSquare, Mail, ArrowRight, X, Loader2, Share2 } from 'lucide-react';
import { graphAPI, cellebriteCommsAPI } from '../../../services/api';
import { formatTs } from '../events/eventUtils';
import { useCellebriteSelection } from './CellebriteSelectionContext';

/**
 * Path Flow — multi-hop shortest-path event flow between TWO people.
 *
 * The investigator picks exactly two Person nodes in the Cross-Phone
 * Graph; this panel asks the backend for the shortest path between them
 * and then, for each consecutive Person→Person hop ALONG that path,
 * fetches the actual calls / messages / emails exchanged and renders
 * them chronologically. The question it answers: "how did contact flow
 * from A to B, and what was said at each step."
 *
 * Props:
 *   - caseId : string
 *   - aKey   : string  start person key — `phone-...` form, `person-`
 *                      prefix already stripped by the caller.
 *   - bKey   : string  end person key — same form.
 *   - aName  : string  display name for A
 *   - bName  : string  display name for B
 *   - open   : bool
 *   - onClose: () => void
 *
 * ── Path-ordering logic (the tricky part) ───────────────────────────
 * The shortest-paths endpoint returns { nodes, links } where each link
 * is { source, target, type, ... } keyed by node `key` (NOT `id`). The
 * backend uses an UNDIRECTED `shortestPath((a)-[*]-(b))`, so a link's
 * source/target reflect the STORED relationship direction, not the walk
 * direction. We therefore treat the links as an UNDIRECTED adjacency
 * map and BFS from aKey to bKey to recover the ordered key sequence
 * a → … → b (shortest walk = the path the backend found). Mapping those
 * keys back to node objects gives us each node's `type` and `name`.
 *
 * Persons (type === 'Person') are the hop endpoints. Any non-person
 * node sitting BETWEEN two consecutive persons (e.g. a shared
 * "Chat (Facebook Messenger)") is surfaced as a small "via …" connector
 * label on that hop. Limitation: if multiple shortest paths of equal
 * length exist, BFS returns one of them (the first discovered); and if
 * the endpoints are not connected within max_depth the path is empty.
 * Both cases are reported honestly in the UI.
 */

const COMM_TYPES = ['message', 'call', 'email'];
const MAX_HOPS = 8;            // cap person→person hops we render
const PER_HOP_LIMIT = 50;      // cap events fetched per hop per direction

const ICON_FOR_TYPE = {
  call: Phone,
  message: MessageSquare,
  email: Mail,
};

export default function PathFlowPanel({
  caseId,
  aKey,
  bKey,
  aName,
  bName,
  open = false,
  onClose,
}) {
  const { selectEntity } = useCellebriteSelection();

  // Raw shortest-path subgraph.
  const [pathData, setPathData] = useState(null);
  const [pathLoading, setPathLoading] = useState(false);
  const [pathError, setPathError] = useState(null);

  // Fetch the shortest path on open / key change. Never while closed.
  useEffect(() => {
    if (!open || !caseId || !aKey || !bKey) {
      setPathData(null);
      return undefined;
    }
    let cancelled = false;
    setPathLoading(true);
    setPathError(null);
    setPathData(null);
    graphAPI
      .getShortestPaths(caseId, [aKey, bKey], 10)
      .then((res) => {
        if (cancelled) return;
        setPathData(res || { nodes: [], links: [] });
        setPathLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setPathError(err?.message || 'Failed to find a path');
        setPathData(null);
        setPathLoading(false);
      });
    return () => { cancelled = true; };
  }, [open, caseId, aKey, bKey]);

  // Esc closes while open — mirrors SubgraphEventStream.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // Reconstruct the ordered node sequence a → … → b from the links.
  // Returns { ordered, persons, hops } or null when no path.
  const path = useMemo(() => {
    if (!pathData || !Array.isArray(pathData.nodes) || pathData.nodes.length === 0) {
      return null;
    }
    return reconstructPath(pathData, aKey, bKey);
  }, [pathData, aKey, bKey]);

  if (!open) return null;

  const hopCount = path?.hops?.length || 0;

  return (
    <aside
      className="fixed top-0 right-0 bottom-0 w-[460px] max-w-[92vw] bg-white border-l border-light-200 shadow-2xl z-30 flex flex-col animate-pathflow-slide"
      role="complementary"
      aria-label="Path flow between two people"
      onClick={(e) => e.stopPropagation()}
    >
      <style>{`
        @keyframes pathflow-slide-in { from { transform: translateX(100%); } to { transform: translateX(0); } }
        .animate-pathflow-slide { animation: pathflow-slide-in 220ms cubic-bezier(0.22, 0.61, 0.36, 1); }
      `}</style>

      {/* Header */}
      <div className="flex items-start gap-2 px-3 py-2.5 border-b border-light-200 bg-light-50 flex-shrink-0">
        <Share2 className="w-4 h-4 text-owl-blue-700 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-semibold text-owl-blue-900 flex items-center gap-1.5 flex-wrap">
            <span className="truncate" title={aName}>{aName}</span>
            <ArrowRight className="w-3 h-3 text-light-400 flex-shrink-0" />
            <span className="truncate" title={bName}>{bName}</span>
          </div>
          <div className="mt-0.5 text-[11px] text-light-600">
            {pathLoading
              ? 'Finding shortest path…'
              : path
                ? `Shortest path · ${hopCount} hop${hopCount === 1 ? '' : 's'}`
                : 'Path flow'}
          </div>
        </div>
        <button
          type="button"
          onClick={() => onClose?.()}
          className="p-1 text-light-400 hover:text-light-700 rounded flex-shrink-0"
          title="Close (Esc)"
          aria-label="Close path flow"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto px-2 py-2">
        {pathLoading && (
          <div className="flex items-center gap-2 px-1 py-6 text-xs text-light-500 italic">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Finding the shortest path…
          </div>
        )}
        {!pathLoading && pathError && (
          <div className="px-1 py-6 text-xs text-red-600">{pathError}</div>
        )}
        {!pathLoading && !pathError && !path && (
          <div className="px-1 py-6 text-xs text-light-500 italic">
            No connecting path within 10 hops between {aName} and {bName}.
          </div>
        )}
        {!pathLoading && !pathError && path && path.hops.length === 0 && (
          <div className="px-1 py-6 text-xs text-light-500 italic">
            {aName} and {bName} resolve to the same person — no hop to trace.
          </div>
        )}
        {!pathLoading && !pathError && path && path.hops.length > 0 && (
          <>
            {/* Path overview — ordered chips for the whole walk */}
            <PathOverview ordered={path.ordered} />
            {path.truncated && (
              <div className="mb-2 px-1 text-[10px] text-amber-600">
                Long path — showing the first {MAX_HOPS} person-to-person hops.
              </div>
            )}
            <ol className="space-y-3">
              {path.hops.slice(0, MAX_HOPS).map((hop, idx) => (
                <HopSection
                  key={`${hop.from.key}-${hop.to.key}-${idx}`}
                  caseId={caseId}
                  hop={hop}
                  index={idx + 1}
                  onSelectItem={(it) => publishItem(selectEntity, it, caseId)}
                />
              ))}
            </ol>
          </>
        )}
      </div>
    </aside>
  );
}

/* ────────────────────── Path ordering ────────────────────── */

/**
 * Reconstruct the ordered path a → … → b from the shortest-path
 * subgraph. See the file header for the rationale.
 *
 * Returns:
 *   {
 *     ordered : [{ key, name, type, isPerson }]  full node walk a→b
 *     persons : [{ key, name, type }]            person nodes in order
 *     hops    : [{ from, to, via:[node…] }]      consecutive person pairs
 *     truncated : bool                           > MAX_HOPS person hops
 *   }
 * or null when a→b can't be walked from the links.
 */
function reconstructPath(pathData, aKey, bKey) {
  const nodeByKey = new Map();
  for (const n of pathData.nodes || []) {
    if (n && n.key != null) nodeByKey.set(String(n.key), n);
  }
  // Undirected adjacency keyed by node key.
  const adj = new Map();
  const addEdge = (u, v) => {
    if (!adj.has(u)) adj.set(u, new Set());
    adj.get(u).add(v);
  };
  for (const l of pathData.links || []) {
    const s = l?.source != null ? String(l.source) : null;
    const t = l?.target != null ? String(l.target) : null;
    if (!s || !t) continue;
    addEdge(s, t);
    addEdge(t, s);
  }

  const start = String(aKey);
  const goal = String(bKey);

  // Degenerate: A and B are the same node.
  if (start === goal) {
    const node = toNode(nodeByKey, start);
    return { ordered: [node], persons: [node], hops: [], truncated: false };
  }

  // BFS for the shortest walk start → goal over the undirected adjacency.
  const orderedKeys = bfsPath(adj, start, goal);
  if (!orderedKeys) return null;

  const ordered = orderedKeys.map((k) => toNode(nodeByKey, k));

  // Partition the ordered walk into person hops. Persons are hop
  // endpoints; any run of non-person nodes between two persons is the
  // hop's "via" connector list.
  const persons = ordered.filter((n) => n.isPerson);
  const hops = [];
  let pendingVia = [];
  let prevPerson = null;
  for (const node of ordered) {
    if (node.isPerson) {
      if (prevPerson) {
        hops.push({ from: prevPerson, to: node, via: pendingVia });
      }
      prevPerson = node;
      pendingVia = [];
    } else if (prevPerson) {
      // Only collect intermediaries once we've passed the first person.
      pendingVia.push(node);
    }
  }

  return {
    ordered,
    persons,
    hops,
    truncated: hops.length > MAX_HOPS,
  };
}

/** Map a key to a normalised node descriptor (falls back gracefully). */
function toNode(nodeByKey, key) {
  const n = nodeByKey.get(key);
  const type = n?.type || 'Unknown';
  return {
    key,
    name: n?.name || key,
    type,
    isPerson: type === 'Person',
  };
}

/** Breadth-first shortest walk from start to goal. Returns key[] or null. */
function bfsPath(adj, start, goal) {
  if (!adj.has(start)) return null;
  const prev = new Map();
  const visited = new Set([start]);
  const queue = [start];
  while (queue.length) {
    const cur = queue.shift();
    if (cur === goal) break;
    const neighbours = adj.get(cur);
    if (!neighbours) continue;
    for (const nxt of neighbours) {
      if (visited.has(nxt)) continue;
      visited.add(nxt);
      prev.set(nxt, cur);
      queue.push(nxt);
    }
  }
  if (!visited.has(goal)) return null;
  const out = [goal];
  let cur = goal;
  while (cur !== start) {
    const p = prev.get(cur);
    if (p == null) return null; // disconnected — shouldn't happen post-visit
    out.push(p);
    cur = p;
  }
  out.reverse();
  return out;
}

/* ────────────────────── Sub-components ────────────────────── */

/** Compact ordered chip row for the whole walk a → … → b. */
function PathOverview({ ordered }) {
  return (
    <div className="mb-3 px-1 py-2 rounded-lg bg-light-50 border border-light-200">
      <div className="flex items-center gap-1 flex-wrap text-[11px]">
        {ordered.map((n, i) => (
          <React.Fragment key={`${n.key}-${i}`}>
            <span
              className={`px-1.5 py-0.5 rounded truncate max-w-[140px] ${
                n.isPerson
                  ? 'bg-owl-blue-50 text-owl-blue-900 font-medium border border-owl-blue-100'
                  : 'bg-light-100 text-light-600 border border-light-200'
              }`}
              title={`${n.name} (${n.type})`}
            >
              {n.name}
            </span>
            {i < ordered.length - 1 && (
              <ArrowRight className="w-2.5 h-2.5 text-light-400 flex-shrink-0" />
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

/**
 * A single Person→Person hop: the directed back-and-forth comms between
 * the two parties, fetched with the SAME two-directed-call merge pattern
 * GraphEdgeAccordion uses (PR #71 fix), shown chronologically.
 */
function HopSection({ caseId, hop, index, onSelectItem }) {
  const { from, to, via } = hop;
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!caseId || !from?.key || !to?.key) {
      setItems([]);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Two DIRECTED getBetween calls (a→b and b→a), merged + de-duped +
    // sorted ascending — the exact pattern from GraphEdgeAccordion.
    Promise.all([
      cellebriteCommsAPI.getBetween(caseId, {
        fromKeys: [from.key], toKeys: [to.key], types: COMM_TYPES, limit: PER_HOP_LIMIT, sort: 'asc',
      }),
      cellebriteCommsAPI.getBetween(caseId, {
        fromKeys: [to.key], toKeys: [from.key], types: COMM_TYPES, limit: PER_HOP_LIMIT, sort: 'asc',
      }),
    ])
      .then(([abRes, baRes]) => {
        if (cancelled) return;
        const merged = [...(abRes?.items || []), ...(baRes?.items || [])];
        const seen = new Set();
        const deduped = [];
        for (const it of merged) {
          const k = it?.id || `${it?.type}-${it?.timestamp}-${it?.sender?.key}`;
          if (seen.has(k)) continue;
          seen.add(k);
          deduped.push(it);
        }
        deduped.sort((x, y) => {
          const tx = x?.timestamp ? new Date(x.timestamp).getTime() : 0;
          const ty = y?.timestamp ? new Date(y.timestamp).getTime() : 0;
          return tx - ty;
        });
        setItems(deduped);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'Failed to load comms for this hop');
        setItems([]);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [caseId, from?.key, to?.key]);

  return (
    <li className="rounded-lg border border-light-200 overflow-hidden">
      {/* Hop header */}
      <div className="px-2.5 py-1.5 bg-light-50 border-b border-light-200">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold text-owl-blue-900">
          <span className="font-mono text-[10px] text-light-400">#{index}</span>
          <span className="truncate max-w-[150px]" title={from.name}>{from.name}</span>
          <ArrowRight className="w-3 h-3 text-light-400 flex-shrink-0" />
          <span className="truncate max-w-[150px]" title={to.name}>{to.name}</span>
        </div>
        {Array.isArray(via) && via.length > 0 && (
          <div className="mt-0.5 text-[10px] text-light-500">
            via {via.map((v) => v.name).join(' · ')}
          </div>
        )}
      </div>

      {/* Hop comms */}
      <div className="px-2 py-2">
        {loading && (
          <div className="px-1 py-2 text-[11px] text-light-500 italic flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 animate-spin" />
            Loading comms…
          </div>
        )}
        {!loading && error && (
          <div className="px-1 py-2 text-[11px] text-red-600">{error}</div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="px-1 py-2 text-[11px] text-light-500 italic">
            No direct calls, messages, or emails on this hop
            {Array.isArray(via) && via.length > 0
              ? ' — the two are linked only through the connector above.'
              : '.'}
          </div>
        )}
        {!loading && !error && items.length > 0 && (
          <ul className="space-y-1.5">
            {items.map((it, idx) => (
              <HopEventRow
                key={it.id || `${it.type}-${it.timestamp}-${idx}`}
                item={it}
                seq={idx + 1}
                fromKey={from.key}
                onSelect={() => onSelectItem(it)}
              />
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

/** One comms row inside a hop — mirrors GraphEdgeAccordion.EdgeEventRow. */
function HopEventRow({ item, seq, fromKey, onSelect }) {
  const Icon = ICON_FOR_TYPE[item.type] || MessageSquare;
  const fromName = item?.sender?.name || item?.sender?.key || 'Unknown';
  const toName = (Array.isArray(item?.recipients) && item.recipients[0]?.name)
    || (Array.isArray(item?.recipients) && item.recipients[0]?.key)
    || 'Unknown';
  const when = item?.timestamp ? formatTs(item.timestamp) : '';
  const body = (item?.body || '').trim();
  // Direction relative to the hop's "from" party: from→ on the left
  // tinted blue, →from on the right tinted slate, so a hop reads as a
  // back-and-forth flow.
  const fromA = item?.sender?.key === fromKey;
  const dur = item?.duration || item?.call_duration || null;

  return (
    <li className={`flex ${fromA ? 'justify-start' : 'justify-end'}`}>
      <button
        type="button"
        onClick={onSelect}
        className={`text-left rounded-lg px-2.5 py-1.5 max-w-[88%] border hover:brightness-95 ${
          fromA
            ? 'bg-owl-blue-50 border-owl-blue-100'
            : 'bg-light-100 border-light-200'
        }`}
      >
        <div className="flex items-center gap-1.5 text-[10px] text-light-500">
          <span className="font-mono text-light-400">#{seq}</span>
          <Icon className="w-3 h-3 flex-shrink-0" />
          <span className="font-medium text-light-700 truncate max-w-[80px]" title={fromName}>{fromName}</span>
          <ArrowRight className="w-2.5 h-2.5 text-light-400 flex-shrink-0" />
          <span className="truncate max-w-[80px]" title={toName}>{toName}</span>
          {when && <span className="ml-auto whitespace-nowrap pl-1.5">{when}</span>}
        </div>
        {item.type === 'message' && body && (
          <div className="mt-0.5 text-[12px] text-owl-blue-900 break-words line-clamp-4">
            {body}
          </div>
        )}
        {item.type === 'email' && (item.subject || body) && (
          <div className="mt-0.5 text-[12px] text-owl-blue-900 break-words">
            {item.subject && <span className="font-semibold">{item.subject}</span>}
            {item.subject && body && <span className="text-light-400"> — </span>}
            {body && <span className="line-clamp-3">{body}</span>}
          </div>
        )}
        {item.type === 'call' && (
          <div className="mt-0.5 text-[12px] text-owl-blue-900">
            {item.call_type ? `${item.call_type} call` : 'Call'}
            {dur ? <span className="text-light-500"> · {dur}</span> : null}
          </div>
        )}
        {(item.source_app || (Array.isArray(item.attachments) && item.attachments.length > 0)) && (
          <div className="mt-0.5 text-[10px] text-light-500 flex items-center gap-1.5 flex-wrap">
            {item.source_app && <span>{item.source_app}</span>}
            {item.source_app && Array.isArray(item.attachments) && item.attachments.length > 0 && <span>·</span>}
            {Array.isArray(item.attachments) && item.attachments.length > 0 && (
              <span>{item.attachments.length} attachment{item.attachments.length > 1 ? 's' : ''}</span>
            )}
          </div>
        )}
      </button>
    </li>
  );
}

/* ────────────────────── Helpers ────────────────────── */

/**
 * Re-publish a single comms item as its own typed selection so the rail
 * hops to the EventAccordion — identical hand-off to GraphEdgeAccordion
 * and SubgraphEventStream so a row opens full detail.
 */
function publishItem(selectEntity, item, caseId) {
  if (!selectEntity || !item?.id) return;
  const type = item.type === 'call' ? 'call'
    : item.type === 'email' ? 'email'
    : 'message';
  selectEntity({
    type,
    id: item.id,
    caseId,
    reportKey: item.report_key || item.cellebrite_report_key || null,
    payload: {
      ...item,
      node_key: item.id,
      event_type: item.type,
    },
    source: 'graph.path-flow.item',
  });
}
