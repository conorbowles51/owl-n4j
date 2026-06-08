import React, { useEffect, useState } from 'react';
import {
  FileText, Loader2, User, Phone, MessageSquare, AlertTriangle,
  ChevronDown, ChevronRight, Hash, Clock, Tag, Download,
} from 'lucide-react';
import { cellebriteAPI, cellebriteEventsAPI } from '../../services/api';
import { phoneFromKey } from './shared/PersonName';
import EntitySummaryCard from './report/EntitySummaryCard';
import { exportCellebriteReportToPDF } from '../../utils/cellebritePdfExport';

/**
 * Report tab — the honest, traffic-derived profile of every phone.
 *
 * Unlike Overview (which trusts the ingest-time owner), the "primary user"
 * here is who ACTUALLY sent the messages, cross-checked against the device's
 * own numbers — so a mislabelled owner is visible. Surfaces recovered contact
 * aliases (the names the old pipeline used to discard) and the activity window
 * (so post-event usage is plain). Numbers are always shown beside names.
 */
export default function CellebriteReport({ caseId, isActive = true }) {
  const [devices, setDevices] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(() => new Set());
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!isActive || !caseId || devices) return;
    setLoading(true);
    cellebriteAPI.getDeviceReport(caseId)
      .then((r) => setDevices(r.devices || []))
      .catch((e) => setError(e.message || 'Failed to load device report'))
      .finally(() => setLoading(false));
  }, [isActive, caseId, devices]);

  const toggle = (key) => setExpanded((prev) => {
    const next = new Set(prev);
    next.has(key) ? next.delete(key) : next.add(key);
    return next;
  });

  // Export the assembled client-facing report to a client-side PDF (no
  // backend; the download is user-initiated via the Export button). The
  // component only receives `caseId`, so it's passed as the report name.
  //
  // Sections (S3-09): device summaries (already loaded), plus the investigator's
  // flagged "Key Events / Callouts" fetched here. Callouts are best-effort —
  // a failure to load them must not block the device-summary export, so we
  // default to [] on error.
  //
  // Visualizations (S3-08): the export utility now has an image slot ready
  // ({ title, dataUrl }), but live graph-image capture is DEFERRED for this
  // PR. Rationale: the cross-phone graph canvas lives in a different tab and is
  // not mounted inside the Report tab, so there's no canvas here to rasterize.
  // We pass `visualizations: []` now; wiring a real capture requires the graph
  // component to be mounted (a follow-up). The slot is exercised by the util's
  // own tests/callers and works when images are supplied.
  const handleExport = async () => {
    if (!devices || !devices.length || exporting) return;
    setExporting(true);
    try {
      let callouts = [];
      try {
        const res = await cellebriteEventsAPI.getCallouts(caseId);
        callouts = (res && res.callouts) || [];
      } catch (e) {
        console.warn('Could not load callouts for report; continuing without them:', e);
      }
      await exportCellebriteReportToPDF(caseId, {
        devices,
        callouts,
        visualizations: [],
        createdAt: new Date(),
      });
    } catch (e) {
      console.error('Cellebrite report PDF export failed:', e);
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-light-500 text-sm py-16">
        <Loader2 className="w-4 h-4 animate-spin mr-2" /> Building device report…
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-center gap-2 text-sm text-red-600 p-4">
        <AlertTriangle className="w-4 h-4" /> {error}
      </div>
    );
  }
  if (!devices || devices.length === 0) {
    return <div className="text-sm text-light-500 p-4">No devices to report on.</div>;
  }

  const fmtDate = (ts) => (ts ? String(ts).slice(0, 10) : '—');
  const label = (d) => {
    // Pull "C1".."C9" out of the report name when present.
    const m = (d.report_name || '').match(/_(C\d+[a-z]?)_|^(C\d+-\d+)/i);
    return m ? (m[1] || m[2]) : (d.evidence_number || d.report_key);
  };

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 bg-owl-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
          <FileText className="w-5 h-5 text-owl-blue-700" />
        </div>
        <div className="flex-1">
          <h2 className="text-base font-semibold text-owl-blue-900">Device Report</h2>
          <p className="text-xs text-light-600 max-w-3xl mt-0.5">
            Each phone's <strong>assigned owner</strong> (investigator-set) shown with
            the <strong>dominant user by traffic</strong> — the device's own number that
            actually sends the messages — and its number. When traffic is dominated by a
            different person than the assigned owner, it's flagged. Expand a row for device
            numbers, IMEI, and every saved alias.
          </p>
        </div>
        <button
          onClick={handleExport}
          disabled={exporting}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-owl-blue-200 text-owl-blue-700 hover:bg-owl-blue-50 disabled:opacity-60 disabled:cursor-not-allowed flex-shrink-0"
        >
          {exporting
            ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Generating…</>
            : <><Download className="w-3.5 h-3.5" /> Export PDF</>}
        </button>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-owl-blue-900 mb-2">Summary</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {devices.map((d) => (
            <EntitySummaryCard key={d.report_key} device={d} />
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-light-200">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-light-50 text-light-600 text-left">
              <th className="px-3 py-2 font-medium w-8"></th>
              <th className="px-3 py-2 font-medium">Device</th>
              <th className="px-3 py-2 font-medium">Owner / dominant user</th>
              <th className="px-3 py-2 font-medium text-right">Contacts</th>
              <th className="px-3 py-2 font-medium text-right">Messages</th>
              <th className="px-3 py-2 font-medium text-right">Calls (in/out)</th>
              <th className="px-3 py-2 font-medium">Activity window</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((d) => {
              const pu = d.primary_user || {};
              const isOpen = expanded.has(d.report_key);
              // Prefer the key-derived E.164 — the canonical identity — over
              // pu.numbers[0], which can carry junk MSISDN text like
              // "mobile number is 13014420513" straight from the extraction.
              const ownerNum = phoneFromKey(pu.key) || (pu.numbers && pu.numbers[0]) || '';
              // When the "name" is just the bare number (owner's own number
              // never saved as a contact), show "(unnamed)" instead of echoing
              // the number as a name.
              const nameIsNum = pu.name && /^[+(]?\d[\d\s().-]{5,}$/.test(String(pu.name).trim());
              const trafficName = (pu.name && !nameIsNum) ? pu.name : null;
              // Lead with the investigator-assigned owner (ground truth); fall
              // back to the dominant traffic name, then "(unnamed)".
              const ownerLabel = d.assigned_owner || trafficName || '(unnamed)';
              // Flag when the dominant traffic identity is a clearly different
              // name from the assigned owner (neither contains the other) — a
              // real forensic signal (e.g. C6 assigned "Gloria…" but Trabajo
              // sends the traffic).
              const _norm = (s) => String(s || '').toLowerCase();
              const trafficDiverges = d.assigned_owner && trafficName
                && !_norm(d.assigned_owner).includes(_norm(trafficName).split(' ')[0])
                && !_norm(trafficName).includes(_norm(d.assigned_owner).split(' ')[0]);
              return (
                <React.Fragment key={d.report_key}>
                  <tr className="border-t border-light-100 hover:bg-light-50/50">
                    <td className="px-2 py-2 align-top">
                      <button onClick={() => toggle(d.report_key)} className="text-light-400 hover:text-owl-blue-600">
                        {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </button>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <div className="font-semibold text-owl-blue-900">{label(d)}</div>
                      <div className="text-light-500">{d.device_model || 'Unknown'}</div>
                      {d.examiner && <div className="text-light-400 text-[10px]">{d.examiner}</div>}
                    </td>
                    <td className="px-3 py-2 align-top">
                      <div className="flex items-center gap-1.5">
                        <User className="w-3 h-3 text-light-400 flex-shrink-0" />
                        <span className="font-medium text-owl-blue-800">{ownerLabel}</span>
                        {d.assigned_owner && (
                          <span className="text-[9px] uppercase bg-owl-blue-100 text-owl-blue-700 px-1 rounded">assigned</span>
                        )}
                      </div>
                      {ownerNum && (
                        <div className="text-light-500 font-mono text-[11px] ml-4.5 flex items-center gap-1.5">
                          {ownerNum}
                          {pu.matches_device_number
                            ? <span className="text-[9px] uppercase bg-emerald-100 text-emerald-700 px-1 rounded font-sans">device #</span>
                            : <span className="text-[9px] uppercase bg-amber-100 text-amber-700 px-1 rounded font-sans">inferred</span>}
                        </div>
                      )}
                      {trafficDiverges && (
                        <div className="text-[10px] text-amber-700 ml-4.5 flex items-center gap-1 mt-0.5">
                          <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                          traffic dominated by “{trafficName}”
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 align-top text-right tabular-nums">{d.contact_entries.toLocaleString()}</td>
                    <td className="px-3 py-2 align-top text-right tabular-nums">{d.messages.toLocaleString()}</td>
                    <td className="px-3 py-2 align-top text-right tabular-nums">
                      {d.calls_in.toLocaleString()}/{d.calls_out.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 align-top whitespace-nowrap text-light-600">
                      {fmtDate(d.activity_first)} → {fmtDate(d.activity_last)}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-light-50/60">
                      <td></td>
                      <td colSpan={6} className="px-3 py-3">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <DetailBlock icon={Hash} title="Device numbers (as extracted)">
                            {(d.device_numbers || []).length
                              ? d.device_numbers.map((n) => (
                                  <div key={n} className="font-mono text-[11px] text-light-700">{n}</div>
                                ))
                              : <span className="text-light-400">none</span>}
                            {d.imei && <div className="text-[10px] text-light-400 mt-1">IMEI {d.imei}</div>}
                          </DetailBlock>
                          <DetailBlock icon={Tag} title={`Primary user saved as (${(pu.aliases || []).length})`}>
                            {(pu.aliases || []).length
                              ? pu.aliases.map((a) => (
                                  <span key={a} className="inline-block bg-white border border-light-200 rounded px-1.5 py-px text-[11px] text-light-700 mr-1 mb-1">{a}</span>
                                ))
                              : <span className="text-light-400">no saved name (own number)</span>}
                          </DetailBlock>
                          <DetailBlock icon={Clock} title="Counts">
                            <div className="text-[11px] text-light-700 space-y-0.5">
                              <div>{d.messages.toLocaleString()} messages · {pu.messages_sent?.toLocaleString() || 0} sent by owner</div>
                              <div>{d.calls.toLocaleString()} calls ({d.calls_in}/{d.calls_out})</div>
                              <div>{d.contact_entries.toLocaleString()} contact records · {d.locations.toLocaleString()} locations</div>
                            </div>
                          </DetailBlock>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DetailBlock({ icon: Icon, title, children }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-light-600 mb-1">
        <Icon className="w-3 h-3" /> {title}
      </div>
      <div>{children}</div>
    </div>
  );
}
