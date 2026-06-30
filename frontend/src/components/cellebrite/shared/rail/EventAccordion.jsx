import React, { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, MessageSquare, Clock } from 'lucide-react';
import { cellebriteEventsAPI } from '../../../../services/api';
import { EventBody } from '../../events/EventDetailDrawer';
import { useCellebriteSelection } from '../CellebriteSelectionContext';
import { formatTs } from '../../events/eventUtils';
import PersonName from '../PersonName';
import CommsMediaStrip from '../../comms/CommsMediaStrip';

/**
 * Rail accordion for "event-like" selections (call / message / email /
 * location / cell_tower / wifi / device_event / app_session).
 *
 * Reuses EventBody from EventDetailDrawer so the rail renders byte-for-
 * byte the same content the slide-over drawer does. Selection's payload
 * already has the projected event-row fields; we additionally fetch the
 * full detail document via getEventDetail (gives us recipients, body,
 * attachments) the same way the drawer does.
 *
 * For comms anchors (call / message / email) we additionally fetch the
 * /related endpoint and render two collapsible sub-sections below the
 * detail body:
 *   - Conversation: surrounding messages in the same thread
 *   - Around this time: cross-channel comms with the same parties
 *     within ±24h of the anchor
 * Clicking a row in either list re-publishes the selection, so the user
 * can hop along the conversation without leaving the rail.
 *
 * The rail header is owned by CellebriteSelectionRail — this component
 * renders only the body content.
 */
export default function EventAccordion({ selection }) {
  const caseId = selection?.caseId;
  const event = selection?.payload || null;
  const nodeKey = event?.node_key || event?.id;
  const isCommsAnchor = ['message', 'call', 'email'].includes(selection?.type);

  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [related, setRelated] = useState(null);
  const [relatedLoading, setRelatedLoading] = useState(false);

  // Detail + related are fetched in parallel — no dependency between
  // them server-side, so serialising would just cost a round trip.
  useEffect(() => {
    if (!caseId || !nodeKey) {
      setDetail(null);
      setRelated(null);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    cellebriteEventsAPI
      .getEventDetail(caseId, nodeKey)
      .then((d) => {
        if (cancelled) return;
        setDetail(d || null);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        // Don't blank an existing detail on transient failures — it
        // would make the rail flicker between "loading… not found"
        // and the previous selection during scroll-driven re-fetches.
        setLoading(false);
      });

    // Only chase /related for comms anchors. Locations / cell towers /
    // app sessions get the existing detail-only treatment.
    if (isCommsAnchor) {
      setRelatedLoading(true);
      cellebriteEventsAPI
        .getEventRelated(caseId, nodeKey, { windowH: 24, limit: 30 })
        .then((r) => {
          if (cancelled) return;
          setRelated(r || null);
          setRelatedLoading(false);
        })
        .catch(() => {
          if (cancelled) return;
          // Same flicker rule — keep the previous related set on
          // transient errors.
          setRelatedLoading(false);
        });
    } else {
      setRelated(null);
    }

    return () => {
      cancelled = true;
    };
  }, [caseId, nodeKey, isCommsAnchor]);

  if (!event) return null;
  if (loading && !detail) {
    return <div className="px-3 py-4 text-xs text-light-500">Loading details…</div>;
  }
  if (!detail) {
    return (
      <div className="px-3 py-4 text-xs text-red-600">
        Event detail not found.
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <EventBody event={event} detail={detail} caseId={caseId} />
      {isCommsAnchor && (
        <RelatedSections
          related={related}
          loading={relatedLoading}
          caseId={caseId}
          anchorKey={nodeKey}
        />
      )}
    </div>
  );
}

/**
 * Two collapsible lists below the EventBody — Conversation thread and
 * Around-this-time pair window. Each row is a one-click re-selection
 * so the rail re-renders with the new event's accordion + its own
 * related set (cheap; the new accordion just re-fetches the two URLs).
 */
function RelatedSections({ related, loading, caseId, anchorKey }) {
  const { selectEntity } = useCellebriteSelection();
  const [threadOpen, setThreadOpen] = useState(true);
  const [aroundOpen, setAroundOpen] = useState(true);

  if (loading && !related) {
    return (
      <div className="px-3 py-2 text-[11px] text-light-500 border-t border-light-100">
        Loading related events…
      </div>
    );
  }
  if (!related) return null;

  const thread = related.thread || [];
  const around = related.around || [];
  if (thread.length === 0 && around.length === 0) return null;

  const onPick = (row) => {
    if (!row) return;
    const id = row.id || row.node_key;
    if (!id || id === anchorKey) return;
    // Map projected event_type back into the rail selection type so
    // EventAccordion is re-used (rather than a generic accordion).
    const type =
      row.event_type === 'call' ? 'call'
      : row.event_type === 'email' ? 'email'
      : row.event_type === 'message' ? 'message'
      : 'event';
    selectEntity({
      type,
      id,
      caseId,
      reportKey: row.device_report_key,
      payload: row,
      source: 'rail.related',
    });
  };

  return (
    <div className="border-t border-light-100">
      {thread.length > 0 && (
        <Section
          icon={MessageSquare}
          title="Conversation"
          count={thread.length}
          open={threadOpen}
          onToggle={() => setThreadOpen((v) => !v)}
        >
          <RelatedList items={thread} onPick={onPick} highlight={anchorKey} />
        </Section>
      )}
      {around.length > 0 && (
        <Section
          icon={Clock}
          title="Around this time"
          count={around.length}
          open={aroundOpen}
          onToggle={() => setAroundOpen((v) => !v)}
        >
          <RelatedList items={around} onPick={onPick} highlight={anchorKey} />
        </Section>
      )}
    </div>
  );
}

function Section({ icon: Icon, title, count, open, onToggle, children }) {
  return (
    <div className="border-b border-light-100 last:border-b-0">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-1.5 px-3 py-1.5 text-[11px] uppercase tracking-wide text-light-600 hover:bg-light-50"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Icon className="w-3 h-3" />
        <span className="font-semibold">{title}</span>
        <span className="ml-auto text-light-400 normal-case tracking-normal">
          {count}
        </span>
      </button>
      {open && <div className="px-3 pb-2">{children}</div>}
    </div>
  );
}

function RelatedList({ items, onPick, highlight }) {
  return (
    <ul className="space-y-1 max-h-[260px] overflow-y-auto pr-1">
      {items.map((it) => {
        const id = it.id || it.node_key;
        const isAnchor = id === highlight;
        return (
          <li
            key={id}
            onClick={() => !isAnchor && onPick(it)}
            className={`text-[11px] border rounded px-2 py-1 ${
              isAnchor
                ? 'border-owl-blue-400 bg-owl-blue-50 cursor-default'
                : 'border-light-100 cursor-pointer hover:bg-light-50'
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-owl-blue-900 truncate">
                {it.label || it.event_type || 'Event'}
                {isAnchor && (
                  <span className="ml-1 text-[9px] uppercase tracking-wide text-owl-blue-600">
                    · this event
                  </span>
                )}
              </span>
              {it.timestamp && (
                <span className="text-light-500 tabular-nums whitespace-nowrap">
                  {formatTs(it.timestamp)}
                </span>
              )}
            </div>
            {(it.body || it.summary || it.sender?.name || it.counterpart?.name) && (
              <div className="text-light-600 mt-0.5 whitespace-pre-wrap break-words">
                {(it.sender || it.counterpart)?.name && (
                  <PersonName
                    name={(it.sender || it.counterpart).name}
                    personKey={(it.sender || it.counterpart).key}
                    className={`font-medium ${it.is_owner_sender ? 'text-owl-blue-700' : 'text-light-700'}`}
                    numberClassName="text-[10px]"
                  />
                )}
                {(it.sender || it.counterpart)?.name && (it.body || it.summary) && <span className="mx-1 text-light-400">·</span>}
                {(it.body || it.summary) && <span>{it.body || it.summary}</span>}
              </div>
            )}
            {Array.isArray(it.attachments) && it.attachments.length > 0 && (
              <CommsMediaStrip attachments={it.attachments} />
            )}
          </li>
        );
      })}
    </ul>
  );
}
