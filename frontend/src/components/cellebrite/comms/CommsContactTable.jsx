/**
 * CommsContactTable
 *
 * Flat row-per-event table view of the contact's cross-device feed.
 * Sibling to CommsContactFeed's chat-bubble layout — same data
 * (`/comms/contact-feed` items), different rendering. Mounted by
 * `CommsContactFeed` when the user picks the Table view-mode toggle.
 *
 * Columns:
 *   Type · Time · App · From · To · Subject / Body · Direction · Phone
 *
 * Cell behaviour (per the user-approved interaction model):
 *   - Names (sender / recipient) → drill into that Person.
 *     Hands off to `onDrillName(personKey, name)` provided by the
 *     parent CellebriteCommunicationView, which pushes a new frame.
 *   - Non-name cells (app, type, direction, date) → in-table filter
 *     that narrows the visible rows without leaving the drill. The
 *     filter chip strip above the table shows active filters; clicking
 *     a chip clears it.
 *   - Body / Subject cells are not directly clickable — clicking the
 *     row opens the rail.
 *
 * Performance:
 *   - Pure render against the already-filtered items array passed in.
 *     The parent (CommsContactFeed) applies the search filter; this
 *     table only paginates / sorts within the already-narrowed set.
 *   - Up to ~2000 rows render fine without virtualisation.
 */

import React, { useMemo, useState } from 'react';
import {
  Phone, MessageSquare, Mail, PhoneIncoming, PhoneOutgoing, PhoneMissed,
  ArrowUpDown, X,
} from 'lucide-react';
import PhoneIdentityChip from '../shared/PhoneIdentityChip';
import HighlightedText from '../shared/HighlightedText';
import { usePhoneReports } from '../../../context/PhoneReportsContext';
import { useCellebriteSelection } from '../shared/CellebriteSelectionContext';

const TYPE_META = {
  call:    { icon: Phone,         color: 'text-emerald-600', label: 'Call'    },
  message: { icon: MessageSquare, color: 'text-owl-blue-600', label: 'Message' },
  email:   { icon: Mail,          color: 'text-amber-600',    label: 'Email'   },
};

export default function CommsContactTable({
  items,           // pre-filtered comms feed items
  caseId,
  onDrillName,     // (personKey, name) -> push a new drill frame
  highlights = [], // search highlights (for HighlightedText)
  // In-table filter state lives in the parent so it persists across
  // toggling between chat and table modes. The parent provides both
  // the active filter set and the setter.
  cellFilters,     // { app: '…', type: '…', direction: '…', date: '2022-12-03' } | null
  onCellFiltersChange,
}) {
  const phoneCtx = usePhoneReports();
  const { selectEntity } = useCellebriteSelection();
  const [sort, setSort] = useState({ key: 'timestamp', dir: 'desc' });

  const sortedItems = useMemo(() => {
    const arr = items ? [...items] : [];
    arr.sort((a, b) => {
      const av = pickSortValue(a, sort.key);
      const bv = pickSortValue(b, sort.key);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return sort.dir === 'asc' ? -1 : 1;
      if (av > bv) return sort.dir === 'asc' ? 1 : -1;
      return 0;
    });
    return arr;
  }, [items, sort]);

  const toggleSort = (key) => {
    setSort((prev) => {
      if (prev.key !== key) return { key, dir: 'desc' };
      return { key, dir: prev.dir === 'desc' ? 'asc' : 'desc' };
    });
  };

  const setFilter = (key, value) => {
    if (!onCellFiltersChange) return;
    onCellFiltersChange({ ...(cellFilters || {}), [key]: value });
  };

  const clearFilter = (key) => {
    if (!onCellFiltersChange) return;
    const next = { ...(cellFilters || {}) };
    delete next[key];
    onCellFiltersChange(next);
  };

  const onRowClick = (item) => {
    selectEntity({
      type: item.type || 'message',
      id: item.id || item.key,
      caseId,
      reportKey: item.report_key,
      payload: {
        ...item,
        node_key: item.key || item.id,
        event_type: item.type,
        label:
          item.type === 'email'
            ? (item.subject || '(no subject)')
            : item.type === 'call'
              ? `${item.sender?.name || 'Unknown'} → ${item.recipients?.[0]?.name || 'Unknown'}`
              : (item.body || '(message)').slice(0, 80),
      },
      source: 'communications.drill.table',
    });
  };

  const hasActiveFilters = cellFilters && Object.keys(cellFilters).length > 0;
  const hasMultiplePhones = !!phoneCtx?.hasMultiple;

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* In-table filter chip strip — shows what's narrowing the table
          right now and offers single-click clearing. */}
      {hasActiveFilters && (
        <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-light-200 bg-amber-50 text-[11px] flex-wrap flex-shrink-0">
          <span className="text-amber-700 font-semibold uppercase tracking-wide text-[10px]">
            In-table filters:
          </span>
          {Object.entries(cellFilters).map(([k, v]) => (
            <button
              key={k}
              type="button"
              onClick={() => clearFilter(k)}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-100 border border-amber-200 text-amber-900 hover:bg-amber-200"
              title={`Clear ${k} filter`}
            >
              <span className="font-medium">{k}</span>=<span className="font-mono">{v}</span>
              <X className="w-2.5 h-2.5" />
            </button>
          ))}
          <button
            type="button"
            onClick={() => onCellFiltersChange && onCellFiltersChange({})}
            className="text-amber-700 hover:text-amber-900 underline ml-1"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto min-h-0">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-light-50 z-10">
            <tr className="border-b border-light-200">
              <Th label="Type"      sortKey="type"      sort={sort} onSort={toggleSort} />
              <Th label="Time"      sortKey="timestamp" sort={sort} onSort={toggleSort} />
              <Th label="App"       sortKey="source_app" sort={sort} onSort={toggleSort} />
              <Th label="From"      sortKey="sender"    sort={sort} onSort={toggleSort} />
              <Th label="To"        sortKey="recipient" sort={sort} onSort={toggleSort} />
              <Th label="Body / Subject" sortKey="body" sort={sort} onSort={toggleSort} className="text-left" />
              <Th label="Direction" sortKey="direction" sort={sort} onSort={toggleSort} />
              {hasMultiplePhones && <Th label="Phone" sortKey="report_key" sort={sort} onSort={toggleSort} />}
            </tr>
          </thead>
          <tbody>
            {sortedItems.map((item, idx) => (
              <Row
                key={item.id || idx}
                item={item}
                onRowClick={onRowClick}
                onDrillName={onDrillName}
                onApplyFilter={setFilter}
                highlights={highlights}
                hasMultiplePhones={hasMultiplePhones}
              />
            ))}
            {sortedItems.length === 0 && (
              <tr>
                <td colSpan={hasMultiplePhones ? 8 : 7} className="px-3 py-8 text-center text-light-400 italic">
                  No comms match the current filters
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ─────────────────────────── Sub-components ─────────────────────────── */

function Th({ label, sortKey, sort, onSort, className = '' }) {
  const active = sort?.key === sortKey;
  return (
    <th
      onClick={() => onSort(sortKey)}
      className={`px-2 py-1.5 font-medium text-light-600 cursor-pointer hover:bg-light-100 select-none whitespace-nowrap text-left ${className}`}
    >
      <span className="inline-flex items-center gap-0.5">
        {label}
        <ArrowUpDown className={`w-3 h-3 ${active ? 'text-emerald-600' : 'text-light-300'}`} />
        {active && (
          <span className="text-[9px] text-light-400">
            {sort.dir === 'desc' ? '↓' : '↑'}
          </span>
        )}
      </span>
    </th>
  );
}

function Row({ item, onRowClick, onDrillName, onApplyFilter, highlights, hasMultiplePhones }) {
  const meta = TYPE_META[item.type] || TYPE_META.message;
  const Icon = meta.icon;
  const sender = item.sender;
  const recipients = item.recipients || [];
  const primaryRecipient = recipients[0];
  const date = (item.timestamp || '').slice(0, 10);

  // Direction icon for calls.
  const DirIcon = pickDirectionIcon(item);

  // Composite preview: subject for email, otherwise body. Truncated to
  // keep rows scannable; the row click opens the rail with the full
  // content.
  const preview = item.type === 'email'
    ? (item.subject || '(no subject)')
    : (item.body || '');

  return (
    <tr
      onClick={() => onRowClick(item)}
      className="border-b border-light-100 hover:bg-light-50 cursor-pointer group align-top"
    >
      {/* Type — clickable to filter the table to that event type. */}
      <Td>
        <ClickableCell
          onClick={(e) => { e.stopPropagation(); onApplyFilter('type', item.type); }}
          title={`Filter to ${meta.label}s only`}
        >
          <Icon className={`w-3 h-3 ${meta.color}`} />
          <span>{meta.label}</span>
        </ClickableCell>
      </Td>

      {/* Time — clickable to filter to that date. */}
      <Td>
        <ClickableCell
          onClick={(e) => { e.stopPropagation(); onApplyFilter('date', date); }}
          title={`Filter to ${date}`}
        >
          <span className="tabular-nums text-light-700">
            <HighlightedText text={formatTime(item.timestamp)} highlights={highlights} />
          </span>
        </ClickableCell>
      </Td>

      {/* App — clickable to filter to that app. */}
      <Td>
        {item.source_app ? (
          <ClickableCell
            onClick={(e) => { e.stopPropagation(); onApplyFilter('app', item.source_app); }}
            title={`Filter to ${item.source_app} only`}
          >
            <HighlightedText text={item.source_app} highlights={highlights} />
          </ClickableCell>
        ) : <span className="text-light-400">—</span>}
      </Td>

      {/* From — clickable to drill into that person. */}
      <Td>
        <PersonCell person={sender} onDrillName={onDrillName} highlights={highlights} />
      </Td>

      {/* To — first recipient as a clickable name + +N more chip. */}
      <Td>
        {primaryRecipient ? (
          <span className="inline-flex items-center gap-1">
            <PersonCell person={primaryRecipient} onDrillName={onDrillName} highlights={highlights} />
            {recipients.length > 1 && (
              <span className="text-[10px] text-light-400">+{recipients.length - 1}</span>
            )}
          </span>
        ) : <span className="text-light-400">—</span>}
      </Td>

      {/* Body / Subject — read-only preview, click row to open in rail. */}
      <Td className="max-w-[420px]">
        <span className="text-light-700 truncate block" title={preview}>
          <HighlightedText text={truncate(preview, 160)} highlights={highlights} />
        </span>
      </Td>

      {/* Direction — clickable to filter (Incoming / Outgoing). */}
      <Td>
        {item.direction ? (
          <ClickableCell
            onClick={(e) => { e.stopPropagation(); onApplyFilter('direction', item.direction); }}
            title={`Filter to ${item.direction} only`}
          >
            {DirIcon && <DirIcon className="w-3 h-3 text-light-500" />}
            <span>{item.direction}</span>
          </ClickableCell>
        ) : <span className="text-light-400">—</span>}
      </Td>

      {hasMultiplePhones && (
        <Td>
          {item.report_key ? (
            <PhoneIdentityChip reportKey={item.report_key} variant="dense" />
          ) : <span className="text-light-400">—</span>}
        </Td>
      )}
    </tr>
  );
}

function Td({ children, className = '' }) {
  return <td className={`px-2 py-1.5 ${className}`}>{children}</td>;
}

function ClickableCell({ children, onClick, title }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="inline-flex items-center gap-1 px-1 py-0.5 rounded hover:bg-light-200 hover:text-owl-blue-700 transition-colors text-light-700 max-w-full"
    >
      {children}
    </button>
  );
}

/**
 * Renders a person name with click-to-drill. Stops row-click propagation
 * so clicking the name *only* triggers the drill (not the rail open).
 *
 * Names with no person_key (e.g. unresolved counterparties on calls that
 * lost their Person edge during ingest) render as static text so we
 * don't suggest an action we can't fulfil.
 */
function PersonCell({ person, onDrillName, highlights }) {
  if (!person) return <span className="text-light-400">—</span>;
  const name = person.name || person.identifier || person.key || '?';
  const personKey = person.key;
  if (!personKey || !onDrillName) {
    return (
      <span className="text-light-700 truncate" title={name}>
        <HighlightedText text={name} highlights={highlights} />
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onDrillName(personKey, name); }}
      title={`Drill into ${name}'s communications`}
      className="text-owl-blue-700 hover:text-owl-blue-900 hover:underline font-medium truncate max-w-[180px] text-left"
    >
      <HighlightedText text={name} highlights={highlights} />
    </button>
  );
}

/* ─────────────────────────── Helpers ─────────────────────────── */

function pickSortValue(item, key) {
  switch (key) {
    case 'timestamp': return item.timestamp || '';
    case 'type':      return item.type || '';
    case 'source_app': return (item.source_app || '').toLowerCase();
    case 'sender':    return (item.sender?.name || '').toLowerCase();
    case 'recipient': return (item.recipients?.[0]?.name || '').toLowerCase();
    case 'body':      return (item.body || item.subject || '').toLowerCase();
    case 'direction': return (item.direction || '').toLowerCase();
    case 'report_key': return item.report_key || '';
    default:          return item[key];
  }
}

function pickDirectionIcon(item) {
  if (item.type !== 'call') return null;
  const d = (item.direction || '').toLowerCase();
  const t = (item.call_type_display || item.call_type || '').toLowerCase();
  if (t === 'missed' || t === 'cancelled' || t === 'rejected' || d.includes('miss')) {
    return PhoneMissed;
  }
  if (d.includes('incoming')) return PhoneIncoming;
  if (d.includes('outgoing')) return PhoneOutgoing;
  return null;
}

function formatTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return iso;
  }
}

function truncate(s, n) {
  if (!s) return '';
  return s.length > n ? `${s.slice(0, n)}…` : s;
}
