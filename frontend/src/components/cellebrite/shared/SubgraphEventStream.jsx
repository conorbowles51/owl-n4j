import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Phone, MessageSquare, Mail, ArrowRight, X, Loader2 } from 'lucide-react';
import { cellebriteCommsAPI } from '../../../services/api';
import { formatTs } from '../events/eventUtils';
import { dayKey, getTzId } from './cellebriteTime';
import { useCellebriteSelection } from './CellebriteSelectionContext';

/**
 * Subgraph Event Stream — a single chronological feed of ALL
 * communications (calls / messages / emails) involving ANY of the
 * people currently rendered in the Cross-Phone Graph subgraph.
 *
 * This complements GraphEdgeAccordion, which shows the back-and-forth
 * for exactly ONE pair (the clicked edge). Here the investigator gets
 * one timeline that captures the whole flow across the visible people,
 * each row tagged with who → who.
 *
 * Data source: cellebriteCommsAPI.getBetween with `participantKeys`
 * (an OR involvement filter) set to every person key in the subgraph.
 * The server merges them into one chronological feed and returns
 * { items, total, next_cursor }.
 *
 * Props:
 *   - caseId      : string
 *   - personKeys  : string[]  person keys (prefix-stripped) in the subgraph
 *   - activeTypes : string[]  the graph's active edge types (from activeEventTypes)
 *   - open        : bool
 *   - onClose     : () => void
 *
 * Dock choice: RIGHT side, `fixed top-0 right-0 bottom-0 w-[440px]`,
 * z-30. The selection rail is also right-docked but at z-40 and only
 * mounts when a selection exists; the investigator opens one at a time
 * and clicking a row here publishes a selection (which raises the rail
 * above this panel). Docking left was rejected because the app sidebar
 * lives there.
 */

const COMM_TYPES = ['message', 'call', 'email'];

const ICON_FOR_TYPE = {
  call: Phone,
  message: MessageSquare,
  email: Mail,
};

export default function SubgraphEventStream({
  caseId,
  personKeys = [],
  activeTypes = [],
  open = false,
  onClose,
}) {
  const { selectEntity } = useCellebriteSelection();

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Stable, bounded participant slice (cap 200). Sorted + joined so the
  // effect only refetches when the actual SET of people changes, not on
  // every parent render (graphData.nodes is a fresh array each tick).
  const boundedKeys = useMemo(
    () => Array.from(new Set((personKeys || []).filter(Boolean))).slice(0, 200),
    [personKeys],
  );
  const keysSig = useMemo(() => [...boundedKeys].sort().join(','), [boundedKeys]);

  // Comms-only type filter derived from the graph's active edge types.
  // Fall back to all three when the active set carries none of them
  // (e.g. the user is only showing location/resource edges).
  const fetchTypes = useMemo(() => {
    const filtered = (activeTypes || []).filter((t) => COMM_TYPES.includes(t));
    return filtered.length ? filtered : COMM_TYPES;
  }, [activeTypes]);
  const typesSig = useMemo(() => [...fetchTypes].sort().join(','), [fetchTypes]);

  // Fetch on open and whenever the people / types change. Never fetch
  // while closed — the panel pays zero network cost when hidden.
  useEffect(() => {
    if (!open || !caseId || boundedKeys.length === 0) {
      setItems([]);
      setTotal(0);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    cellebriteCommsAPI
      .getBetween(caseId, {
        participantKeys: boundedKeys,
        types: fetchTypes,
        limit: 300,
        sort: 'asc',
      })
      .then((res) => {
        if (cancelled) return;
        const list = Array.isArray(res?.items) ? res.items : [];
        // Server already sorts asc; sort defensively so the day grouping
        // and sequence numbering are correct even if it doesn't.
        list.sort((x, y) => {
          const tx = x?.timestamp ? new Date(x.timestamp).getTime() : 0;
          const ty = y?.timestamp ? new Date(y.timestamp).getTime() : 0;
          return tx - ty;
        });
        setItems(list);
        setTotal(res?.total != null ? res.total : list.length);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'Failed to load the event stream');
        setItems([]);
        setTotal(0);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [open, caseId, keysSig, typesSig]); // eslint-disable-line react-hooks/exhaustive-deps

  // Esc closes while open.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // Group items into day buckets for date headers, preserving the
  // chronological order and a running global sequence number.
  const days = useMemo(() => {
    const tz = getTzId();
    const out = [];
    let cur = null;
    items.forEach((it, idx) => {
      const dk = it?.timestamp ? dayKey(it.timestamp, tz) : '—';
      if (!cur || cur.key !== dk) {
        cur = { key: dk, rows: [] };
        out.push(cur);
      }
      cur.rows.push({ item: it, seq: idx + 1 });
    });
    return out;
  }, [items]);

  if (!open) return null;

  return (
    <aside
      className="fixed top-0 right-0 bottom-0 w-[440px] max-w-[90vw] bg-white border-l border-light-200 shadow-2xl z-30 flex flex-col animate-stream-slide"
      role="complementary"
      aria-label="Subgraph event stream"
      onClick={(e) => e.stopPropagation()}
    >
      <style>{`
        @keyframes stream-slide-in { from { transform: translateX(100%); } to { transform: translateX(0); } }
        .animate-stream-slide { animation: stream-slide-in 220ms cubic-bezier(0.22, 0.61, 0.36, 1); }
      `}</style>

      {/* Header */}
      <div className="flex items-start gap-2 px-3 py-2.5 border-b border-light-200 bg-light-50 flex-shrink-0">
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-semibold text-owl-blue-900">
            Event stream
          </div>
          <div className="mt-0.5 text-[11px] text-light-600">
            {loading
              ? 'Loading…'
              : `${Number(total).toLocaleString()} event${total === 1 ? '' : 's'} across ${boundedKeys.length} ${boundedKeys.length === 1 ? 'person' : 'people'}`}
            {boundedKeys.length >= 200 && (
              <span className="text-amber-600"> · capped at 200 people</span>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() => onClose?.()}
          className="p-1 text-light-400 hover:text-light-700 rounded flex-shrink-0"
          title="Close (Esc)"
          aria-label="Close event stream"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto px-2 py-2">
        {loading && (
          <div className="flex items-center gap-2 px-1 py-6 text-xs text-light-500 italic">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Loading event stream…
          </div>
        )}
        {!loading && error && (
          <div className="px-1 py-6 text-xs text-red-600">{error}</div>
        )}
        {!loading && !error && boundedKeys.length === 0 && (
          <div className="px-1 py-6 text-xs text-light-500 italic">
            No people in the current graph to build a stream from.
          </div>
        )}
        {!loading && !error && boundedKeys.length > 0 && items.length === 0 && (
          <div className="px-1 py-6 text-xs text-light-500 italic">
            No calls, messages, or emails among the people currently shown.
          </div>
        )}
        {!loading && !error && days.map((day) => (
          <div key={day.key} className="mb-2">
            <div className="sticky top-0 z-10 -mx-2 px-3 py-1 bg-light-50/95 backdrop-blur border-y border-light-100 text-[10px] font-semibold uppercase tracking-wide text-light-500">
              {day.key}
            </div>
            <ul className="space-y-1.5 mt-1.5">
              {day.rows.map(({ item, seq }) => (
                <StreamEventRow
                  key={item.id || `${item.type}-${item.timestamp}-${seq}`}
                  item={item}
                  seq={seq}
                  onSelect={() => publishItem(selectEntity, item, caseId)}
                />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </aside>
  );
}

/* ────────────────────── Sub-components ────────────────────── */

function StreamEventRow({ item, seq, onSelect }) {
  const Icon = ICON_FOR_TYPE[item.type] || MessageSquare;
  const fromName = item?.sender?.name || item?.sender?.key || 'Unknown';
  const toName = (Array.isArray(item?.recipients) && item.recipients[0]?.name)
    || (Array.isArray(item?.recipients) && item.recipients[0]?.key)
    || 'Unknown';
  const extraRecipients = Array.isArray(item?.recipients) && item.recipients.length > 1
    ? item.recipients.length - 1
    : 0;
  const when = item?.timestamp ? formatTs(item.timestamp) : '';
  const body = (item?.body || '').trim();
  const dur = item?.duration || item?.call_duration || null;

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className="w-full text-left rounded-lg px-2.5 py-1.5 border bg-white border-light-200 hover:bg-light-50"
      >
        {/* sequence + type + who → who + time */}
        <div className="flex items-center gap-1.5 text-[10px] text-light-500">
          <span className="font-mono text-light-400">#{seq}</span>
          <Icon className="w-3 h-3 flex-shrink-0" />
          <span className="font-medium text-light-700 truncate max-w-[90px]" title={fromName}>{fromName}</span>
          <ArrowRight className="w-2.5 h-2.5 text-light-400 flex-shrink-0" />
          <span className="truncate max-w-[90px]" title={toName}>
            {toName}{extraRecipients > 0 ? ` +${extraRecipients}` : ''}
          </span>
          {when && <span className="ml-auto whitespace-nowrap pl-1.5">{when}</span>}
        </div>
        {/* content */}
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
        {/* metadata footer: app + attachment count */}
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
 * Re-publish a single comms item as its own typed selection so the
 * selection rail hops to the EventAccordion — identical hand-off to
 * GraphEdgeAccordion.publishItem so a row opens full detail.
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
    source: 'graph.event-stream.item',
  });
}
