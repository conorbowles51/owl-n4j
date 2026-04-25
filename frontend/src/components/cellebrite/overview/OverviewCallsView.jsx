import React, { useState } from 'react';
import { Phone, PhoneIncoming, PhoneOutgoing, PhoneMissed, Video } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import OverviewDetailView from './OverviewDetailView';
import EventDetailDrawer from '../events/EventDetailDrawer';
import { formatTs, formatDuration } from '../events/eventUtils';

function callIcon(direction, callType) {
  const t = (callType || '').toLowerCase();
  const d = (direction || '').toLowerCase();
  if (t === 'missed' || d.includes('miss')) return PhoneMissed;
  if (d.includes('incoming')) return PhoneIncoming;
  if (d.includes('outgoing')) return PhoneOutgoing;
  return Phone;
}

const COLUMNS = [
  {
    key: 'timestamp',
    label: 'Time',
    width: 'minmax(140px, 160px)',
    render: (r) => (r.timestamp ? formatTs(r.timestamp) : '—'),
  },
  {
    key: 'direction',
    label: 'Direction',
    width: 'minmax(120px, 140px)',
    render: (r) => {
      const Icon = callIcon(r.direction, r.call_type);
      const isMissed = (r.call_type || '').toLowerCase() === 'missed';
      return (
        <span className="flex items-center gap-1.5">
          <Icon className={`w-3 h-3 ${isMissed ? 'text-red-600' : 'text-emerald-600'}`} />
          <span>{r.direction || '—'}</span>
          {r.video_call && <Video className="w-3 h-3 text-light-500" />}
        </span>
      );
    },
  },
  {
    key: 'call_type',
    label: 'Type',
    width: 'minmax(100px, 120px)',
    render: (r) => r.call_type || '—',
  },
  {
    key: 'duration',
    label: 'Duration',
    width: 'minmax(90px, 110px)',
    render: (r) => formatDuration(r.duration) || '—',
  },
  {
    key: 'from_name',
    label: 'From',
    width: 'minmax(120px, 1fr)',
    render: (r) => r.from_name || r.from_key || '—',
  },
  {
    key: 'to_name',
    label: 'To',
    width: 'minmax(120px, 1fr)',
    render: (r) => r.to_name || r.to_key || '—',
  },
  {
    key: 'source_app',
    label: 'Source app',
    width: 'minmax(120px, 140px)',
    render: (r) => r.source_app || '—',
  },
];

export default function OverviewCallsView({ caseId, report, onBack }) {
  const [openEvent, setOpenEvent] = useState(null);

  const fetchPage = (cid, rk, opts) => cellebriteOverviewAPI.getCalls(cid, rk, opts);

  const onRowClick = (row) => {
    // Project the row into an event-like shape for EventDetailDrawer
    setOpenEvent({
      id: row.id,
      node_key: row.node_key,
      event_type: 'call',
      label: `Call (${row.direction || ''} ${row.call_type || ''})`.trim(),
      timestamp: row.timestamp,
      latitude: null,
      longitude: null,
      sender: row.from_key ? { key: row.from_key, name: row.from_name } : null,
      counterpart: row.to_key ? { key: row.to_key, name: row.to_name } : null,
    });
  };

  return (
    <>
      <OverviewDetailView
        report={report}
        title="Calls"
        icon={Phone}
        color="emerald"
        onBack={onBack}
        columns={COLUMNS}
        defaultSort={{ key: 'timestamp', dir: 'desc' }}
        fetchPage={fetchPage}
        caseId={caseId}
        onRowClick={onRowClick}
      />
      {openEvent && (
        <EventDetailDrawer
          caseId={caseId}
          event={openEvent}
          onClose={() => setOpenEvent(null)}
        />
      )}
    </>
  );
}
