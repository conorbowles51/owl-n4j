import React, { useCallback, useMemo, useState } from 'react';
import { User, Smartphone, Phone, MessageSquare, Mail } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import OverviewDetailView from './OverviewDetailView';
import ContactDetailDrawer from './ContactDetailDrawer';
import FilterCommsButton from './FilterCommsButton';
import PersonName, { phoneFromKey } from '../shared/PersonName';
import { useCellebriteSelection } from '../shared/CellebriteSelectionContext';

export default function OverviewContactsView({ caseId, report, onBack }) {
  const [openContact, setOpenContact] = useState(null);

  // Bridge contact selection into the universal rail. Drawer + rail
  // both render during the transition; once the rail is proven solid,
  // the slide-over can be removed in a follow-up.
  const { selectEntity, clearSelection } = useCellebriteSelection();
  const handleContactSelect = useCallback((row) => {
    setOpenContact(row);
    if (row) {
      selectEntity({
        type: 'contact',
        id: row.key,
        caseId,
        reportKey: report?.report_key,
        payload: row,
        source: 'overview',
      });
    } else {
      clearSelection();
    }
  }, [caseId, report?.report_key, selectEntity, clearSelection]);

  // Columns built inside the component so the trailing 'Filter Comms'
  // column closes over caseId / report.report_key — those aren't
  // available to a module-scoped COLUMNS const.
  const reportKey = report?.report_key;
  const COLUMNS = useMemo(() => [
    {
      key: 'name',
      label: 'Name',
      width: 'minmax(180px, 1fr)',
      render: (r) => (
        <span className="flex items-center gap-1.5">
          {r.is_phone_owner ? (
            <Smartphone className="w-3 h-3 text-emerald-600" title="Phone owner" />
          ) : (
            <User className="w-3 h-3 text-light-400" />
          )}
          <PersonName name={r.name} personKey={r.key} hideNumber className="truncate" />
        </span>
      ),
    },
    {
      key: 'phone_numbers',
      label: 'Phone numbers',
      width: 'minmax(180px, 1fr)',
      render: (r) => {
        const nums = r.phone_numbers || [];
        if (nums.length > 0) {
          return (
            <span className="font-mono text-[11px] text-light-700">
              {nums.slice(0, 2).join(', ')}
              {nums.length > 2 && ` +${nums.length - 2}`}
            </span>
          );
        }
        // Fall back to the canonical number derived from the phone-<digits>
        // key so a missing phone_numbers list never leaves the column blank.
        const fromKey = phoneFromKey(r.key);
        return fromKey
          ? <span className="font-mono text-[11px] text-light-700">{fromKey}</span>
          : '—';
      },
    },
    {
      key: 'calls',
      label: 'Calls',
      width: 'minmax(70px, 90px)',
      align: 'right',
      render: (r) =>
        r.calls > 0 ? (
          <span className="flex items-center justify-end gap-1 text-emerald-700">
            <Phone className="w-3 h-3" />
            {r.calls}
          </span>
        ) : (
          '—'
        ),
    },
    {
      key: 'messages',
      label: 'Messages',
      width: 'minmax(80px, 100px)',
      align: 'right',
      render: (r) =>
        r.messages > 0 ? (
          <span className="flex items-center justify-end gap-1 text-blue-700">
            <MessageSquare className="w-3 h-3" />
            {r.messages}
          </span>
        ) : (
          '—'
        ),
    },
    {
      key: 'emails',
      label: 'Emails',
      width: 'minmax(70px, 90px)',
      align: 'right',
      render: (r) =>
        r.emails > 0 ? (
          <span className="flex items-center justify-end gap-1 text-amber-700">
            <Mail className="w-3 h-3" />
            {r.emails}
          </span>
        ) : (
          '—'
        ),
    },
    {
      key: 'interactions',
      label: 'Total',
      width: 'minmax(70px, 90px)',
      align: 'right',
      render: (r) => r.interactions > 0 ? r.interactions.toLocaleString() : '—',
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
          personKeys={[r.key]}
          intentId={`overview.contact.${r.key}`}
          label={r.name || r.key}
        />
      ),
    },
  ], [caseId, reportKey]);

  return (
    <>
      <OverviewDetailView
        report={report}
        title="Contacts"
        icon={User}
        color="blue"
        onBack={onBack}
        columns={COLUMNS}
        defaultSort={{ key: 'interactions', dir: 'desc' }}
        fetchPage={cellebriteOverviewAPI.getContacts}
        caseId={caseId}
        onRowClick={handleContactSelect}
      />
      {openContact && (
        <ContactDetailDrawer
          caseId={caseId}
          reportKey={report?.report_key}
          contactKey={openContact.key}
          contactPreview={openContact}
          onClose={() => handleContactSelect(null)}
        />
      )}
    </>
  );
}
