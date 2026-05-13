import React, { useEffect, useState } from 'react';
import { cellebriteEventsAPI } from '../../../../services/api';
import { EventBody } from '../../events/EventDetailDrawer';

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
 * The rail header is owned by CellebriteSelectionRail — this component
 * renders only the body content.
 */
export default function EventAccordion({ selection }) {
  const caseId = selection?.caseId;
  const event = selection?.payload || null;
  const nodeKey = event?.node_key || event?.id;

  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!caseId || !nodeKey) {
      setDetail(null);
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
    return () => {
      cancelled = true;
    };
  }, [caseId, nodeKey]);

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
  return <EventBody event={event} detail={detail} />;
}
