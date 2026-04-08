import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer, Cell,
} from 'recharts';
import {
  Search, X, ArrowUpDown, ArrowUp, ArrowDown,
  ArrowDownLeft, ArrowUpRight, Repeat, TrendingUp, Info,
} from 'lucide-react';

function formatCurrency(amount) {
  if (amount == null) return '$0.00';
  const absVal = Math.abs(amount);
  if (absVal >= 1_000_000) return `$${(absVal / 1_000_000).toFixed(2)}M`;
  if (absVal >= 1_000) return `$${(absVal / 1_000).toFixed(1)}K`;
  return `$${absVal.toFixed(2)}`;
}

function formatCompact(amount) {
  const abs = Math.abs(amount);
  if (abs >= 1_000_000) return `$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${(abs / 1_000).toFixed(1)}K`;
  return `$${abs.toFixed(0)}`;
}

/**
 * MoneyFlowSection
 *
 * Multi-select entity picker + perspective summary + divergent counterparty
 * bar chart. A transaction is in scope for this section iff any selected
 * entity appears in `from_entity` OR `to_entity`. Within the scope we split
 * into:
 *   - Inflow:   external → selected (money coming into the perspective set)
 *   - Outflow:  selected → external (money leaving the perspective set)
 *   - Internal: selected → selected (intra-set, counted once, not in chart)
 *
 * This is fundamentally different from the From/To cross-filter above it,
 * which is an AND over two orthogonal dimensions.
 */
export default function MoneyFlowSection({
  entityOptions,
  selectedEntities,
  onSelectionChange,
  summary,
  crossFilterOverlapCount = 0,
}) {
  const [search, setSearch] = useState('');
  const [sortField, setSortField] = useState('totalVolume');
  const [sortDir, setSortDir] = useState('desc');

  // Persistent name cache — survives base-filter changes so chips always have labels
  const nameCacheRef = useRef(new Map());
  useEffect(() => {
    entityOptions.forEach(e => nameCacheRef.current.set(e.key, e.name));
  }, [entityOptions]);

  const getEntityName = (key) => nameCacheRef.current.get(key) || key;

  const filtered = useMemo(() => {
    let list = entityOptions;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(e => e.name.toLowerCase().includes(q));
    }
    return [...list].sort((a, b) => {
      const mul = sortDir === 'asc' ? 1 : -1;
      if (sortField === 'name') return mul * a.name.localeCompare(b.name);
      if (sortField === 'asFrom') return mul * (a.asFromCount - b.asFromCount);
      if (sortField === 'asTo') return mul * (a.asToCount - b.asToCount);
      return mul * (a.totalVolume - b.totalVolume);
    });
  }, [entityOptions, search, sortField, sortDir]);

  const toggleSort = (field) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const toggleEntity = useCallback((key) => {
    onSelectionChange(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, [onSelectionChange]);

  const removeEntity = useCallback((key) => {
    onSelectionChange(prev => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
  }, [onSelectionChange]);

  const clearAll = useCallback(() => {
    onSelectionChange(() => new Set());
  }, [onSelectionChange]);

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <ArrowUpDown className="w-3 h-3 text-light-300" />;
    return sortDir === 'asc'
      ? <ArrowUp className="w-3 h-3 text-light-600" />
      : <ArrowDown className="w-3 h-3 text-light-600" />;
  };

  const hasSelection = selectedEntities.size > 0;

  // Build chart data: top 12 counterparties by absolute total. Outflow values
  // are stored as NEGATIVE so the bar extends to the left of zero.
  const chartData = useMemo(() => {
    if (!summary || !summary.counterparties) return [];
    const top = summary.counterparties.slice(0, 12);
    return top.map(c => ({
      name: c.name,
      inflow: c.inflow,
      outflow: -c.outflow, // negative so divergent chart extends leftward
      outflowDisplay: c.outflow,
      count: c.count,
    }));
  }, [summary]);

  const extraCounterparties = useMemo(() => {
    if (!summary || !summary.counterparties || summary.counterparties.length <= 12) return null;
    const extra = summary.counterparties.slice(12);
    const total = extra.reduce((s, c) => s + c.total, 0);
    return { count: extra.length, total };
  }, [summary]);

  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload || !payload.length) return null;
    const row = payload[0].payload;
    const net = row.inflow - row.outflowDisplay;
    return (
      <div className="bg-white border border-light-200 rounded shadow-sm text-[11px] p-2">
        <div className="font-medium text-light-800 mb-1 truncate max-w-[200px]">{row.name}</div>
        {row.inflow > 0 && (
          <div className="text-green-600">In: {formatCurrency(row.inflow)}</div>
        )}
        {row.outflowDisplay > 0 && (
          <div className="text-red-600">Out: {formatCurrency(row.outflowDisplay)}</div>
        )}
        <div className="text-light-600 border-t border-light-100 mt-1 pt-1">
          Net: <span className={net >= 0 ? 'text-green-600' : 'text-red-600'}>{net >= 0 ? '+' : '-'}{formatCurrency(net)}</span>
        </div>
        <div className="text-light-500 text-[10px]">{row.count} txn{row.count !== 1 ? 's' : ''}</div>
      </div>
    );
  };

  // ── Left-side entity picker ──
  const pickerBody = (
    <div className="flex flex-col min-w-0 border border-light-200 rounded-lg bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-light-100">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold text-owl-blue-700">Perspective Entities</span>
          <span className="text-[10px] text-light-400 bg-light-50 px-1.5 py-0.5 rounded-full">{entityOptions.length}</span>
        </div>
        {hasSelection && (
          <button
            onClick={clearAll}
            className="flex items-center gap-1 text-[10px] text-red-500 hover:text-red-700 px-1.5 py-0.5 rounded hover:bg-red-50 transition-colors"
          >
            <X className="w-3 h-3" />
            Clear all ({selectedEntities.size})
          </button>
        )}
      </div>

      {/* Selected entity chips */}
      {hasSelection && (
        <div className="px-2 py-1.5 border-b border-light-100 bg-owl-blue-50/50">
          <div className="flex flex-wrap gap-1">
            {[...selectedEntities].map(key => {
              const name = getEntityName(key);
              return (
                <span
                  key={key}
                  className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-owl-blue-100 text-owl-blue-700 max-w-[140px]"
                >
                  <span className="truncate">{name}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); removeEntity(key); }}
                    className="flex-shrink-0 p-0.5 rounded-full hover:bg-owl-blue-200 transition-colors"
                    title={`Remove ${name}`}
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Search */}
      <div className="px-2 py-1.5 border-b border-light-50">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-light-400" />
          <input
            type="text"
            placeholder="Search entities..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full text-[11px] pl-6 pr-6 py-1 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 text-light-400 hover:text-light-600"
            >
              <X className="w-2.5 h-2.5" />
            </button>
          )}
        </div>
      </div>

      {/* Column headers */}
      <div className="flex items-center text-[10px] text-light-500 font-medium border-b border-light-100 bg-light-25">
        <button
          onClick={() => toggleSort('name')}
          className="flex-1 min-w-0 flex items-center gap-1 px-2.5 py-1.5 hover:text-light-700 text-left"
        >
          Entity <SortIcon field="name" />
        </button>
        <button
          onClick={() => toggleSort('asFrom')}
          className="w-10 flex items-center justify-end gap-0.5 px-1 py-1.5 hover:text-light-700"
          title="Transactions where entity is the sender"
        >
          F <SortIcon field="asFrom" />
        </button>
        <button
          onClick={() => toggleSort('asTo')}
          className="w-10 flex items-center justify-end gap-0.5 px-1 py-1.5 hover:text-light-700"
          title="Transactions where entity is the recipient"
        >
          T <SortIcon field="asTo" />
        </button>
        <button
          onClick={() => toggleSort('totalVolume')}
          className="w-16 flex items-center justify-end gap-1 px-2 py-1.5 hover:text-light-700"
        >
          Volume <SortIcon field="totalVolume" />
        </button>
      </div>

      {/* Rows */}
      <div className="max-h-[220px] overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="px-3 py-4 text-[11px] text-light-400 text-center">
            {search ? 'No matches' : 'No entities in scope'}
          </div>
        ) : (
          filtered.map((entity) => {
            const isSelected = selectedEntities.has(entity.key);
            return (
              <div
                key={entity.key}
                onClick={() => toggleEntity(entity.key)}
                className={`flex items-center cursor-pointer transition-colors border-b border-light-50 last:border-b-0
                  ${isSelected ? 'bg-owl-blue-50 hover:bg-owl-blue-100' : 'hover:bg-light-50'}`}
              >
                <div className="flex-1 min-w-0 px-2.5 py-1.5">
                  <span
                    className={`text-[11px] truncate block ${isSelected ? 'text-owl-blue-700 font-medium' : 'text-light-700'}`}
                    title={entity.name}
                  >
                    {entity.name}
                  </span>
                </div>
                <div className={`w-10 text-right px-1 py-1.5 text-[10px] ${isSelected ? 'text-owl-blue-600' : 'text-light-500'}`}>
                  {entity.asFromCount || ''}
                </div>
                <div className={`w-10 text-right px-1 py-1.5 text-[10px] ${isSelected ? 'text-owl-blue-600' : 'text-light-500'}`}>
                  {entity.asToCount || ''}
                </div>
                <div className={`w-16 text-right px-2 py-1.5 text-[11px] font-medium ${isSelected ? 'text-owl-blue-700' : 'text-light-700'}`}>
                  {formatCompact(entity.totalVolume)}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );

  // ── Right-side perspective summary cards + chart ──
  const summaryCards = [];
  if (summary) {
    summaryCards.push({
      label: 'Inflow',
      sublabel: `${summary.inflowCount} txn${summary.inflowCount !== 1 ? 's' : ''}`,
      value: formatCurrency(summary.inflow),
      Icon: ArrowDownLeft,
      color: '#16a34a',
      bgColor: '#dcfce7',
    });
    summaryCards.push({
      label: 'Outflow',
      sublabel: `${summary.outflowCount} txn${summary.outflowCount !== 1 ? 's' : ''}`,
      value: formatCurrency(summary.outflow),
      Icon: ArrowUpRight,
      color: '#dc2626',
      bgColor: '#fef2f2',
    });
    const netColor = summary.net >= 0 ? '#16a34a' : '#dc2626';
    const netBg = summary.net >= 0 ? '#ecfdf5' : '#fef2f2';
    summaryCards.push({
      label: 'Net',
      sublabel: 'Inflow − Outflow',
      value: `${summary.net >= 0 ? '+' : '-'}${formatCurrency(summary.net)}`,
      Icon: TrendingUp,
      color: netColor,
      bgColor: netBg,
    });
    if (summary.internal > 0) {
      summaryCards.push({
        label: 'Internal',
        sublabel: `${summary.internalCount} intra-set`,
        value: formatCurrency(summary.internal),
        Icon: Repeat,
        color: '#64748b',
        bgColor: '#f1f5f9',
      });
    }
  }

  const rightBody = (
    <div className="flex flex-col min-w-0 gap-2">
      {hasSelection && summary && (
        <div
          className="grid gap-2"
          style={{ gridTemplateColumns: `repeat(${summaryCards.length}, minmax(0, 1fr))` }}
        >
          {summaryCards.map((c) => (
            <div
              key={c.label}
              className="rounded-lg border border-light-200 p-2"
              style={{ backgroundColor: c.bgColor }}
            >
              <div className="flex items-center gap-1 mb-0.5">
                <c.Icon className="w-3 h-3" style={{ color: c.color }} />
                <span className="text-[10px] text-light-700 font-medium">{c.label}</span>
                <span className="text-[9px] text-light-400 ml-auto truncate">{c.sublabel}</span>
              </div>
              <div className="text-base font-bold" style={{ color: c.color }}>
                {c.value}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Cross-filter overlap hint */}
      {hasSelection && crossFilterOverlapCount > 0 && (
        <div className="flex items-start gap-1.5 text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
          <Info className="w-3 h-3 flex-shrink-0 mt-px" />
          <span>
            {crossFilterOverlapCount} selected {crossFilterOverlapCount === 1 ? 'entity is' : 'entities are'} also in the From/To cross-filter —
            the intersection of both filters applies.
          </span>
        </div>
      )}

      {/* Chart */}
      <div className="border border-light-200 rounded-lg bg-white p-2 min-h-[200px]">
        <div className="text-[10px] text-light-600 mb-1 font-medium flex items-center justify-between">
          <span>Counterparty Flow (external only)</span>
          {chartData.length > 0 && (
            <span className="text-[9px] text-light-400">Top {chartData.length}</span>
          )}
        </div>
        {!hasSelection ? (
          <div className="flex flex-col items-center justify-center h-[200px] text-center px-4">
            <TrendingUp className="w-6 h-6 text-light-300 mb-2" />
            <div className="text-xs text-light-500 font-medium">No perspective selected</div>
            <div className="text-[11px] text-light-400 mt-1 max-w-[320px]">
              Select one or more entities in the left panel to see the money flowing in and out of that perspective set.
            </div>
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[200px] text-xs text-light-500">
            {summary && summary.internal > 0
              ? 'All transactions are internal — no external counterparties.'
              : 'No counterparty data for the selected perspective.'}
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 22)}>
              <BarChart
                data={chartData}
                layout="vertical"
                stackOffset="sign"
                margin={{ top: 5, right: 10, left: 5, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fontSize: 9 }}
                  tickFormatter={(v) => formatCompact(v)}
                />
                <YAxis
                  dataKey="name"
                  type="category"
                  tick={{ fontSize: 9 }}
                  width={120}
                  interval={0}
                  tickFormatter={(v) => v.length > 18 ? v.slice(0, 17) + '…' : v}
                />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: '#f8fafc' }} />
                <ReferenceLine x={0} stroke="#94a3b8" />
                <Legend wrapperStyle={{ fontSize: 9 }} />
                <Bar dataKey="outflow" name="Outflow" stackId="flow" fill="#ef4444" />
                <Bar dataKey="inflow" name="Inflow" stackId="flow" fill="#22c55e" />
              </BarChart>
            </ResponsiveContainer>
            {extraCounterparties && (
              <div className="text-[10px] text-light-500 text-right mt-1">
                +{extraCounterparties.count} more counterpart{extraCounterparties.count === 1 ? 'y' : 'ies'} ({formatCurrency(extraCounterparties.total)} combined)
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col md:flex-row gap-3">
      <div className="md:w-[38%] flex-shrink-0">{pickerBody}</div>
      <div className="flex-1 min-w-0">{rightBody}</div>
    </div>
  );
}
