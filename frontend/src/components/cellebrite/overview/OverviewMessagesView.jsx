import React, { useMemo } from 'react';
import { MessageSquare, Paperclip } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import OverviewDetailView from './OverviewDetailView';
import FilterCommsButton from './FilterCommsButton';
import { useCellebriteSelection } from '../shared/CellebriteSelectionContext';
import { formatTs } from '../events/eventUtils';
import { appIconEmoji } from '../comms/commsUtils';

export default function OverviewMessagesView({ caseId, report, onBack }) {
  const { selectEntity } = useCellebriteSelection();
  const reportKey = report?.report_key;

  // Columns built inside the component so the trailing 'Filter Comms'
  // column closes over caseId / reportKey. Sender_key is the only
  // person key we have on a Message row; the recipient lives behind
  // the thread, so single-key filter is the best we can do here
  // without an extra fetch. Filtering by sender alone still gives
  // investigators "every comm involving this sender" which is
  // usually what they want.
  const COLUMNS = useMemo(() => [
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
          personKeys={[r.sender_key]}
          intentId={`overview.message.${r.id || r.node_key}`}
          label={r.sender_name || r.sender_key || 'Sender'}
        />
      ),
    },
  ], [caseId, reportKey]);

  // Click a row → publish a 'thread' selection so the rail's
  // ThreadAccordion renders the WHOLE conversation with the clicked
  // message as the scroll-to anchor. Replaces the legacy single-message
  // EventDetailDrawer — investigators kept asking "where does this fit
  // in the conversation?" and that's what they actually want to see.
  const onRowClick = (row) => {
    if (!row?.thread_id) {
      // Fallback for messages with no resolved chat parent — publish
      // as a single-message selection so the rail still has something
      // to show. Rare; happens for orphaned message nodes.
      selectEntity({
        type: 'message',
        id: row.id || row.node_key,
        caseId,
        reportKey: report?.report_key,
        payload: {
          ...row,
          node_key: row.node_key || row.id,
          event_type: 'message',
          label: `${row.source_app || ''} message`.trim(),
          summary: row.body_preview,
          sender: row.sender_key ? { key: row.sender_key, name: row.sender_name } : null,
        },
        source: 'overview.messages',
      });
      return;
    }
    selectEntity({
      type: 'thread',
      id: row.thread_id,
      caseId,
      reportKey: report?.report_key,
      payload: {
        thread_id: row.thread_id,
        // Overview Messages is by definition the messages tab — every
        // row here is a chat-typed thread.
        thread_type: 'chat',
        report_key: report?.report_key,
        // Anchor the in-rail scroll to the clicked message and seed the
        // bubble highlight ring. `message_id` matches the bubble's DOM
        // data-attr; `anchor_key` is the Neo4j key, which the server
        // uses to centre the loaded window — needed for long chats
        // (1k+ messages, common for WhatsApp) where the default
        // oldest-first slice wouldn't include the clicked message.
        message_id: row.id || row.node_key,
        anchor_key: row.node_key || row.key,
        label: row.thread_name || `${row.source_app || ''} conversation`.trim(),
      },
      source: 'overview.messages',
    });
  };

  return (
    <OverviewDetailView
      report={report}
      title="Messages"
      icon={MessageSquare}
      color="amber"
      onBack={onBack}
      columns={COLUMNS}
      defaultSort={{ key: 'timestamp', dir: 'desc' }}
      fetchPage={cellebriteOverviewAPI.getMessages}
      caseId={caseId}
      onRowClick={onRowClick}
    />
  );
}
