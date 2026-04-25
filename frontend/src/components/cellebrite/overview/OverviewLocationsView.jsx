import React, { useState } from 'react';
import { MapPin } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import OverviewDetailView from './OverviewDetailView';
import EventDetailDrawer from '../events/EventDetailDrawer';
import { formatTs } from '../events/eventUtils';

const COLUMNS = [
  {
    key: 'timestamp',
    label: 'Time',
    width: 'minmax(140px, 160px)',
    render: (r) => (r.timestamp ? formatTs(r.timestamp) : '—'),
  },
  {
    key: 'name',
    label: 'Name',
    width: 'minmax(180px, 1fr)',
    render: (r) => r.name || '—',
  },
  {
    key: 'location_type',
    label: 'Type',
    width: 'minmax(120px, 140px)',
    render: (r) => r.location_type || '—',
  },
  {
    key: 'source_app',
    label: 'Source app',
    width: 'minmax(120px, 150px)',
    render: (r) => r.source_app || '—',
  },
  {
    key: 'latitude',
    label: 'Lat / Lon',
    width: 'minmax(160px, 200px)',
    render: (r) =>
      r.latitude != null && r.longitude != null ? (
        <span className="flex items-center gap-1 font-mono text-[10px]">
          <MapPin className="w-2.5 h-2.5 text-cyan-600" />
          {Number(r.latitude).toFixed(4)}, {Number(r.longitude).toFixed(4)}
        </span>
      ) : (
        '—'
      ),
  },
];

export default function OverviewLocationsView({ caseId, report, onBack }) {
  const [openEvent, setOpenEvent] = useState(null);

  const fetchPage = (cid, rk, opts) => cellebriteOverviewAPI.getLocations(cid, rk, opts);

  const onRowClick = (row) => {
    setOpenEvent({
      id: row.id,
      node_key: row.node_key,
      event_type: 'location',
      label: row.name || 'Location',
      summary: row.location_type,
      timestamp: row.timestamp,
      latitude: row.latitude,
      longitude: row.longitude,
    });
  };

  return (
    <>
      <OverviewDetailView
        report={report}
        title="Locations"
        icon={MapPin}
        color="cyan"
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
