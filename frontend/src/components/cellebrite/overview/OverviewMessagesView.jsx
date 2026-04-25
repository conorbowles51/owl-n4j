import React, { useState } from 'react';
import { MessageSquare, Paperclip } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import OverviewDetailView from './OverviewDetailView';
import EventDetailDrawer from '../events/EventDetailDrawer';
import { formatTs } from '../events/eventUtils';
import { appIconEmoji } from '../comms/commsUtils';

const COLUMNS = [
  {
    key: 'timestamp',
    label: 'Time',
    width: 'minmax(140px, 160px)',
    render: (r) => (r.timestamp ? formatTs(r.timestamp) : '—'),
  },
  {
    key: 'source_app',
    label: 'App',
    width: 'minmax(120px, 150px)',
    render: (r) => (
      <span className="flex items-center gap-1.5">
        <span>{appIconEmoji(r.source_app)}</span>
        <span className="truncate">{r.source_app || '—'}</span>
      </span>
    ),
  },
  {
    key: 'sender_name',
    label: 'Sender',
    width: 'minmax(120px, 180px)',
    render: (r) => r.sender_name || r.sender_key || '—',
  },
  {
    key: 'body_preview',
    label: 'Body',
    width: 'minmax(220px, 1.5fr)',
    render: (r) => r.body_preview || '',
  },
  {
    key: 'attachment_count',
    label: 'Attachments',
    width: 'minmax(100px, 120px)',
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

export default function OverviewMessagesView({ caseId, report, onBack }) {
  const [openEvent, setOpenEvent] = useState(null);

  const fetchPage = (cid, rk, opts) => cellebriteOverviewAPI.getMessages(cid, rk, opts);

  const onRowClick = (row) => {
    setOpenEvent({
      id: row.id,
      node_key: row.node_key,
      event_type: 'message',
      label: `${row.source_app || ''} message`.trim(),
      summary: row.body_preview,
      timestamp: row.timestamp,
      latitude: null,
      longitude: null,
      sender: row.sender_key ? { key: row.sender_key, name: row.sender_name } : null,
      thread_id: row.thread_id,
    });
  };

  return (
    <>
      <OverviewDetailView
        report={report}
        title="Messages"
        icon={MessageSquare}
        color="amber"
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
