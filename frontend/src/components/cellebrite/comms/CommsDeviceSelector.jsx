import React from 'react';
import { Smartphone, Check } from 'lucide-react';

/**
 * Renders a horizontal strip of device chips. Each chip represents a PhoneReport
 * (one device) and can be toggled on/off. The "All" chip selects/deselects every
 * device. When there is only one report we render nothing (no need to filter).
 *
 * Props:
 *  - reports: array of report objects from cellebriteAPI.getReports
 *  - selectedReportKeys: Set<string>
 *  - onToggle: (key: string) => void
 *  - onSelectAll: () => void
 *  - onClear: () => void
 */
export default function CommsDeviceSelector({
  reports = [],
  selectedReportKeys,
  onToggle,
  onSelectAll,
  onClear,
}) {
  if (!reports || reports.length <= 1) {
    return null;
  }

  const total = reports.length;
  const selectedCount = selectedReportKeys.size;
  const allSelected = selectedCount === total;
  const noneSelected = selectedCount === 0;

  return (
    <div className="flex items-center gap-2 px-4 py-2 border-b border-light-200 bg-light-50 flex-shrink-0 overflow-x-auto">
      <div className="flex items-center gap-1.5 text-xs text-light-600 flex-shrink-0">
        <Smartphone className="w-3.5 h-3.5" />
        <span className="font-medium">Devices:</span>
      </div>

      <button
        onClick={allSelected ? onClear : onSelectAll}
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors flex-shrink-0 ${
          allSelected
            ? 'bg-emerald-100 border-emerald-400 text-emerald-800'
            : noneSelected
            ? 'bg-light-100 border-light-300 text-light-600 hover:bg-light-200'
            : 'bg-owl-blue-50 border-owl-blue-300 text-owl-blue-800 hover:bg-owl-blue-100'
        }`}
        title={allSelected ? 'Deselect all devices' : 'Select all devices'}
      >
        {allSelected && <Check className="w-3 h-3" />}
        All ({total})
      </button>

      {reports.map((r) => {
        const active = selectedReportKeys.has(r.report_key);
        const total = (r.stats?.calls || 0) + (r.stats?.messages || 0) + (r.stats?.emails || 0);
        return (
          <button
            key={r.report_key}
            onClick={() => onToggle(r.report_key)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors flex-shrink-0 ${
              active
                ? 'bg-emerald-100 border-emerald-400 text-emerald-800'
                : 'bg-white border-light-300 text-light-600 hover:bg-light-100'
            }`}
            title={`${r.device_model} — ${r.phone_owner_name || 'Unknown owner'}\n${total.toLocaleString()} comms`}
          >
            {active && <Check className="w-3 h-3" />}
            <Smartphone className="w-3 h-3" />
            <span className="truncate max-w-[180px]">
              {r.device_model}
              {r.phone_owner_name ? ` · ${r.phone_owner_name}` : ''}
            </span>
          </button>
        );
      })}
    </div>
  );
}
