import React, { useMemo } from 'react';
import { Phone, PhoneIncoming, PhoneOutgoing, PhoneMissed, Video } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import OverviewDetailView from './OverviewDetailView';
import FilterCommsButton from './FilterCommsButton';
import { useCellebriteSelection } from '../shared/CellebriteSelectionContext';
import { formatTs, formatDuration } from '../events/eventUtils';

function callIcon(direction, callType) {
  const t = (callType || '').toLowerCase();
  const d = (direction || '').toLowerCase();
  if (t === 'missed' || d.includes('miss')) return PhoneMissed;
  if (d.includes('incoming')) return PhoneIncoming;
  if (d.includes('outgoing')) return PhoneOutgoing;
  return Phone;
}

export default function OverviewCallsView({ caseId, report, onBack }) {
  const { selectEntity } = useCellebriteSelection();
  const reportKey = report?.report_key;

  // Row click → open the call in the universal rail (replaces the
  // legacy slide-over for consistency with the other Overview tabs).
  const onRowClick = (row) => {
    selectEntity({
      type: 'call',
      id: row.id || row.node_key,
      caseId,
      reportKey,
      payload: {
        ...row,
        node_key: row.node_key || row.id,
        event_type: 'call',
        label: `Call (${row.direction || ''} ${row.call_type || ''})`.trim(),
        sender: row.from_key ? { key: row.from_key, name: row.from_name } : null,
        counterpart: row.to_key ? { key: row.to_key, name: row.to_name } : null,
      },
      source: 'overview.calls',
    });
  };

  // Columns built inside so the trailing 'Filter Comms' column closes
  // over caseId / reportKey. Calls have both from_key and to_key so
  // the filter seeds the full pair — the Comms feed shows everything
  // between these two parties (calls, messages, emails).
  const COLUMNS = useMemo(() => [
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
    {
      key: '_filter',
      label: '',
      width: 'minmax(40px, 48px)',
      align: 'right',
      sortable: false,
      render: (r) => (
        <FilterCommsButton
          caseId={caseId}
          reportKey={reportKey}
          personKeys={[r.from_key, r.to_key]}
          intentId={`overview.call.${r.id || r.node_key}`}
          label={`${r.from_name || r.from_key || '?'} ↔ ${r.to_name || r.to_key || '?'}`}
        />
      ),
    },
  ], [caseId, reportKey]);

  return (
    <OverviewDetailView
      report={report}
      title="Calls"
      icon={Phone}
      color="emerald"
      onBack={onBack}
      columns={COLUMNS}
      defaultSort={{ key: 'timestamp', dir: 'desc' }}
      fetchPage={cellebriteOverviewAPI.getCalls}
      caseId={caseId}
      onRowClick={onRowClick}
    />
  );
}
