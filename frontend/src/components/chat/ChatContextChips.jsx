import React from 'react';
import { X, Target, Eye, EyeOff } from 'lucide-react';

/**
 * Renders a row of chips above the chat input showing the view-aware context:
 *   - Which view is active (e.g. "Financial view")
 *   - Each applied filter as a removable pill
 *   - Row counts ("7 rows · of 1,247 total")
 *   - Selection count ("3 selected")
 *   - An "Include in chat" toggle to opt out of view-aware context.
 *
 * Props:
 *   ctx               — the current ChatContext state
 *   includeInChat     — whether view context will be sent with chat requests
 *   onToggleInclude   — () => void
 *   onRemoveFilter    — (key: string) => void
 */
export default function ChatContextChips({ ctx, includeInChat, onToggleInclude, onRemoveFilter }) {
  if (!ctx?.viewType) return null;

  const filterEntries = Object.entries(ctx.filters || {});
  const hasFilters = filterEntries.length > 0;
  const selectionCount = ctx.selectionIds?.length || 0;
  const totalRows = ctx.totalMatching || ctx.resultIds?.length || 0;
  const previewRows = ctx.resultPreview?.length || 0;

  return (
    <div
      className={`flex items-center gap-1 flex-wrap px-3 py-1.5 border-b border-light-200 text-xs ${
        includeInChat ? 'bg-owl-blue-50/60' : 'bg-light-50'
      }`}
    >
      {/* View label */}
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-owl-blue-100 text-owl-blue-800 border border-owl-blue-200 font-medium">
        <Target className="w-3 h-3" />
        {ctx.viewLabel || ctx.viewType}
      </span>

      {/* Filters */}
      {hasFilters &&
        filterEntries.map(([key, val]) => {
          const label = ctx.filterLabels?.[key] || key;
          const display = formatFilterValue(val);
          if (!display) return null;
          return (
            <span
              key={key}
              className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-white border border-light-300 text-light-700"
              title={`${label}: ${display}`}
            >
              <span className="text-light-500">{label}:</span>
              <span className="max-w-[160px] truncate">{display}</span>
              {onRemoveFilter && (
                <button
                  onClick={() => onRemoveFilter(key)}
                  className="opacity-60 hover:opacity-100"
                  title={`Remove ${label} from context`}
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              )}
            </span>
          );
        })}

      {/* Selection chip */}
      {selectionCount > 0 && (
        <span className="px-2 py-0.5 rounded-full bg-emerald-50 border border-emerald-300 text-emerald-800">
          {selectionCount} selected
        </span>
      )}

      {/* Row count chip */}
      {totalRows > 0 && (
        <span className="px-2 py-0.5 rounded-full bg-white border border-light-300 text-light-600">
          {previewRows < totalRows
            ? `showing ${previewRows.toLocaleString()} of ${totalRows.toLocaleString()} rows`
            : `${totalRows.toLocaleString()} row${totalRows === 1 ? '' : 's'}`}
        </span>
      )}

      <div className="flex-1" />

      {/* Include toggle */}
      <button
        onClick={onToggleInclude}
        className={`flex items-center gap-1 px-2 py-0.5 rounded-full border transition-colors ${
          includeInChat
            ? 'bg-emerald-100 border-emerald-400 text-emerald-800'
            : 'bg-white border-light-300 text-light-500'
        }`}
        title={
          includeInChat
            ? 'View context will be sent with the next question. Click to opt out.'
            : 'View context is disabled. Click to include it in the next question.'
        }
      >
        {includeInChat ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
        {includeInChat ? 'In context' : 'Ignoring view'}
      </button>
    </div>
  );
}

function formatFilterValue(val) {
  if (val === null || val === undefined) return '';
  if (typeof val === 'boolean') return val ? 'on' : 'off';
  if (Array.isArray(val)) {
    if (val.length === 0) return '';
    if (val.length <= 2) return val.join(', ');
    return `${val.slice(0, 2).join(', ')} +${val.length - 2}`;
  }
  if (typeof val === 'object') {
    try {
      return JSON.stringify(val);
    } catch {
      return String(val);
    }
  }
  return String(val);
}
