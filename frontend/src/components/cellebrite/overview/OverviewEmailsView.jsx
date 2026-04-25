import React, { useState } from 'react';
import { Mail, Paperclip, Folder } from 'lucide-react';
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
    key: 'subject',
    label: 'Subject',
    width: 'minmax(220px, 1.5fr)',
    render: (r) => r.subject || '(no subject)',
  },
  {
    key: 'from_name',
    label: 'From',
    width: 'minmax(140px, 200px)',
    render: (r) => r.from_name || r.from_key || '—',
  },
  {
    key: 'to_name',
    label: 'To',
    width: 'minmax(140px, 200px)',
    render: (r) => {
      if (!r.to_name && !r.to_key) return '—';
      const main = r.to_name || r.to_key;
      const more = r.to_count > 1 ? ` +${r.to_count - 1}` : '';
      return `${main}${more}`;
    },
  },
  {
    key: 'folder',
    label: 'Folder',
    width: 'minmax(120px, 160px)',
    render: (r) =>
      r.folder ? (
        <span className="flex items-center gap-1">
          <Folder className="w-2.5 h-2.5 text-light-500" />
          <span className="truncate">{r.folder}</span>
        </span>
      ) : (
        '—'
      ),
  },
  {
    key: 'attachment_count',
    label: 'Attach.',
    width: 'minmax(80px, 100px)',
    align: 'right',
    render: (r) =>
      r.attachment_count > 0 ? (
        <span className="flex items-center justify-end gap-1 text-amber-700">
          <Paperclip className="w-3 h-3" />
          {r.attachment_count}
        </span>
      ) : (
        '—'
      ),
  },
];

export default function OverviewEmailsView({ caseId, report, onBack }) {
  const [openEvent, setOpenEvent] = useState(null);

  const fetchPage = (cid, rk, opts) => cellebriteOverviewAPI.getEmails(cid, rk, opts);

  const onRowClick = (row) => {
    setOpenEvent({
      id: row.id,
      node_key: row.node_key,
      event_type: 'email',
      label: row.subject || 'Email',
      summary: row.subject,
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
        title="Emails"
        icon={Mail}
        color="red"
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
