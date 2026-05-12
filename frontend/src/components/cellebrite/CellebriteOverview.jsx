import React, { useState } from 'react';
import {
  Smartphone, Phone, MessageSquare, MapPin, Mail, User, Hash, Shield,
  Trash2, Pencil, Loader2, X, Check, AlertTriangle, ChevronDown, ChevronRight,
  CheckCircle2,
} from 'lucide-react';
import OverviewContactsView from './overview/OverviewContactsView';
import OverviewCallsView from './overview/OverviewCallsView';
import OverviewMessagesView from './overview/OverviewMessagesView';
import OverviewLocationsView from './overview/OverviewLocationsView';
import OverviewEmailsView from './overview/OverviewEmailsView';
import { cellebriteAPI } from '../../services/api';
import { usePhoneReports } from '../../context/PhoneReportsContext';

/**
 * Device cards dashboard showing all ingested phone reports.
 *
 * Each stat tile (Contacts / Calls / Messages / Locations / Emails) drills
 * into a category-specific detail view. The detail view replaces the cards
 * grid and provides a Back button to return.
 *
 * Each card also exposes:
 *   - "Edit name" pencil → override the auto-detected device name
 *   - "Delete phone report" trash → remove the PhoneReport and every
 *     node tagged with its key from the case (with confirmation).
 */
export default function CellebriteOverview({ caseId, reports, onReportsChanged }) {
  const phoneCtx = usePhoneReports();

  // When set, we render the matching detail view instead of the cards grid.
  // Shape: { category: "contacts" | "calls" | ..., report: <reportObj> }
  const [drillDown, setDrillDown] = useState(null);

  // Confirmation dialogs.
  const [deleteTarget, setDeleteTarget] = useState(null); // report obj
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const [editTarget, setEditTarget] = useState(null); // report obj

  const performDelete = async () => {
    if (!deleteTarget || !caseId) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await cellebriteAPI.deleteReport(caseId, deleteTarget.report_key);
      setDeleteTarget(null);
      // Refresh the global phone-reports context so every Cellebrite
      // tab (selector chip strip, identity chips, etc.) updates.
      if (phoneCtx?.refresh) await phoneCtx.refresh();
      if (onReportsChanged) await onReportsChanged();
    } catch (err) {
      setDeleteError(err?.message || 'Failed to delete phone report');
    } finally {
      setDeleting(false);
    }
  };

  if (!reports || reports.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-light-500 text-sm">
        No phone reports available
      </div>
    );
  }

  // Drill-down view active → render the matching category view
  if (drillDown) {
    const onBack = () => setDrillDown(null);
    const Common = { caseId, report: drillDown.report, onBack };
    switch (drillDown.category) {
      case 'contacts':
        return <OverviewContactsView {...Common} />;
      case 'calls':
        return <OverviewCallsView {...Common} />;
      case 'messages':
        return <OverviewMessagesView {...Common} />;
      case 'locations':
        return <OverviewLocationsView {...Common} />;
      case 'emails':
        return <OverviewEmailsView {...Common} />;
      default:
        return null;
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {reports.map((report) => (
          <DeviceCard
            key={report.report_key}
            report={report}
            onDrillDown={(category) => setDrillDown({ category, report })}
            onDelete={() => setDeleteTarget(report)}
            onEditName={() => setEditTarget(report)}
          />
        ))}
      </div>

      {deleteTarget && (
        <DeleteConfirmModal
          report={deleteTarget}
          onCancel={() => { setDeleteTarget(null); setDeleteError(null); }}
          onConfirm={performDelete}
          deleting={deleting}
          error={deleteError}
        />
      )}

      {editTarget && (
        <EditDeviceNameModal
          caseId={caseId}
          report={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={async () => {
            setEditTarget(null);
            if (phoneCtx?.refresh) await phoneCtx.refresh();
            if (onReportsChanged) await onReportsChanged();
          }}
        />
      )}
    </div>
  );
}

function DeviceCard({ report, onDrillDown, onDelete, onEditName }) {
  const stats = report.stats || {};
  const totalComms = (stats.calls || 0) + (stats.messages || 0) + (stats.emails || 0);
  const isOverridden = !!report.device_name_override;

  return (
    <div className="bg-white border border-light-200 rounded-lg shadow-sm hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="p-4 border-b border-light-100 bg-gradient-to-r from-emerald-50 to-white">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center flex-shrink-0">
            <Smartphone className="w-5 h-5 text-emerald-600" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <h3 className="text-sm font-semibold text-owl-blue-900 truncate">
                {report.device_model || 'Unknown Device'}
              </h3>
              {isOverridden && (
                <span
                  className="text-[9px] uppercase tracking-wide bg-amber-100 text-amber-800 px-1 py-px rounded"
                  title="Investigator-supplied name; click pencil to edit"
                >
                  Custom
                </span>
              )}
              {onEditName && (
                <button
                  onClick={onEditName}
                  className="p-0.5 text-light-400 hover:text-owl-blue-600 rounded"
                  title="Edit device name"
                >
                  <Pencil className="w-3 h-3" />
                </button>
              )}
            </div>
            {report.phone_owner_name && (
              <div className="flex items-center gap-1 mt-0.5">
                <User className="w-3 h-3 text-light-500" />
                <span className="text-xs text-light-600 truncate">
                  {report.phone_owner_name}
                </span>
              </div>
            )}
          </div>
          {onDelete && (
            <button
              onClick={onDelete}
              className="p-1 text-light-400 hover:text-red-600 rounded"
              title="Delete this phone report"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Device Info */}
      <div className="p-4 space-y-2">
        {report.phone_numbers && (
          <InfoRow icon={Phone} label="Phone" value={report.phone_numbers} />
        )}
        {report.imei && (
          <InfoRow icon={Hash} label="IMEI" value={report.imei} />
        )}
        {report.extraction_type && (
          <InfoRow icon={Shield} label="Extraction" value={report.extraction_type} />
        )}
        {report.case_number && (
          <InfoRow icon={Hash} label="Case #" value={report.case_number} />
        )}
        {report.examiner && (
          <InfoRow icon={User} label="Examiner" value={report.examiner} />
        )}
      </div>

      {/* Stats — clickable */}
      <div className="px-4 pb-4">
        <div className="grid grid-cols-3 gap-2">
          <StatBadge
            icon={User}
            count={stats.contacts || 0}
            label="Contacts"
            color="blue"
            onClick={() => onDrillDown('contacts')}
          />
          <StatBadge
            icon={Phone}
            count={stats.calls || 0}
            label="Calls"
            color="green"
            onClick={() => onDrillDown('calls')}
          />
          <StatBadge
            icon={MessageSquare}
            count={stats.messages || 0}
            label="Messages"
            color="purple"
            onClick={() => onDrillDown('messages')}
          />
          <StatBadge
            icon={MapPin}
            count={stats.locations || 0}
            label="Locations"
            color="orange"
            onClick={() => onDrillDown('locations')}
          />
          <StatBadge
            icon={Mail}
            count={stats.emails || 0}
            label="Emails"
            color="red"
            onClick={() => onDrillDown('emails')}
          />
          <StatBadge
            icon={MessageSquare}
            count={totalComms}
            label="Total Comms"
            color="emerald"
          />
        </div>
      </div>

      {/* Ingestion reconciliation: surfaced only when present, prominent
          only when something looks wrong. Lets the investigator confirm we
          processed everything Cellebrite reported, or spot a gap. */}
      {report.reconciliation && (
        <ReconciliationPanel reconciliation={report.reconciliation} />
      )}
    </div>
  );
}

/**
 * Compact per-card panel comparing Cellebrite XML model counts against the
 * counts persisted to Neo4j. Defaults to collapsed; always-visible if any
 * row has status="under" or "not_supported".
 */
function ReconciliationPanel({ reconciliation }) {
  const summary = reconciliation?.summary || {};
  const rows = Array.isArray(reconciliation?.rows) ? reconciliation.rows : [];

  const hasIssues = (summary.types_under || 0) > 0;
  const hasUnknown = (summary.types_not_supported || 0) > 0;
  // Default-open when there's something the investigator should look at.
  const [open, setOpen] = useState(hasIssues);

  if (rows.length === 0) return null;

  const totalXml = summary.total_xml_models || 0;

  return (
    <div className="border-t border-light-100 px-4 py-2 text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 text-left text-light-600 hover:text-owl-blue-700"
      >
        <span className="flex items-center gap-1.5">
          {hasIssues ? (
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          )}
          <span className="font-medium">
            {hasIssues
              ? `Reconciliation: ${summary.types_under} type${summary.types_under === 1 ? '' : 's'} under-persisted`
              : 'Reconciliation: all counts match'}
          </span>
          <span className="text-light-400">
            ({totalXml.toLocaleString()} XML models, {rows.length} types)
          </span>
        </span>
        {open ? (
          <ChevronDown className="w-3.5 h-3.5 text-light-400" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-light-400" />
        )}
      </button>

      {open && (
        <div className="mt-2 max-h-48 overflow-y-auto rounded border border-light-100">
          <table className="w-full text-[11px]">
            <thead className="bg-light-50 text-light-500">
              <tr>
                <th className="text-left px-2 py-1 font-medium">Model type</th>
                <th className="text-right px-2 py-1 font-medium">XML</th>
                <th className="text-right px-2 py-1 font-medium">Persisted</th>
                <th className="text-left px-2 py-1 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <ReconciliationRow key={r.model_type} row={r} />
              ))}
            </tbody>
          </table>
          {hasUnknown && (
            <div className="px-2 py-1 text-[10px] text-light-500 bg-light-50 border-t border-light-100">
              "Not supported" types are present in the XML but the parser
              has no writer for them yet. They are recorded for visibility
              and can be added later if useful.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const STATUS_STYLE = {
  ok:           { label: 'ok',            cls: 'text-emerald-700 bg-emerald-50' },
  nested:       { label: 'nested',        cls: 'text-owl-blue-700 bg-owl-blue-50' },
  skipped:      { label: 'skipped',       cls: 'text-light-500 bg-light-50' },
  under:        { label: 'under',         cls: 'text-amber-800 bg-amber-50' },
  not_supported:{ label: 'not supported', cls: 'text-light-500 bg-light-50' },
};

function ReconciliationRow({ row }) {
  const style = STATUS_STYLE[row.status] || STATUS_STYLE.ok;
  return (
    <tr className="border-t border-light-100">
      <td className="px-2 py-1 text-owl-blue-900 font-mono">{row.model_type}</td>
      <td className="px-2 py-1 text-right tabular-nums">
        {row.xml_count.toLocaleString()}
      </td>
      <td className="px-2 py-1 text-right tabular-nums">
        {row.persisted_count.toLocaleString()}
      </td>
      <td className="px-2 py-1">
        <span className={`px-1.5 py-px rounded text-[10px] uppercase tracking-wide ${style.cls}`}>
          {style.label}
        </span>
      </td>
    </tr>
  );
}

function InfoRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <Icon className="w-3 h-3 text-light-400 flex-shrink-0" />
      <span className="text-light-500 w-16 flex-shrink-0">{label}</span>
      <span className="text-owl-blue-900 truncate">{value}</span>
    </div>
  );
}

const colorMap = {
  blue: 'bg-owl-blue-50 text-owl-blue-700',
  green: 'bg-green-50 text-green-700',
  purple: 'bg-purple-50 text-purple-700',
  orange: 'bg-orange-50 text-orange-700',
  red: 'bg-red-50 text-red-700',
  emerald: 'bg-emerald-50 text-emerald-700',
};

function StatBadge({ icon: Icon, count, label, color, onClick }) {
  const base = `rounded p-2 text-center transition-all ${colorMap[color] || colorMap.blue}`;
  if (onClick) {
    return (
      <button
        onClick={onClick}
        className={`${base} cursor-pointer hover:shadow-sm hover:ring-2 hover:ring-current/20 active:scale-[0.98]`}
        title={`Browse all ${count.toLocaleString()} ${label.toLowerCase()}`}
      >
        <div className="text-sm font-semibold">{count.toLocaleString()}</div>
        <div className="text-[10px] opacity-75">{label} ›</div>
      </button>
    );
  }
  return (
    <div className={base}>
      <div className="text-sm font-semibold">{count.toLocaleString()}</div>
      <div className="text-[10px] opacity-75">{label}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modals
// ---------------------------------------------------------------------------

function DeleteConfirmModal({ report, onCancel, onConfirm, deleting, error }) {
  const stats = report.stats || {};
  const total =
    (stats.contacts || 0) +
    (stats.calls || 0) +
    (stats.messages || 0) +
    (stats.locations || 0) +
    (stats.emails || 0);

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-5">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center flex-shrink-0">
            <Trash2 className="w-5 h-5 text-red-600" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-semibold text-owl-blue-900">
              Delete phone report?
            </h2>
            <p className="text-sm text-light-700 mt-1">
              This will remove <span className="font-semibold">
                {report.device_model || 'Unknown Device'}
                {report.phone_owner_name ? ` · ${report.phone_owner_name}` : ''}
              </span> and all of its data from this case
              {total > 0 && <> ({total.toLocaleString()} entities across contacts, calls, messages, locations and emails)</>}.
              <br />
              <span className="text-red-700 font-medium">This cannot be undone.</span>
            </p>
            {error && (
              <div className="mt-3 text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1.5">
                {error}
              </div>
            )}
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onCancel}
            disabled={deleting}
            className="px-3 py-1.5 text-xs font-medium border border-light-300 text-light-700 rounded hover:bg-light-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            className="px-3 py-1.5 text-xs font-medium bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            {deleting && <Loader2 className="w-3 h-3 animate-spin" />}
            {deleting ? 'Deleting…' : 'Delete phone report'}
          </button>
        </div>
      </div>
    </div>
  );
}

function EditDeviceNameModal({ caseId, report, onClose, onSaved }) {
  const detected =
    [report.manufacturer, report.detected_device_model].filter(Boolean).join(' ') ||
    report.detected_device_model ||
    '';
  const candidates = Array.isArray(report.device_name_candidates)
    ? report.device_name_candidates
    : [];
  const [value, setValue] = useState(report.device_name_override || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const save = async (override) => {
    setSaving(true);
    setError(null);
    try {
      await cellebriteAPI.patchReport(caseId, report.report_key, {
        device_name_override: override,
      });
      if (onSaved) await onSaved();
    } catch (err) {
      setError(err?.message || 'Failed to update device name');
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-5">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h2 className="text-base font-semibold text-owl-blue-900">
              Edit device name
            </h2>
            <p className="text-xs text-light-500 mt-0.5">
              Detected: <span className="font-medium text-light-700">{detected || '—'}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={saving}
            className="p-1 text-light-400 hover:text-light-700 rounded"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {candidates.length > 0 && (
          <div className="mb-3">
            <div className="text-[11px] font-medium uppercase tracking-wide text-light-500 mb-1.5">
              Detected candidates
            </div>
            <div className="flex flex-wrap gap-1">
              {candidates.map((c, i) => (
                <button
                  key={`${c.source}-${i}`}
                  onClick={() => setValue(c.value)}
                  className={`text-xs px-2 py-1 rounded border transition-colors ${
                    value === c.value
                      ? 'bg-owl-blue-50 border-owl-blue-400 text-owl-blue-800'
                      : 'bg-white border-light-300 text-light-700 hover:bg-light-50'
                  }`}
                  title={`Source: ${c.source}${c.extraction_id ? ` (extraction ${c.extraction_id})` : ''}`}
                >
                  {c.value}
                  {value === c.value && <Check className="w-3 h-3 inline ml-1" />}
                </button>
              ))}
            </div>
          </div>
        )}

        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-light-500">
            Custom name
          </label>
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="e.g. Brayan's iPhone 13 mini"
            disabled={saving}
            className="mt-1 w-full px-2 py-1.5 text-sm border border-light-300 rounded focus:outline-none focus:border-owl-blue-400 disabled:opacity-50"
          />
        </div>

        {error && (
          <div className="mt-3 text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1.5">
            {error}
          </div>
        )}

        <div className="flex justify-between items-center mt-5">
          <button
            onClick={() => save(null)}
            disabled={saving || !report.device_name_override}
            className="text-xs text-light-600 hover:text-owl-blue-700 underline disabled:opacity-40 disabled:no-underline"
            title="Clear the custom name and revert to the detected one"
          >
            Reset to detected
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              disabled={saving}
              className="px-3 py-1.5 text-xs font-medium border border-light-300 text-light-700 rounded hover:bg-light-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={() => save(value.trim() || null)}
              disabled={saving}
              className="px-3 py-1.5 text-xs font-medium bg-owl-blue-600 text-white rounded hover:bg-owl-blue-700 disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              {saving && <Loader2 className="w-3 h-3 animate-spin" />}
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
