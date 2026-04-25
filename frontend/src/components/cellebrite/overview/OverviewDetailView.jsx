import React, { useEffect, useMemo, useState, useRef, useCallback } from 'react';
import { ArrowLeft, ArrowUp, ArrowDown, Search, Loader2, Smartphone, User } from 'lucide-react';
import {
  ROW_HEIGHT,
  HEADER_HEIGHT,
  FOOTER_HEIGHT,
  useTableWindow,
  sortRows,
} from './overviewTableUtils';

/**
 * Shared shell for all Cellebrite Overview drill-down detail views.
 *
 * Owns: header (back button, device chip, title, count, search), virtualised
 * sortable table, footer. Categories pass in their column defs + fetch fn +
 * row click handler.
 *
 * Props:
 *   report            — the full report object (for the device chip)
 *   title             — "Calls", "Messages", etc.
 *   icon              — lucide icon for the title
 *   color             — tailwind color slug for the title accent
 *   onBack            — () => void
 *   columns           — [{ key, label, width, render(row), sortable=true, align? }]
 *   defaultSort       — { key, dir }
 *   fetchPage         — (caseId, reportKey, { search, limit, offset }) => Promise<{rows, total}>
 *   caseId
 *   onRowClick        — (row) => void
 */
export default function OverviewDetailView({
  report,
  title,
  icon: Icon,
  color = 'emerald',
  onBack,
  columns = [],
  defaultSort = { key: 'timestamp', dir: 'desc' },
  fetchPage,
  caseId,
  onRowClick,
}) {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sort, setSort] = useState(defaultSort);

  // Debounce search input (300ms)
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  // Fetch when filters / device change
  useEffect(() => {
    if (!report?.report_key || !caseId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPage(caseId, report.report_key, {
      search: debouncedSearch || null,
      limit: 1000,
      offset: 0,
    })
      .then((data) => {
        if (cancelled) return;
        setRows(data.rows || []);
        setTotal(data.total || 0);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setRows([]);
        setError(err.message || 'Failed to load');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, report?.report_key, debouncedSearch, fetchPage]);

  // Sort
  const sortedRows = useMemo(() => sortRows(rows, sort.key, sort.dir), [rows, sort]);
  const totalRows = sortedRows.length;
  const { bodyRef, startIdx, endIdx, totalHeight, onScroll } = useTableWindow(totalRows);
  const visibleRows = sortedRows.slice(startIdx, endIdx);

  const toggleSort = useCallback(
    (key) => {
      setSort((prev) =>
        prev.key === key
          ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
          : { key, dir: 'desc' }
      );
    },
    []
  );

  // Build the gridTemplateColumns string from column widths
  const gridTemplate = useMemo(
    () => columns.map((c) => c.width || 'minmax(120px, 1fr)').join(' '),
    [columns]
  );

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
        <button
          onClick={onBack}
          className="flex items-center gap-1 px-2 py-1 text-xs text-light-700 hover:text-owl-blue-700 hover:bg-light-100 rounded"
          title="Back to overview"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back
        </button>

        <div className="flex items-center gap-2 px-2 py-1 bg-emerald-50 border border-emerald-200 rounded">
          <Smartphone className="w-3 h-3 text-emerald-700" />
          <span className="text-xs font-medium text-emerald-900">
            {report?.device_model || 'Device'}
          </span>
          {report?.phone_owner_name && (
            <>
              <span className="text-emerald-300">·</span>
              <User className="w-3 h-3 text-emerald-700" />
              <span className="text-xs text-emerald-800">{report.phone_owner_name}</span>
            </>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {Icon && <Icon className={`w-4 h-4 text-${color}-600`} />}
          <span className="text-sm font-semibold text-owl-blue-900">{title}</span>
          <span className="text-xs text-light-500">
            ({total.toLocaleString()})
          </span>
        </div>

        <div className="relative flex-1 max-w-md ml-2">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="w-full pl-7 pr-2 py-1 text-xs border border-light-300 rounded focus:outline-none focus:border-owl-blue-400"
          />
        </div>

        <div className="flex-1" />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-light-400" />}
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>

      {/* Column header */}
      <div
        className="grid border-b border-light-200 bg-light-50 text-[11px] font-semibold text-light-700 flex-shrink-0"
        style={{ gridTemplateColumns: gridTemplate, height: HEADER_HEIGHT }}
      >
        {columns.map((c) => (
          <button
            key={c.key}
            onClick={() => (c.sortable !== false ? toggleSort(c.key) : null)}
            className={`flex items-center gap-1 px-2 border-r border-light-200 hover:bg-light-100 ${
              c.align === 'right' ? 'justify-end' : 'justify-start'
            } ${sort.key === c.key ? 'text-owl-blue-700' : 'text-light-700'} ${
              c.sortable === false ? 'cursor-default' : ''
            }`}
          >
            <span className="truncate">{c.label}</span>
            {sort.key === c.key && (sort.dir === 'asc' ? <ArrowUp className="w-2.5 h-2.5" /> : <ArrowDown className="w-2.5 h-2.5" />)}
          </button>
        ))}
      </div>

      {/* Body */}
      <div ref={bodyRef} onScroll={onScroll} className="flex-1 min-h-0 overflow-auto relative">
        {totalRows === 0 ? (
          <div className="flex items-center justify-center h-full text-sm text-light-500 italic">
            {loading ? 'Loading…' : 'No items found.'}
          </div>
        ) : (
          <div style={{ height: totalHeight, position: 'relative' }}>
            {visibleRows.map((row, i) => {
              const idx = startIdx + i;
              const top = idx * ROW_HEIGHT;
              return (
                <div
                  key={row.key || row.id || idx}
                  className="grid absolute inset-x-0 items-center border-b border-light-100 cursor-pointer hover:bg-owl-blue-50"
                  style={{
                    top,
                    height: ROW_HEIGHT,
                    gridTemplateColumns: gridTemplate,
                  }}
                  onClick={() => onRowClick?.(row)}
                >
                  {columns.map((c) => (
                    <div
                      key={c.key}
                      className={`px-2 border-r border-light-100 truncate text-xs text-light-800 ${
                        c.align === 'right' ? 'text-right' : ''
                      }`}
                    >
                      {c.render ? c.render(row) : (row[c.key] != null ? String(row[c.key]) : '—')}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-between px-3 text-[10px] text-light-500 border-t border-light-200 bg-light-50 flex-shrink-0"
        style={{ height: FOOTER_HEIGHT }}
      >
        <span>
          Showing {totalRows.toLocaleString()} of {total.toLocaleString()}
        </span>
        <span>
          Sorted by {sort.key} {sort.dir === 'asc' ? '↑' : '↓'}
        </span>
      </div>
    </div>
  );
}
