import React, { useMemo } from 'react';
import { Mail, Paperclip, Folder, ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import OverviewDetailView from './OverviewDetailView';
import FilterCommsButton from './FilterCommsButton';
import PersonName from '../shared/PersonName';
import { useCellebriteSelection } from '../shared/CellebriteSelectionContext';
import { formatTs } from '../events/eventUtils';

// Tiny in/out chip — mirrors the visual language used by Messages and
// Contacts so investigators see the same indicator everywhere.
function DirectionChip({ direction }) {
  const isIncoming = direction === 'incoming';
  const Arrow = isIncoming ? ArrowDownLeft : ArrowUpRight;
  const colour = isIncoming ? 'text-blue-700' : 'text-emerald-700';
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-semibold uppercase ${colour}`}>
      <Arrow className="w-3 h-3" />
      {isIncoming ? 'In' : 'Out'}
    </span>
  );
}

export default function OverviewEmailsView({ caseId, report, onBack }) {
  const { selectEntity } = useCellebriteSelection();
  const reportKey = report?.report_key;

  // Columns built inside the function so the trailing 'Filter Comms'
  // column closes over caseId / reportKey. Emails carry both from_key
  // and to_key so the filter seeds the full pair (everything between
  // these two parties — chat + calls + emails).
  const COLUMNS = useMemo(() => [
    {
      key: 'direction',
      label: '',
      width: 'minmax(50px, 60px)',
      render: (r) => <DirectionChip direction={r.direction} />,
    },
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
      width: 'minmax(160px, 220px)',
      render: (r) =>
        (r.from_name || r.from_key)
          ? <PersonName name={r.from_name} personKey={r.from_key} numberClassName="text-[10px]" />
          : '—',
    },
    {
      key: 'to_name',
      label: 'To',
      width: 'minmax(160px, 220px)',
      render: (r) => {
        if (!r.to_name && !r.to_key) return '—';
        const more = r.to_count > 1 ? ` +${r.to_count - 1}` : '';
        return (
          <span className="inline-flex items-baseline gap-1 min-w-0">
            <PersonName name={r.to_name} personKey={r.to_key} numberClassName="text-[10px]" />
            {more && <span className="text-light-500 flex-shrink-0">{more}</span>}
          </span>
        );
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
          intentId={`overview.email.${r.id || r.node_key}`}
          label={`${r.from_name || r.from_key || '?'} ↔ ${r.to_name || r.to_key || '?'}`}
        />
      ),
    },
  ], [caseId, reportKey]);

  // Click an email → publish a 'thread' rail selection so the
  // ThreadAccordion shows the WHOLE pair conversation (everything
  // between sender and first recipient, on this device) with this
  // email as the scroll-to anchor. Replaces the legacy single-email
  // EventDetailDrawer — investigators wanted to see the conversation
  // context, not just the one email body.
  //
  // When the row has no thread_id (single email with no resolvable
  // pair, or sender == recipient) fall back to a single-email rail
  // selection so the rail still has something to show.
  const onRowClick = (row) => {
    if (!row?.thread_id) {
      selectEntity({
        type: 'email',
        id: row.id || row.node_key,
        caseId,
        reportKey: report?.report_key,
        payload: {
          ...row,
          node_key: row.node_key || row.id,
          event_type: 'email',
          label: row.subject || 'Email',
          summary: row.subject,
          sender: row.from_key ? { key: row.from_key, name: row.from_name } : null,
          counterpart: row.to_key ? { key: row.to_key, name: row.to_name } : null,
        },
        source: 'overview.emails',
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
        // Backend get_thread_detail handles 'emails' type by parsing
        // the synthetic id back into report_key + party pair and
        // rebuilding the pair feed.
        thread_type: 'emails',
        report_key: report?.report_key,
        // Anchor on the clicked email so ThreadAccordion's wrapper
        // around CommsThreadView's firstMatch handler scrolls to it
        // and flashes the highlight ring.
        message_id: row.id || row.node_key,
        label: row.subject || 'Email conversation',
      },
      source: 'overview.emails',
    });
  };

  return (
    <OverviewDetailView
      report={report}
      title="Emails"
      icon={Mail}
      color="red"
      onBack={onBack}
      columns={COLUMNS}
      defaultSort={{ key: 'timestamp', dir: 'desc' }}
      fetchPage={cellebriteOverviewAPI.getEmails}
      caseId={caseId}
      onRowClick={onRowClick}
    />
  );
}
