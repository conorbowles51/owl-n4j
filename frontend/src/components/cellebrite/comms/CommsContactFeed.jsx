/**
 * CommsContactFeed
 *
 * Inline (non-drawer) version of CommsContactDrawer's body. Renders
 * every call/message/email involving one contact across all phones,
 * grouped by day, newest first. Used by:
 *
 *   - CommsContactDrawer (legacy slide-in flyover from the old
 *     Communications row click), as a thin shell around this feed
 *   - CellebriteCommunicationView's NEW breadcrumb drill pane,
 *     mounted directly in the page (no drawer chrome) so the
 *     investigator can chain drills.
 *
 * Adds a `nameRenderer` slot so the page-level caller can wrap each
 * person name (sender, recipient) with a clickable affordance. Every
 * existing comm bubble / card already accepts the name via
 * `item.sender`/`item.recipients`, so we pass the renderer in as a
 * prop and have the bubbles pick it up on render.
 *
 * The drawer wrapper continues to work — it uses the default
 * (non-clickable) name renderer.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Phone, MessageSquare, Mail } from 'lucide-react';
import { cellebriteCommsAPI } from '../../../services/api';
import CommsTypeFilter from './CommsTypeFilter';
import CommsMessageBubble from './CommsMessageBubble';
import CommsCallRow from './CommsCallRow';
import CommsEmailCard from './CommsEmailCard';
import { usePhoneReports } from '../../../context/PhoneReportsContext';
import { buildSenderPalette } from './commsUtils';

export default function CommsContactFeed({
  caseId,
  contact, // { person_key, name, ... } — minimum required is person_key
  // Optional pass-through so callers can pre-narrow by type
  initialTypes = ['message', 'call', 'email'],
  // Called when the user clicks a name in any rendered row. The new
  // Communications breadcrumb drill wires this to push a new frame;
  // the legacy drawer leaves it undefined (names are unclickable
  // there, preserving the original UX).
  onDrillName = null,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTypes, setActiveTypes] = useState(new Set(initialTypes));

  useEffect(() => {
    if (!caseId || !contact?.person_key) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    cellebriteCommsAPI
      .getContactFeed(caseId, contact.person_key, {
        types: [...activeTypes],
        limit: 1000,
      })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || 'Failed to load contact comms');
        setData(null);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [caseId, contact?.person_key, activeTypes]);

  const phoneCtx = usePhoneReports();
  const hasMultiplePhones = !!phoneCtx?.hasMultiple;

  // Stable colour palette across the contact's feed.
  const palette = useMemo(() => {
    const seen = new Map();
    for (const it of data?.items || []) {
      const s = it.sender;
      if (s?.key && !seen.has(s.key)) {
        seen.set(s.key, { key: s.key, name: s.name || s.key, is_owner: !!s.is_owner });
      }
    }
    return buildSenderPalette([...seen.values()]);
  }, [data]);

  // Group by day + mark speaker runs so the message-bubble component
  // collapses repeated sender avatars.
  const grouped = useMemo(() => {
    const out = [];
    let currentDay = null;
    let lastSenderKey = null;
    for (const item of data?.items || []) {
      const day = (item.timestamp || '').slice(0, 10) || '—';
      if (currentDay !== day) {
        out.push({ type: 'date-sep', day });
        currentDay = day;
        lastSenderKey = null;
      }
      if (item.type === 'message') {
        const senderKey = item.sender?.key || 'unknown';
        const isFirstInRun = senderKey !== lastSenderKey;
        out.push({ type: 'item', item, isFirstInRun });
        lastSenderKey = senderKey;
      } else {
        out.push({ type: 'item', item, isFirstInRun: true });
        lastSenderKey = null;
      }
    }
    return out;
  }, [data]);

  const counts = useMemo(() => {
    if (!data?.items) return {};
    return data.items.reduce((acc, it) => {
      acc[it.type] = (acc[it.type] || 0) + 1;
      return acc;
    }, {});
  }, [data]);

  if (!contact?.person_key) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-light-500 italic">
        No contact selected.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Filter row + counts */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
        <CommsTypeFilter active={activeTypes} onChange={setActiveTypes} />
        <div className="flex-1" />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-light-400" />}
        <div className="flex items-center gap-2 text-[11px] text-light-600">
          <span className="flex items-center gap-1">
            <Phone className="w-3 h-3 text-emerald-600" />
            {(counts.call || 0).toLocaleString()}
          </span>
          <span className="flex items-center gap-1">
            <MessageSquare className="w-3 h-3 text-blue-600" />
            {(counts.message || 0).toLocaleString()}
          </span>
          <span className="flex items-center gap-1">
            <Mail className="w-3 h-3 text-amber-600" />
            {(counts.email || 0).toLocaleString()}
          </span>
          <span className="text-light-500">· {(data?.total || 0).toLocaleString()} total</span>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto bg-gradient-to-b from-light-50 to-light-100 py-2">
        {error && <div className="p-4 text-xs text-red-600">{error}</div>}
        {!loading && !error && (data?.items?.length || 0) === 0 && (
          <div className="flex items-center justify-center h-full text-sm text-light-500 italic">
            No comms found for this contact.
          </div>
        )}
        {grouped.map((row, idx) => {
          if (row.type === 'date-sep') {
            return (
              <div key={`sep-${idx}`} className="flex items-center justify-center my-2">
                <span className="text-[10px] bg-light-200 text-light-600 px-2 py-0.5 rounded-full">
                  {formatDay(row.day)}
                </span>
              </div>
            );
          }
          const item = row.item;
          if (item.type === 'call') {
            return (
              <CommsCallRow
                key={item.id || idx}
                item={item}
                reportKey={item.report_key}
                showPhoneChip={hasMultiplePhones}
                caseId={caseId}
                onDrillName={onDrillName}
              />
            );
          }
          if (item.type === 'email') {
            return (
              <CommsEmailCard
                key={item.id || idx}
                item={item}
                reportKey={item.report_key}
                showPhoneChip={hasMultiplePhones}
                caseId={caseId}
                onDrillName={onDrillName}
              />
            );
          }
          return (
            <CommsMessageBubble
              key={item.id || idx}
              item={item}
              palette={palette}
              showSenderName
              isFirstInRun={row.isFirstInRun}
              reportKey={item.report_key}
              showPhoneChip={hasMultiplePhones}
              caseId={caseId}
              onDrillName={onDrillName}
            />
          );
        })}
      </div>
    </div>
  );
}

function formatDay(d) {
  if (!d || d === '—') return '(no date)';
  try {
    const dt = new Date(d + 'T00:00:00');
    if (isNaN(dt.getTime())) return d;
    return dt.toLocaleDateString([], {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return d;
  }
}
