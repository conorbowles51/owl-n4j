import React, { useCallback, useState } from 'react';
import { User, Smartphone, Phone, MessageSquare, Mail } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import OverviewDetailView from './OverviewDetailView';
import ContactDetailDrawer from './ContactDetailDrawer';
import { useCellebriteSelection } from '../shared/CellebriteSelectionContext';

const COLUMNS = [
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
        <span className="truncate">{r.name || r.key}</span>
      </span>
    ),
  },
  {
    key: 'phone_numbers',
    label: 'Phone numbers',
    width: 'minmax(180px, 1fr)',
    render: (r) =>
      (r.phone_numbers || []).length > 0 ? (
        <span className="font-mono text-[11px] text-light-700">
          {r.phone_numbers.slice(0, 2).join(', ')}
          {r.phone_numbers.length > 2 && ` +${r.phone_numbers.length - 2}`}
        </span>
      ) : (
        '—'
      ),
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
];

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
