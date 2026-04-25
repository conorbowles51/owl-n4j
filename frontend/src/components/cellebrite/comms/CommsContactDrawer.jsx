import React, { useEffect, useRef, useState } from 'react';
import { X, User, Smartphone, Loader2, Phone, MessageSquare, Mail } from 'lucide-react';
import { cellebriteCommsAPI } from '../../../services/api';
import CommsTypeFilter from './CommsTypeFilter';
import CommsMessageBubble from './CommsMessageBubble';
import CommsCallRow from './CommsCallRow';
import CommsEmailCard from './CommsEmailCard';
import LinkNodeToEntityButton from '../../entities/LinkNodeToEntityButton';

/**
 * Slide-in drawer showing every comm event involving one contact, across all
 * devices, interleaved by time (newest first).
 *
 * Reuses the existing comms render components (CommsMessageBubble for
 * messages, CommsCallRow for calls, CommsEmailCard for emails).
 *
 * Props:
 *   caseId
 *   contact         — minimum: { person_key, name } from the Communications row
 *   onClose
 */
export default function CommsContactDrawer({ caseId, contact, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTypes, setActiveTypes] = useState(new Set(['message', 'call', 'email']));
  const scrollRef = useRef(null);

  // Esc closes
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Fetch feed
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
    return () => {
      cancelled = true;
    };
  }, [caseId, contact?.person_key, activeTypes]);

  if (!contact) return null;

  // Compute counts to show in the header
  const counts = data?.items
    ? data.items.reduce(
        (acc, it) => {
          acc[it.type] = (acc[it.type] || 0) + 1;
          return acc;
        },
        {}
      )
    : {};

  // Build day-grouped list (newest first)
  const grouped = [];
  let currentDay = null;
  for (const item of data?.items || []) {
    const day = (item.timestamp || '').slice(0, 10) || '—';
    if (currentDay !== day) {
      grouped.push({ type: 'date-sep', day });
      currentDay = day;
    }
    grouped.push({ type: 'item', item });
  }

  const headerName = data?.contact?.name || contact.name || contact.person_key;
  const headerKey = data?.contact?.key || contact.person_key;

  return (
    <div className="fixed inset-y-0 right-0 w-[36vw] min-w-[460px] max-w-[700px] bg-white shadow-2xl border-l border-light-200 z-40 flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-light-200 bg-blue-50">
        <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 bg-blue-100">
          <User className="w-4 h-4 text-blue-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-owl-blue-900 truncate">
            {headerName}
          </div>
          <div className="text-[11px] text-light-600 flex items-center gap-1.5 flex-wrap">
            {data?.contact?.is_phone_owner && (
              <span className="flex items-center gap-0.5 text-emerald-700">
                <Smartphone className="w-3 h-3" />
                Phone owner
              </span>
            )}
            {(data?.contact?.phone_numbers || []).slice(0, 2).map((p) => (
              <span key={p} className="font-mono text-light-700">{p}</span>
            ))}
            {(data?.contact?.phone_numbers || []).length > 2 && (
              <span className="text-light-500">+{data.contact.phone_numbers.length - 2}</span>
            )}
          </div>
        </div>
        <LinkNodeToEntityButton caseId={caseId} nodeKey={headerKey} />
        <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800" title="Close (Esc)">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Sub-header: type filter + counts */}
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
      <div ref={scrollRef} className="flex-1 overflow-y-auto bg-gradient-to-b from-light-50 to-light-100 py-2">
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
            return <CommsCallRow key={item.id || idx} item={item} />;
          }
          if (item.type === 'email') {
            return <CommsEmailCard key={item.id || idx} item={item} />;
          }
          // message
          return (
            <CommsMessageBubble
              key={item.id || idx}
              item={item}
              showSenderName
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
