import React, { useEffect, useMemo, useState } from 'react';
import { Phone, MessageSquare, Mail, ArrowRight } from 'lucide-react';
import { cellebriteCommsAPI } from '../../../../services/api';
import { formatTs } from '../../events/eventUtils';
import { useCellebriteSelection } from '../CellebriteSelectionContext';

/**
 * Rail accordion for a directional comms edge in the Cross-Phone Graph.
 *
 * Selection contract (published by CellebriteCrossPhoneGraph's
 * onLinkClick):
 *   {
 *     type: 'graph-edge',
 *     id:   `edge-<a>-<b>-<label>`,
 *     caseId,
 *     payload: {
 *       _kind: 'graph-edge',
 *       a, b,                 // the two person keys (already prefix-stripped)
 *       aName, bName,         // display names
 *       label,                // 'call' | 'message' | 'email' | 'comms'
 *       total,                // edge total events
 *       dir_counts: { ab, ba },// ab = a→b, ba = b→a
 *       initiator,            // optional dominant initiator key
 *     }
 *   }
 *
 * Fetches the actual call/message/email items exchanged between exactly
 * those two parties (cellebriteCommsAPI.getBetween with participantKeys
 * = [a, b]) and renders them chronologically. The getBetween call is
 * involvement-based and can pull in 3rd parties on group threads, so we
 * client-side filter to items strictly between a and b: sender in {a,b}
 * AND at least one recipient in {a,b}.
 */
export default function GraphEdgeAccordion({ selection }) {
  // Re-publishing per-item lets a click on an event hop the rail to the
  // EventAccordion, matching the ThreadAccordion behaviour.
  const { selectEntity } = useCellebriteSelection();
  const caseId = selection?.caseId;
  const payload = selection?.payload || {};
  const { a, b, aName, bName, label, total, dir_counts } = payload;

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch only when the selected edge changes — not on every render.
  // The edge identity is captured by caseId + the two keys + label.
  useEffect(() => {
    if (!caseId || !a || !b) {
      setItems([]);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Pair-isolated, directional fetch. `participant_keys` is an OR
    // *involvement* filter — for a shared-chat edge it returns every
    // message either party sent in any chat (incl. with 3rd parties),
    // which is why the old strict client-filter dropped everything and
    // the body read "no events" despite a non-zero header.
    //
    // The correct query for "the comms ON this edge" is two DIRECTED
    // calls: from_keys=a→to_keys=b and from_keys=b→to_keys=a. Each
    // returns exactly the messages/calls/emails addressed between the
    // two parties (matching the edge's dir_counts), with no group-chat
    // noise. We merge + sort ascending to get the true sequence.
    const types = ['message', 'call', 'email'];
    Promise.all([
      cellebriteCommsAPI.getBetween(caseId, { fromKeys: [a], toKeys: [b], types, limit: 200, sort: 'asc' }),
      cellebriteCommsAPI.getBetween(caseId, { fromKeys: [b], toKeys: [a], types, limit: 200, sort: 'asc' }),
    ])
      .then(([abRes, baRes]) => {
        if (cancelled) return;
        const merged = [...(abRes?.items || []), ...(baRes?.items || [])];
        // De-dupe by id (a call can surface from both directions) and
        // sort chronologically so the panel reads as a flow.
        const seen = new Set();
        const deduped = [];
        for (const it of merged) {
          const key = it?.id || `${it?.type}-${it?.timestamp}-${it?.sender?.key}`;
          if (seen.has(key)) continue;
          seen.add(key);
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
        setError(err?.message || 'Failed to load comms for this edge');
        setItems([]);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [caseId, a, b, label]);

  const dirAB = dir_counts?.ab || 0;
  const dirBA = dir_counts?.ba || 0;
  const headerCount = total != null ? total : items.length;

  const labelText = useMemo(() => {
    const l = (label || '').toLowerCase();
    if (l === 'call') return 'calls';
    if (l === 'message') return 'messages';
    if (l === 'email') return 'emails';
    return 'events';
  }, [label]);

  if (!a || !b) {
    return (
      <div className="px-3 py-4 text-xs text-red-600">
        Edge selection is missing its participant keys.
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {/* Header — A ↔ B summary + direction breakdown */}
      <div className="px-3 py-2.5 border-b border-light-200 bg-light-50">
        <div className="text-[13px] font-semibold text-owl-blue-900 flex items-center gap-1.5 flex-wrap">
          <span className="truncate" title={aName}>{aName}</span>
          <span className="text-light-400">↔</span>
          <span className="truncate" title={bName}>{bName}</span>
        </div>
        <div className="mt-1 text-[11px] text-light-600 flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-owl-blue-800">
            {Number(headerCount).toLocaleString()} {labelText}
          </span>
          {(dirAB > 0 || dirBA > 0) && (
            <span className="text-light-500">
              {aName}→{bName}: {dirAB.toLocaleString()}
              {' · '}
              {bName}→{aName}: {dirBA.toLocaleString()}
            </span>
          )}
        </div>
      </div>

      {/* Body — chronological feed */}
      <div className="px-2 py-2">
        {loading && (
          <div className="px-1 py-4 text-xs text-light-500 italic">
            Loading comms…
          </div>
        )}
        {!loading && error && (
          <div className="px-1 py-4 text-xs text-red-600">
            {error}
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="px-1 py-4 text-xs text-light-500 italic">
            No direct calls, messages, or emails between {aName} and {bName}.
          </div>
        )}
        {!loading && !error && items.length > 0 && (
          <ul className="space-y-1.5">
            {items.map((it, idx) => (
              <EdgeEventRow
                key={it.id || `${it.type}-${it.timestamp}-${idx}`}
                item={it}
                seq={idx + 1}
                aKey={a}
                onSelect={() => publishItem(selectEntity, it, caseId)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ────────────────────── Sub-components ────────────────────── */

function EdgeEventRow({ item, seq, aKey, onSelect }) {
  const Icon = ICON_FOR_TYPE[item.type] || MessageSquare;
  const fromName = item?.sender?.name || item?.sender?.key || 'Unknown';
  const toName = (Array.isArray(item?.recipients) && item.recipients[0]?.name)
    || (Array.isArray(item?.recipients) && item.recipients[0]?.key)
    || 'Unknown';
  const when = item?.timestamp ? formatTs(item.timestamp) : '';
  const body = (item?.body || '').trim();
  // Direction relative to the edge's "a" party: events a→ sit on the
  // left tinted blue, events →a (from the other party) sit on the right
  // tinted slate — so the panel reads as a back-and-forth flow.
  const fromA = item?.sender?.key === aKey;
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
        {/* sequence + direction + time */}
        <div className="flex items-center gap-1.5 text-[10px] text-light-500">
          <span className="font-mono text-light-400">#{seq}</span>
          <Icon className="w-3 h-3 flex-shrink-0" />
          <span className="font-medium text-light-700 truncate max-w-[80px]" title={fromName}>{fromName}</span>
          <ArrowRight className="w-2.5 h-2.5 text-light-400 flex-shrink-0" />
          <span className="truncate max-w-[80px]" title={toName}>{toName}</span>
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

const ICON_FOR_TYPE = {
  call: Phone,
  message: MessageSquare,
  email: Mail,
};

/**
 * Re-publish a single comms item as its own typed selection so the
 * rail hops to the EventAccordion (same hand-off pattern the Thread
 * accordion uses for per-message clicks).
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
    source: 'rail.graph-edge.item',
  });
}
