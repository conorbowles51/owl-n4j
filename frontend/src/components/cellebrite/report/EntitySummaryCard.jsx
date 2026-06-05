import React from 'react';
import { User, Phone, MessageSquare, Clock, Tag, Hash } from 'lucide-react';
import { phoneFromKey } from '../shared/PersonName';

/**
 * Presentational summary card for ONE device/entity in the Device Report.
 *
 * Mirrors the honest, traffic-derived profile the Report table already
 * computes: leads with the investigator-assigned owner (ground truth),
 * falls back to the dominant traffic name, and always shows the canonical
 * number beside it. Surfaces the activity window, contact/message/call
 * counts, and the recovered aliases the primary user was saved as.
 *
 * Driven entirely by the device object already fetched by CellebriteReport —
 * no API calls. Field names match the device-report payload exactly:
 * report_name, evidence_number, report_key, device_model, examiner,
 * assigned_owner, primary_user{key,name,aliases,numbers}, contact_entries,
 * messages, calls_in, calls_out, activity_first, activity_last.
 */
export default function EntitySummaryCard({ device }) {
  const d = device || {};
  const pu = d.primary_user || {};

  // Pull "C1".."C9" out of the report name when present (same heuristic the
  // table uses), else fall back to evidence number / report key.
  const m = (d.report_name || '').match(/_(C\d+[a-z]?)_|^(C\d+-\d+)/i);
  const cardLabel = m ? (m[1] || m[2]) : (d.evidence_number || d.report_key);

  // Prefer the key-derived E.164 (canonical identity) over pu.numbers[0],
  // which can carry junk MSISDN text from the extraction.
  const ownerNum = phoneFromKey(pu.key) || (pu.numbers && pu.numbers[0]) || '';
  const nameIsNum = pu.name && /^[+(]?\d[\d\s().-]{5,}$/.test(String(pu.name).trim());
  const trafficName = (pu.name && !nameIsNum) ? pu.name : null;
  const ownerLabel = d.assigned_owner || trafficName || '(unnamed)';

  const fmtDate = (ts) => (ts ? String(ts).slice(0, 10) : '—');
  const aliases = pu.aliases || [];

  return (
    <div className="rounded-lg border border-light-200 bg-white p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-owl-blue-900 text-sm">{cardLabel}</div>
          <div className="text-light-500 text-xs">{d.device_model || 'Unknown'}</div>
          {d.examiner && <div className="text-light-400 text-[10px]">{d.examiner}</div>}
        </div>
        {d.assigned_owner && (
          <span className="text-[9px] uppercase bg-owl-blue-100 text-owl-blue-700 px-1.5 py-0.5 rounded">assigned</span>
        )}
      </div>

      <div>
        <div className="flex items-center gap-1.5">
          <User className="w-3.5 h-3.5 text-light-400 flex-shrink-0" />
          <span className="font-medium text-owl-blue-800 text-sm">{ownerLabel}</span>
        </div>
        {ownerNum && (
          <div className="text-light-500 font-mono text-[11px] ml-5 flex items-center gap-1.5">
            <Phone className="w-3 h-3 text-light-400 flex-shrink-0" />
            {ownerNum}
            {pu.matches_device_number
              ? <span className="text-[9px] uppercase bg-emerald-100 text-emerald-700 px-1 rounded font-sans">device #</span>
              : <span className="text-[9px] uppercase bg-amber-100 text-amber-700 px-1 rounded font-sans">inferred</span>}
          </div>
        )}
      </div>

      <div className="flex items-center gap-1.5 text-xs text-light-600">
        <Clock className="w-3.5 h-3.5 text-light-400 flex-shrink-0" />
        <span className="whitespace-nowrap">{fmtDate(d.activity_first)} → {fmtDate(d.activity_last)}</span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <Stat icon={User} label="Contacts" value={(d.contact_entries || 0).toLocaleString()} />
        <Stat icon={MessageSquare} label="Messages" value={(d.messages || 0).toLocaleString()} />
        <Stat icon={Phone} label="Calls in/out" value={`${(d.calls_in || 0).toLocaleString()}/${(d.calls_out || 0).toLocaleString()}`} />
      </div>

      <div>
        <div className="flex items-center gap-1.5 text-[11px] font-medium text-light-600 mb-1">
          <Tag className="w-3 h-3" /> Saved as ({aliases.length})
        </div>
        {aliases.length
          ? aliases.map((a) => (
              <span key={a} className="inline-block bg-light-50 border border-light-200 rounded px-1.5 py-px text-[11px] text-light-700 mr-1 mb-1">{a}</span>
            ))
          : <span className="text-light-400 text-[11px]">no saved name (own number)</span>}
      </div>

      {(d.device_numbers || []).length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-light-600 mb-1">
            <Hash className="w-3 h-3" /> Device numbers
          </div>
          {d.device_numbers.map((n) => (
            <div key={n} className="font-mono text-[11px] text-light-700">{n}</div>
          ))}
          {d.imei && <div className="text-[10px] text-light-400 mt-1">IMEI {d.imei}</div>}
        </div>
      )}
    </div>
  );
}

function Stat({ icon: Icon, label, value }) {
  return (
    <div className="rounded border border-light-100 bg-light-50/60 px-2 py-1.5">
      <div className="flex items-center gap-1 text-[10px] text-light-500">
        <Icon className="w-3 h-3" /> {label}
      </div>
      <div className="font-semibold text-owl-blue-900 tabular-nums">{value}</div>
    </div>
  );
}
