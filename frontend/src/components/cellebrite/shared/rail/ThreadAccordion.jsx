import React, { useCallback, useEffect, useState } from 'react';
import CommsThreadView from '../../comms/CommsThreadView';
import { useCellebriteSelection } from '../CellebriteSelectionContext';

/**
 * Rail body for thread-level selections.
 *
 * Selection contract:
 *   {
 *     type: 'thread',
 *     id:   thread_id,                   // required
 *     caseId,
 *     reportKey,
 *     payload: {
 *       thread_id, thread_type,          // required for the fetch
 *       report_key,                      // device the thread belongs to
 *       message_id?: string,             // optional — scroll to this item
 *       label?: string,                  // optional header hint
 *     }
 *   }
 *
 * Use case: investigator clicks a single message somewhere outside the
 * Comms Center (e.g. Overview → Messages, or a search result list) and
 * wants to see the WHOLE conversation with that message in context.
 *
 * Internally this is a thin wrapper over CommsThreadView (which already
 * has the bubble layout, scroll-to-message via `firstMatch`, and the
 * participant colour palette). The wrapper:
 *   - Maps the rail selection shape onto CommsThreadView's `selectedThread`
 *     + `firstMatch` props.
 *   - Tracks which item inside the thread is currently selected (so the
 *     bubble shows the highlight ring), and re-publishes per-item clicks
 *     through the rail so other accordions (e.g. EventAccordion's related
 *     sub-sections) can respond.
 *
 * Clicking a message inside the rail's thread re-publishes it as a
 * `message` selection — switching the rail to EventAccordion. To return
 * to the thread, click the original row in the source list again.
 */
export default function ThreadAccordion({ selection }) {
  const { selectEntity } = useCellebriteSelection();
  const caseId = selection?.caseId;
  const payload = selection?.payload || {};

  const selectedThread = payload?.thread_id
    ? {
        thread_id: payload.thread_id,
        thread_type: payload.thread_type,
        report_key: payload.report_key,
      }
    : null;

  // The "scroll to this message" anchor. CommsThreadView reads
  // `firstMatch.message_id` so we adapt the rail's flatter shape.
  const firstMatch = payload?.message_id ? { message_id: payload.message_id } : null;

  // Re-key the inner view whenever the thread OR the anchor changes so
  // its scroll-to effect runs again — the user clicked a fresh source
  // row and expects the rail to jump to the new message.
  const viewKey = `${payload?.thread_id || 'none'}::${payload?.message_id || 'top'}`;

  // Track which message inside the thread is "active" — drives the
  // bubble highlight ring. Seed from the anchor so the just-clicked
  // row reads as selected immediately.
  const [activeItemId, setActiveItemId] = useState(payload?.message_id || null);
  useEffect(() => {
    setActiveItemId(payload?.message_id || null);
  }, [payload?.thread_id, payload?.message_id]);

  // When the user clicks a different message inside the rail's thread,
  // republish as a message-typed selection so EventAccordion takes over.
  // The original "thread" selection is lost — to come back, click the
  // source row again. (We could keep a "back to thread" affordance but
  // the universal-rail pattern is one-selection-at-a-time.)
  const onItemSelect = useCallback((item) => {
    if (!item?.id) return;
    setActiveItemId(item.id);
    selectEntity({
      type: item.type === 'call' ? 'call'
          : item.type === 'email' ? 'email'
          : 'message',
      id: item.id,
      caseId,
      reportKey: selection?.reportKey || payload?.report_key,
      payload: {
        ...item,
        node_key: item.id,
        event_type: item.type,
      },
      source: 'rail.thread.item',
    });
  }, [caseId, selection?.reportKey, payload?.report_key, selectEntity]);

  if (!selectedThread) {
    return (
      <div className="px-3 py-4 text-xs text-red-600">
        Thread selection is missing thread_id.
      </div>
    );
  }

  return (
    // Fixed-height container so the inner CommsThreadView's flex-1 has
    // something to fill. The rail itself scrolls separately if its
    // contents grow beyond the available space; capping the thread
    // viewer at a generous height keeps scroll behaviour predictable
    // (scroll IN the thread, not the whole rail).
    <div className="flex flex-col" style={{ height: 'min(70vh, 720px)' }}>
      <CommsThreadView
        key={viewKey}
        caseId={caseId}
        selectedThread={selectedThread}
        firstMatch={firstMatch}
        onItemSelect={onItemSelect}
        selectedItemId={activeItemId}
      />
    </div>
  );
}
