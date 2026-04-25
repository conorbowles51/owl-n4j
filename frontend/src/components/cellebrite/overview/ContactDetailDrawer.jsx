import React, { useEffect, useState } from 'react';
import { X, User, Phone, Mail, MessageSquare, Loader2, Smartphone } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import { formatTs, formatDuration } from '../events/eventUtils';
import LinkNodeToEntityButton from '../../entities/LinkNodeToEntityButton';

/**
 * Drawer showing a single contact + recent calls / messages with that
 * contact, scoped to one device.
 */
export default function ContactDetailDrawer({ caseId, reportKey, contactKey, contactPreview, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!caseId || !reportKey || !contactKey) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    cellebriteOverviewAPI
      .getContactDetail(caseId, reportKey, contactKey)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || 'Failed to load contact');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, reportKey, contactKey]);

  // Esc closes
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const contact = data?.contact || contactPreview || { key: contactKey };

  return (
    <div className="fixed inset-y-0 right-0 w-[32vw] min-w-[400px] max-w-[600px] bg-white shadow-2xl border-l border-light-200 z-40 flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-light-200 bg-blue-50">
        <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 bg-blue-100">
          <User className="w-4 h-4 text-blue-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-owl-blue-900 truncate">
            {contact.name || contact.key}
          </div>
          <div className="text-[11px] text-light-600 flex items-center gap-1">
            {contact.is_phone_owner && (
              <span className="flex items-center gap-0.5 text-emerald-700">
                <Smartphone className="w-3 h-3" />
                Phone owner
              </span>
            )}
            <span className="font-mono text-light-500 truncate">{contact.key}</span>
          </div>
        </div>
        <LinkNodeToEntityButton caseId={caseId} nodeKey={contactKey} />
        <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800" title="Close (Esc)">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="p-6 flex items-center justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-light-400" />
          </div>
        )}
        {error && <div className="p-4 text-xs text-red-600">{error}</div>}
        {data && (
          <div className="p-4 space-y-4">
            {/* Identifiers */}
            {(contact.phone_numbers && contact.phone_numbers.length > 0) && (
              <Section title="Phone numbers">
                <ul className="text-light-800 space-y-0.5 text-sm">
                  {contact.phone_numbers.map((p) => (
                    <li key={p} className="flex items-center gap-1.5">
                      <Phone className="w-3 h-3 text-light-500" /> {p}
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {(contact.all_identifiers || []).filter(Boolean).length > 0 && (
              <Section title="Identifiers">
                <ul className="text-[11px] font-mono text-light-700 space-y-0.5">
                  {contact.all_identifiers.map((v) => (
                    <li key={v} className="break-all">{v}</li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Recent calls */}
            <Section title={`Recent calls (${data.recent_calls?.length || 0})`}>
              {(data.recent_calls || []).length === 0 ? (
                <div className="text-xs text-light-500 italic">No calls</div>
              ) : (
                <ul className="space-y-1">
                  {data.recent_calls.map((c) => (
                    <li key={c.key} className="flex items-center gap-2 text-xs border-b border-light-100 pb-1">
                      <Phone className={`w-3 h-3 ${c.call_type === 'Missed' ? 'text-red-600' : 'text-emerald-600'}`} />
                      <span className="tabular-nums text-light-500 w-32 flex-shrink-0">
                        {c.timestamp ? formatTs(c.timestamp) : '—'}
                      </span>
                      <span className="text-light-700 flex-1">
                        {c.direction || ''} · {c.call_type || ''} · {formatDuration(c.duration) || ''}
                      </span>
                      <span className="text-[10px] text-light-500 flex-shrink-0">{c.source_app}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            {/* Recent messages */}
            <Section title={`Recent messages (${data.recent_messages?.length || 0})`}>
              {(data.recent_messages || []).length === 0 ? (
                <div className="text-xs text-light-500 italic">No messages</div>
              ) : (
                <ul className="space-y-1">
                  {data.recent_messages.map((m) => (
                    <li key={m.key} className="text-xs border-b border-light-100 pb-1">
                      <div className="flex items-center gap-2">
                        <MessageSquare className="w-3 h-3 text-blue-600 flex-shrink-0" />
                        <span className="tabular-nums text-light-500 w-32 flex-shrink-0">
                          {m.timestamp ? formatTs(m.timestamp) : '—'}
                        </span>
                        <span className="text-[10px] text-light-500 flex-shrink-0">{m.source_app}</span>
                      </div>
                      <div className="text-light-800 ml-5 mt-0.5 whitespace-pre-wrap break-words">
                        {m.body}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-light-500 mb-1">
        {title}
      </div>
      {children}
    </div>
  );
}
