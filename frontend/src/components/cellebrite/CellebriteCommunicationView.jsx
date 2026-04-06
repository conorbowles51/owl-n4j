import React, { useState, useEffect, useMemo } from 'react';
import { Loader2, Search, ArrowUpDown, Smartphone, Users } from 'lucide-react';
import { cellebriteAPI } from '../../services/api';

/**
 * Communication analysis view with contact frequency table and shared contacts.
 */
export default function CellebriteCommunicationView({ caseId }) {
  const [data, setData] = useState({ contacts: [], shared_contacts: [] });
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortField, setSortField] = useState('call_count');
  const [sortDir, setSortDir] = useState('desc');
  const [selectedContact, setSelectedContact] = useState(null);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setLoading(true);

    cellebriteAPI.getCommunicationNetwork(caseId).then(result => {
      if (!cancelled) {
        setData(result || { contacts: [], shared_contacts: [] });
        setLoading(false);
      }
    }).catch(() => {
      if (!cancelled) {
        setData({ contacts: [], shared_contacts: [] });
        setLoading(false);
      }
    });

    return () => { cancelled = true; };
  }, [caseId]);

  const filteredContacts = useMemo(() => {
    let list = data.contacts || [];
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      list = list.filter(c =>
        (c.name || '').toLowerCase().includes(term) ||
        (c.phone || '').includes(term) ||
        (c.person_key || '').toLowerCase().includes(term)
      );
    }
    list.sort((a, b) => {
      const aVal = a[sortField] || 0;
      const bVal = b[sortField] || 0;
      return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
    });
    return list;
  }, [data.contacts, searchTerm, sortField, sortDir]);

  const toggleSort = (field) => {
    if (sortField === field) {
      setSortDir(prev => prev === 'desc' ? 'asc' : 'desc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-light-400" />
      </div>
    );
  }

  return (
    <div className="h-full flex min-h-0">
      {/* Left: Contact Frequency Table */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-light-200">
        {/* Search */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
            <input
              type="text"
              placeholder="Search contacts..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs border border-light-300 rounded bg-white focus:outline-none focus:ring-1 focus:ring-emerald-400"
            />
          </div>
          <span className="text-xs text-light-500 flex-shrink-0">
            {filteredContacts.length} contacts
          </span>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto min-h-0">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-light-50 z-10">
              <tr className="border-b border-light-200">
                <th className="text-left px-3 py-2 font-medium text-light-600">Name</th>
                <th className="text-left px-3 py-2 font-medium text-light-600">Phone</th>
                <SortHeader field="call_count" label="Calls" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                <SortHeader field="message_count" label="Messages" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                <SortHeader field="email_count" label="Emails" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                <th className="text-center px-3 py-2 font-medium text-light-600">Devices</th>
              </tr>
            </thead>
            <tbody>
              {filteredContacts.map((contact) => {
                const total = (contact.call_count || 0) + (contact.message_count || 0) + (contact.email_count || 0);
                const isSelected = selectedContact === contact.person_key;
                return (
                  <tr
                    key={contact.person_key}
                    className={`border-b border-light-100 cursor-pointer transition-colors ${
                      isSelected ? 'bg-emerald-50' : 'hover:bg-light-50'
                    }`}
                    onClick={() => setSelectedContact(isSelected ? null : contact.person_key)}
                  >
                    <td className="px-3 py-2 font-medium text-owl-blue-900 truncate max-w-[150px]">
                      {contact.name}
                    </td>
                    <td className="px-3 py-2 text-light-600 truncate max-w-[120px]">
                      {contact.phone}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {contact.call_count > 0 && (
                        <span className="px-1.5 py-0.5 bg-green-50 text-green-700 rounded">
                          {contact.call_count}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {contact.message_count > 0 && (
                        <span className="px-1.5 py-0.5 bg-purple-50 text-purple-700 rounded">
                          {contact.message_count}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {contact.email_count > 0 && (
                        <span className="px-1.5 py-0.5 bg-red-50 text-red-700 rounded">
                          {contact.email_count}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className="text-light-500">{(contact.devices || []).length}</span>
                    </td>
                  </tr>
                );
              })}
              {filteredContacts.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-8 text-center text-light-400">
                    No contacts found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right: Shared Contacts */}
      <div className="w-80 flex-shrink-0 flex flex-col min-h-0 bg-light-50">
        <div className="px-4 py-2.5 border-b border-light-200 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-amber-500" />
            <h3 className="text-sm font-semibold text-owl-blue-900">
              Shared Contacts
            </h3>
            <span className="text-xs text-light-500 ml-auto">
              {(data.shared_contacts || []).length}
            </span>
          </div>
          <p className="text-[10px] text-light-500 mt-0.5">
            Contacts appearing on multiple devices
          </p>
        </div>

        <div className="flex-1 overflow-y-auto min-h-0 px-4 py-2 space-y-2">
          {(data.shared_contacts || []).length === 0 ? (
            <div className="text-xs text-light-400 text-center py-8">
              No shared contacts found.
              {data.contacts?.length > 0 && ' Contacts only appear on one device.'}
            </div>
          ) : (
            (data.shared_contacts || []).map(sc => (
              <div
                key={sc.person_key}
                className={`p-2.5 bg-white rounded border transition-colors ${
                  selectedContact === sc.person_key
                    ? 'border-amber-300 shadow-sm'
                    : 'border-light-200 hover:border-light-300'
                }`}
                onClick={() => setSelectedContact(selectedContact === sc.person_key ? null : sc.person_key)}
              >
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 bg-amber-100 rounded-full flex items-center justify-center flex-shrink-0">
                    <Users className="w-3 h-3 text-amber-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium text-owl-blue-900 truncate">
                      {sc.name}
                    </div>
                    {sc.phone && (
                      <div className="text-[10px] text-light-500 truncate">{sc.phone}</div>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {(sc.devices || []).map((dk, i) => (
                    <span
                      key={dk}
                      className="flex items-center gap-1 px-1.5 py-0.5 bg-amber-50 text-amber-700 text-[10px] rounded"
                    >
                      <Smartphone className="w-2.5 h-2.5" />
                      Device {i + 1}
                    </span>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function SortHeader({ field, label, sortField, sortDir, onSort }) {
  const active = sortField === field;
  return (
    <th
      className="text-center px-3 py-2 font-medium text-light-600 cursor-pointer hover:bg-light-100 select-none"
      onClick={() => onSort(field)}
    >
      <span className="inline-flex items-center gap-0.5">
        {label}
        <ArrowUpDown className={`w-3 h-3 ${active ? 'text-emerald-600' : 'text-light-300'}`} />
      </span>
    </th>
  );
}
