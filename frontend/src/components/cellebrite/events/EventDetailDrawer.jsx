import React, { useEffect, useState } from 'react';
import { X, MapPin, Smartphone, Clock, Info } from 'lucide-react';
import { cellebriteEventsAPI } from '../../../services/api';
import CommsMessageBubble from '../comms/CommsMessageBubble';
import CommsCallRow from '../comms/CommsCallRow';
import CommsEmailCard from '../comms/CommsEmailCard';
import LinkNodeToEntityButton from '../../entities/LinkNodeToEntityButton';
import PhoneIdentityChip from '../shared/PhoneIdentityChip';
import RailEmailBody from '../shared/rail/RailEmailBody';
import { usePhoneReports } from '../../../context/PhoneReportsContext';
import { useCellebriteTime } from '../shared/CellebriteTimezone';
import { EVENT_COLORS, EVENT_ICONS, EVENT_LABELS, formatTs } from './eventUtils';

/**
 * Slide-in drawer showing full detail for a selected event.
 * Reuses Comms Center components for call/message/email renderings.
 */
export default function EventDetailDrawer({ caseId, event, onClose }) {
  useCellebriteTime(); // re-render the drawer's times when the zone toggles
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
  // Show device origin in the header — drawer is shared across map,
  // table, timeline so the user shouldn't have to remember which row
  // they clicked.
  const phoneCtx = usePhoneReports();
  const showPhoneChip = !!phoneCtx?.hasMultiple && !!event.device_report_key;

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
        {showPhoneChip && (
          <PhoneIdentityChip
            reportKey={event.device_report_key}
            variant="default"
            showIcon
            className="flex-shrink-0"
          />
        )}
        <LinkNodeToEntityButton caseId={caseId} nodeKey={event.node_key || event.id} />
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

// Exported so the universal CellebriteSelectionRail can reuse the same
// projection logic instead of duplicating the type-by-type rendering.
// caseId is optional — only the VisitorsBlock currently needs it (so
// it can fetch /locations/visitors). Other branches keep working with
// the legacy two-arg shape.
export function EventBody({ event, detail, caseId = null }) {
  const lat = detail.latitude ?? detail.nearest_location_lat;
  const lon = detail.longitude ?? detail.nearest_location_lon;
  const geoDirect = detail.latitude != null && detail.longitude != null;

  // Phone identity chip shown above the comms anchor renderings so the
  // user always knows WHICH phone the selected message / call / email
  // came from. Only renders for multi-phone cases — single-phone cases
  // don't need the disambiguation and the chip would be noise.
  const PhoneChip = () => {
    return (
      <_PhoneChipForDetail event={event} detail={detail} />
    );
  };

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

  // The detail endpoint now resolves sender/recipient Person nodes
  // for comms-typed events. Prefer those (authoritative) and fall
  // back to whatever the caller passed in `event.sender` /
  // `event.counterpart` when the API hasn't returned them yet.
  const detailSender = detail.sender || event.sender || null;
  const detailRecipient = detail.recipient || event.counterpart || null;
  const detailRecipients =
    Array.isArray(detail.recipients) && detail.recipients.length > 0
      ? detail.recipients
      : (detailRecipient ? [detailRecipient] : []);

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
        sender: detailSender,
        recipient: detailRecipient,
      };
      return (
        <div className="p-3 space-y-3">
          <PhoneChip />
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
        sender: detailSender,
        recipient: detailRecipient,
        recipients: detailRecipients,
      };
      return (
        <div className="p-3 space-y-3">
          <PhoneChip />
          <GeoBlock />
          <CommsMessageBubble item={item} showSenderName />
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
        sender: detailSender,
        recipient: detailRecipient,
        recipients: detailRecipients,
      };
      return (
        <div className="space-y-3">
          <div className="px-3 pt-3">
            <PhoneChip />
            <GeoBlock />
          </div>
          {/* Rail-tuned renderer: HTML / Text / Raw toggle plus a
              dedicated attachments section with "Open in Files"
              links. Replaces the CommsEmailCard reuse, which was
              built for the thread view (collapsible chevron, dense
              metadata row) and didn't suit the permanently-expanded
              rail flyout. */}
          <RailEmailBody item={item} caseId={caseId} />
          <div className="px-3 pb-3">
            <RawProps detail={detail} />
          </div>
        </div>
      );
    }
    case 'location':
    case 'cell_tower':
    case 'wifi':
      return (
        <div className="p-3 space-y-3">
          <PlaceHeader event={event} detail={detail} type={event.event_type} />
          <GeoBlock />
          {event.event_type === 'wifi' && <WifiNetworkBlock detail={detail} />}
          <VisitorsBlock caseId={caseId} lat={lat} lon={lon} />
          <RawProps detail={detail} />
        </div>
      );
    case 'power':
    case 'device_event':
      return (
        <div className="p-3 space-y-3">
          <PhoneChip />
          {/* Single semantic line so the user reads "Connected ·
              Charging · battery 79%" in one glance instead of three
              separate label/value rows. */}
          <div className="text-sm flex flex-wrap items-baseline gap-1.5 p-2 bg-light-50 rounded border border-light-200">
            <span className="font-semibold text-owl-blue-900">
              {detail.state || event.label || event.event_type}
            </span>
            {detail.reason && (
              <span className="text-light-600">· {detail.reason}</span>
            )}
            {detail.battery != null && (
              <span className="text-light-600">· battery {detail.battery}%</span>
            )}
            {detail.source_app && (
              <span className="ml-auto text-[10px] uppercase tracking-wide text-light-500">
                {detail.source_app}
              </span>
            )}
          </div>
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
  // Show selected raw properties (not every property) for forensic traceability.
  // Includes the report key so investigators always see WHICH phone the
  // record came from even when the case has only one device — the
  // PhoneIdentityChip is suppressed on single-phone cases, so without
  // this key the source phone would be invisible.
  const keys = [
    'cellebrite_id',
    'cellebrite_report_key',
    'source_app',
    'deleted_state',
    'location_source',
    'geocode_source',
    'geocode_accuracy',
    'place_name',
    'address',
    'admin1',
    'country',
    'country_code',
    'ssid',
    'bssid',
    'channel',
    'security',
    // Device-event semantics — the writer separates these out of the
    // raw label so the user can see WHY/HOW the event exists
    // (Connected/Disconnected, Charging/Wifi, battery level, the
    // discriminator that decides which row this is).
    'state',
    'reason',
    'battery',
    'event_type',
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

/**
 * Compact "from this phone" chip rendered above comms anchors in the
 * rail. Only shows when the case has more than one phone — single-
 * phone cases don't need device disambiguation.
 */
function _PhoneChipForDetail({ event, detail }) {
  const phoneCtx = usePhoneReports();
  const showPhoneChip = !!phoneCtx?.hasMultiple;
  const reportKey = detail.cellebrite_report_key || event.device_report_key || event.report_key;
  if (!showPhoneChip || !reportKey) return null;
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wide text-light-500">
        From
      </span>
      <PhoneIdentityChip reportKey={reportKey} showIcon />
    </div>
  );
}

/**
 * Header block for location / wifi / cell_tower selections in the rail.
 *
 * Surfaces what the user complained was missing:
 *   - which phone the row came from (PhoneIdentityChip),
 *   - the place / address as a prominent heading instead of being
 *     buried at the end of the row,
 *   - reverse-geocode attribution so the user can tell at a glance
 *     whether the address came from the device or was inferred.
 *
 * Falls back gracefully — if no address / place_name exists we show
 * the location_type or "Location" so the header still anchors the
 * card. The phone chip only renders when the case has more than one
 * phone (single-phone cases don't need device disambiguation).
 */
function PlaceHeader({ event, detail, type }) {
  const phoneCtx = usePhoneReports();
  const showPhoneChip = !!phoneCtx?.hasMultiple;
  const reportKey = detail.cellebrite_report_key || event.device_report_key;
  const place = detail.place_name || event.place_name;
  const address = detail.address || event.address;
  const country = detail.country || event.country;
  const admin1 = detail.admin1 || event.admin1;
  const geo = detail.geocode_source || event.geocode_source;
  const title = address || place || detail.location_type || event.location_type
    || (type === 'wifi' ? (detail.ssid || event.ssid || 'Wi-Fi network')
        : type === 'cell_tower' ? (detail.cell_id || 'Cell tower')
        : 'Location');
  const subtitle = !address && (admin1 || country)
    ? [admin1, country].filter(Boolean).join(', ')
    : null;
  return (
    <div className="flex items-start gap-2 p-2 bg-light-50 rounded border border-light-200">
      <MapPin className="w-4 h-4 text-cyan-600 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-owl-blue-900 break-words">
          {title}
        </div>
        {subtitle && (
          <div className="text-[11px] text-light-600 mt-0.5">{subtitle}</div>
        )}
        {place && place !== title && (
          <div className="text-[11px] text-light-500 mt-0.5">{place}</div>
        )}
        {geo && geo !== 'cellebrite' && geo !== 'none' && (
          <span
            className="inline-block mt-1 text-[9px] uppercase tracking-wide bg-light-100 text-light-600 px-1 py-px rounded"
            title={`Reverse-geocoded via ${geo}${detail.geocode_accuracy ? ` (${detail.geocode_accuracy})` : ''}`}
          >
            via {geo}
          </span>
        )}
      </div>
      {showPhoneChip && reportKey && (
        <PhoneIdentityChip reportKey={reportKey} showIcon className="flex-shrink-0" />
      )}
    </div>
  );
}

/**
 * Network-info block for WiFi selections. Surfaces BSSID / SSID /
 * channel / security so investigators can trace the connection and
 * (where they care) cross-reference against a known-network db.
 *
 * Best-effort field plucking — Cellebrite reports vary in how they
 * label these; we render whichever subset is present rather than
 * forcing a fixed schema.
 */
function WifiNetworkBlock({ detail }) {
  const ssid = detail.ssid || detail.wifi_ssid || detail.network_name;
  const bssid = detail.bssid || detail.wifi_bssid || detail.mac_address;
  const channel = detail.channel || detail.wifi_channel;
  const security = detail.security || detail.wifi_security || detail.encryption;
  const freq = detail.frequency || detail.wifi_frequency;
  const signal = detail.signal_strength || detail.rssi;
  const rows = [];
  if (ssid) rows.push(['SSID', ssid]);
  if (bssid) rows.push(['BSSID', bssid]);
  if (channel) rows.push(['Channel', String(channel)]);
  if (freq) rows.push(['Frequency', String(freq)]);
  if (security) rows.push(['Security', security]);
  if (signal != null) rows.push(['Signal', String(signal)]);
  if (rows.length === 0) return null;
  return (
    <div className="text-xs">
      <div className="text-[10px] uppercase tracking-wide text-light-500 mb-1">
        Network
      </div>
      <table className="w-full text-[11px] border-collapse">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-b border-light-100">
              <td className="pr-2 py-1 text-light-500 font-medium align-top whitespace-nowrap">
                {k}
              </td>
              <td className="py-1 text-light-800 break-all font-mono">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * "Devices that visited this place" — rail section for location /
 * cell_tower / wifi selections that have a lat / lon. Hits
 * /cellebrite/locations/visitors with a 150m radius and renders one
 * row per device with visit count + first/last seen.
 *
 * Defaults to a 150m radius — tight enough to mean "the same place"
 * for a building / address, wide enough to absorb the typical GPS
 * noise on phone fixes. Rendered only when there's at least one
 * visitor (always at least the source phone for a location row).
 *
 * Quietly does nothing on cases without a caseId or coords — the
 * rail flyout shows the rest of the body instead of an empty
 * "Devices" block.
 */
function VisitorsBlock({ caseId, lat, lon }) {
  const phoneCtx = usePhoneReports();
  const [visitors, setVisitors] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!caseId || lat == null || lon == null) {
      setVisitors(null);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    cellebriteEventsAPI
      .getLocationVisitors(caseId, { lat, lon, radiusM: 150 })
      .then((res) => {
        if (!cancelled) {
          setVisitors(res?.visitors || []);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setVisitors([]);
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [caseId, lat, lon]);
  if (!caseId || lat == null || lon == null) return null;
  if (loading && !visitors) {
    return (
      <div className="text-[11px] text-light-500 italic">
        Checking for other devices…
      </div>
    );
  }
  if (!visitors || visitors.length === 0) return null;
  const labelFor = (rk) => {
    const id = phoneCtx?.getIdentityByKey?.(rk);
    return id?.label || id?.deviceModel || rk;
  };
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-light-500 mb-1 flex items-center gap-1.5">
        <Smartphone className="w-3 h-3" />
        Devices that visited this place
        <span className="text-light-400 normal-case tracking-normal">
          (~150m)
        </span>
      </div>
      <ul className="space-y-1">
        {visitors.map((v) => (
          <li
            key={v.device_report_key}
            className="flex items-center gap-2 text-[11px] border border-light-100 rounded px-2 py-1 bg-white"
          >
            <PhoneIdentityChip
              reportKey={v.device_report_key}
              variant="dense"
              className="flex-shrink-0"
            />
            <span className="truncate flex-1 text-light-800" title={v.device_report_key}>
              {labelFor(v.device_report_key)}
            </span>
            <span className="text-light-700 font-medium tabular-nums">
              {v.visit_count.toLocaleString()} visit{v.visit_count === 1 ? '' : 's'}
            </span>
            {v.last_seen && (
              <span className="text-light-500 tabular-nums whitespace-nowrap">
                last {formatTs(v.last_seen)}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
