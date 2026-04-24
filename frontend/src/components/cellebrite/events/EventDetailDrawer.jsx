import React, { useEffect, useState } from 'react';
import { X, MapPin, Smartphone, Clock, Info } from 'lucide-react';
import { cellebriteEventsAPI } from '../../../services/api';
import CommsMessageBubble from '../comms/CommsMessageBubble';
import CommsCallRow from '../comms/CommsCallRow';
import CommsEmailCard from '../comms/CommsEmailCard';
import { EVENT_COLORS, EVENT_ICONS, EVENT_LABELS, formatTs } from './eventUtils';

/**
 * Slide-in drawer showing full detail for a selected event.
 * Reuses Comms Center components for call/message/email renderings.
 */
export default function EventDetailDrawer({ caseId, event, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!event || !caseId) return;
    let cancelled = false;
    setLoading(true);
    cellebriteEventsAPI
      .getEventDetail(caseId, event.node_key || event.id)
      .then((d) => {
        if (!cancelled) {
          setDetail(d);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDetail(null);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, event]);

  // Esc to close
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!event) return null;

  const Icon = EVENT_ICONS[event.event_type] || Info;
  const color = EVENT_COLORS[event.event_type] || '#64748b';

  return (
    <div className="fixed inset-y-0 right-0 w-[30vw] min-w-[380px] max-w-[560px] bg-white shadow-2xl border-l border-light-200 z-40 flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-light-200" style={{ background: color + '10' }}>
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
          style={{ background: color }}
        >
          <Icon className="w-4 h-4 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-owl-blue-900 truncate">{event.label}</div>
          <div className="text-[11px] text-light-600 flex items-center gap-1 flex-wrap">
            <span>{EVENT_LABELS[event.event_type] || event.event_type}</span>
            <span>·</span>
            <Clock className="w-3 h-3" />
            <span className="tabular-nums">{formatTs(event.timestamp)}</span>
          </div>
        </div>
        <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800" title="Close (Esc)">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {loading && <div className="p-6 text-sm text-light-500">Loading…</div>}
        {!loading && !detail && <div className="p-6 text-sm text-red-600">Event detail not found.</div>}
        {detail && <EventBody event={event} detail={detail} />}
      </div>
    </div>
  );
}

function EventBody({ event, detail }) {
  const lat = detail.latitude ?? detail.nearest_location_lat;
  const lon = detail.longitude ?? detail.nearest_location_lon;
  const geoDirect = detail.latitude != null && detail.longitude != null;

  const GeoBlock = () => {
    if (lat == null || lon == null) return null;
    return (
      <div className="flex items-center gap-2 text-xs text-light-700 p-2 bg-light-50 rounded border border-light-200">
        <MapPin className="w-3.5 h-3.5" />
        <span className="font-mono">
          {Number(lat).toFixed(5)}, {Number(lon).toFixed(5)}
        </span>
        {!geoDirect && (
          <span className="text-[10px] text-amber-700">
            (nearest within {Math.round((detail.nearest_location_delta_s || 0) / 60)} min)
          </span>
        )}
      </div>
    );
  };

  // Synthesize data for the comms-center components' expected shapes
  switch (event.event_type) {
    case 'call': {
      const item = {
        id: detail.id,
        timestamp: detail.timestamp,
        source_app: detail.source_app,
        direction: detail.direction,
        call_type: detail.call_type,
        duration: detail.duration,
        video_call: !!detail.video_call,
        deleted_state: detail.deleted_state,
        attachments: detail.attachments || [],
        sender: event.counterpart && !event.sender ? null : event.sender,
        recipient: event.counterpart,
      };
      return (
        <div className="p-3 space-y-3">
          <GeoBlock />
          <div className="border border-light-200 rounded">
            <CommsCallRow item={item} />
          </div>
          <RawProps detail={detail} />
        </div>
      );
    }
    case 'message': {
      const item = {
        id: detail.id,
        timestamp: detail.timestamp,
        source_app: detail.source_app,
        message_type: detail.message_type,
        body: detail.body || '',
        deleted_state: detail.deleted_state,
        attachments: detail.attachments || [],
        sender: event.counterpart ? null : null,
      };
      return (
        <div className="p-3 space-y-3">
          <GeoBlock />
          <CommsMessageBubble item={item} showSenderName={false} />
          <RawProps detail={detail} />
        </div>
      );
    }
    case 'email': {
      const item = {
        id: detail.id,
        timestamp: detail.timestamp,
        source_app: detail.source_app,
        subject: detail.subject,
        body: detail.body || '',
        folder: detail.folder,
        email_status: detail.email_status,
        attachments: detail.attachments || [],
        sender: event.sender,
        recipient: event.counterpart,
      };
      return (
        <div className="p-3 space-y-3">
          <GeoBlock />
          <div className="border border-light-200 rounded">
            <CommsEmailCard item={item} defaultExpanded />
          </div>
          <RawProps detail={detail} />
        </div>
      );
    }
    case 'location':
    case 'cell_tower':
    case 'wifi':
      return (
        <div className="p-3 space-y-3">
          <GeoBlock />
          <RawProps detail={detail} />
        </div>
      );
    case 'power':
    case 'device_event':
      return (
        <div className="p-3 space-y-3">
          <div className="text-sm">
            <span className="font-medium">State:</span> {detail.state || '—'}
          </div>
          {detail.reason && (
            <div className="text-sm">
              <span className="font-medium">Reason:</span> {detail.reason}
            </div>
          )}
          {detail.battery != null && (
            <div className="text-sm">
              <span className="font-medium">Battery:</span> {detail.battery}
            </div>
          )}
          <RawProps detail={detail} />
        </div>
      );
    case 'app_session':
      return (
        <div className="p-3 space-y-3">
          <div className="text-sm">
            <span className="font-medium">App:</span> {detail.app_name || detail.app_package}
          </div>
          {detail.start_time && (
            <div className="text-sm">
              <span className="font-medium">Start:</span> {detail.start_time}
            </div>
          )}
          {detail.end_time && (
            <div className="text-sm">
              <span className="font-medium">End:</span> {detail.end_time}
            </div>
          )}
          {detail.duration_s && (
            <div className="text-sm">
              <span className="font-medium">Duration:</span> {detail.duration_s}s
            </div>
          )}
          <RawProps detail={detail} />
        </div>
      );
    default:
      return (
        <div className="p-3 space-y-3">
          <GeoBlock />
          <RawProps detail={detail} />
        </div>
      );
  }
}

function RawProps({ detail }) {
  // Show selected raw properties (not every property) for forensic traceability
  const keys = [
    'cellebrite_id',
    'cellebrite_report_key',
    'source_app',
    'deleted_state',
    'location_source',
    'nearest_location_key',
    'nearest_location_delta_s',
  ];
  const rows = keys
    .filter((k) => detail[k] != null)
    .map((k) => ({ k, v: String(detail[k]) }));
  if (!rows.length) return null;
  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-light-600 hover:text-owl-blue-700">
        Forensic metadata
      </summary>
      <table className="mt-2 w-full text-[11px] border-collapse">
        <tbody>
          {rows.map((r) => (
            <tr key={r.k} className="border-b border-light-100">
              <td className="pr-2 py-1 text-light-500 font-medium align-top">{r.k}</td>
              <td className="py-1 text-light-800 break-all">{r.v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
