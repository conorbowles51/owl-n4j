import { useState, useMemo, useCallback } from 'react';
import { ArrowUpDown, ArrowUp, ArrowDown, Pencil, Search, X, Check, Tag } from 'lucide-react';
import CategoryBadge from './CategoryBadge';
import { graphAPI, financialAPI } from '../../services/api';

const TYPE_COLORS = {
  Transaction: '#06b6d4',
  Transfer: '#14b8a6',
  Payment: '#84cc16',
  Invoice: '#f97316',
  Deposit: '#3b82f6',
  Withdrawal: '#ef4444',
  Other: '#6b7280',
};

function formatAmount(amount) {
  if (amount == null) return '-';
  const num = parseFloat(amount);
  const formatted = Math.abs(num).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return num >= 0 ? `$${formatted}` : `-$${formatted}`;
}

function EntityCell({ entity, isManual, onEdit }) {
  if (!entity || !entity.name) {
    return (
      <span className="text-light-400 text-xs flex items-center gap-1">
        Unknown
        <button
          onClick={(e) => { e.stopPropagation(); onEdit(); }}
          className="p-0.5 hover:text-owl-blue-600 rounded"
        >
          <Pencil className="w-3 h-3" />
        </button>
      </span>
    );
  }
  return (
    <span className="text-xs flex items-center gap-1">
      <span className="text-owl-blue-600 hover:underline cursor-pointer truncate max-w-[100px]" title={entity.name}>
        {entity.name}
      </span>
      {isManual && <span className="text-light-400" title="Manually set"><Pencil className="w-2.5 h-2.5" /></span>}
      <button
        onClick={(e) => { e.stopPropagation(); onEdit(); }}
        className="p-0.5 hover:text-owl-blue-600 rounded opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <Pencil className="w-3 h-3" />
      </button>
    </span>
  );
}

function EntityEditor({ caseId, side, currentEntity, onSave, onCancel }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [customName, setCustomName] = useState('');

  const handleSearch = useCallback(async (q) => {
    setSearchQuery(q);
    if (q.length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const res = await graphAPI.search(q, 10, caseId);
      setResults(res.results || res || []);
    } catch {
      setResults([]);
    }
    setLoading(false);
  }, [caseId]);

  const handleSelectEntity = (entity) => {
    onSave({ key: entity.key, name: entity.name });
  };

  const handleCustomSave = () => {
    if (customName.trim()) {
      onSave({ key: null, name: customName.trim() });
    }
  };

  return (
    <div className="absolute z-50 bg-white rounded-lg shadow-lg border border-light-200 p-2 w-64" onClick={e => e.stopPropagation()}>
      <div className="text-xs text-light-600 font-medium mb-1.5">Set {side} entity</div>
      <div className="relative mb-2">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
        <input
          type="text"
          placeholder="Search entities..."
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          className="w-full text-xs pl-7 pr-2 py-1.5 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
          autoFocus
        />
      </div>
      {loading && <div className="text-xs text-light-500 py-1">Searching...</div>}
      {results.length > 0 && (
        <div className="max-h-32 overflow-y-auto mb-2 border border-light-100 rounded">
          {results.map(r => (
            <button
              key={r.key}
              onClick={() => handleSelectEntity(r)}
              className="w-full text-left px-2 py-1 text-xs hover:bg-light-50 flex items-center gap-2"
            >
              <span className="font-medium truncate">{r.name}</span>
              <span className="text-light-400 flex-shrink-0">{r.type}</span>
            </button>
          ))}
        </div>
      )}
      <div className="flex items-center gap-1">
        <input
          type="text"
          placeholder="Or type custom name..."
          value={customName}
          onChange={(e) => setCustomName(e.target.value)}
          className="flex-1 text-xs px-2 py-1 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
        />
        <button
          onClick={handleCustomSave}
          disabled={!customName.trim()}
          className="p-1 text-owl-blue-600 hover:bg-owl-blue-50 rounded disabled:opacity-30"
        >
          <Check className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onCancel}
          className="p-1 text-light-500 hover:bg-light-100 rounded"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

export default function FinancialTable({
  transactions = [],
  categories = [],
  caseId,
  onNodeSelect,
  onCategoryChange,
  onFromToChange,
  selectedKeys = [],
  onSelectionChange,
  onBatchCategorize,
}) {
  const [sortField, setSortField] = useState('date');
  const [sortDir, setSortDir] = useState('asc');
  const [editingFromTo, setEditingFromTo] = useState(null); // { key, side: 'from'|'to' }

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const sorted = useMemo(() => {
    const arr = [...transactions];
    arr.sort((a, b) => {
      let va = a[sortField];
      let vb = b[sortField];
      if (sortField === 'amount') {
        va = parseFloat(va) || 0;
        vb = parseFloat(vb) || 0;
        return sortDir === 'asc' ? va - vb : vb - va;
      }
      va = (va || '').toString().toLowerCase();
      vb = (vb || '').toString().toLowerCase();
      const cmp = va.localeCompare(vb);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return arr;
  }, [transactions, sortField, sortDir]);

  const isSelected = (key) => selectedKeys.includes(key);

  const toggleSelection = (key) => {
    if (isSelected(key)) {
      onSelectionChange(selectedKeys.filter(k => k !== key));
    } else {
      onSelectionChange([...selectedKeys, key]);
    }
  };

  const toggleAll = () => {
    if (selectedKeys.length === sorted.length) {
      onSelectionChange([]);
    } else {
      onSelectionChange(sorted.map(t => t.key));
    }
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <ArrowUpDown className="w-3 h-3 text-light-400" />;
    return sortDir === 'asc' ? <ArrowUp className="w-3 h-3 text-owl-blue-600" /> : <ArrowDown className="w-3 h-3 text-owl-blue-600" />;
  };

  const handleFromToSave = async (txnKey, side, entity) => {
    setEditingFromTo(null);
    if (onFromToChange) {
      onFromToChange(txnKey, side, entity);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Batch actions toolbar */}
      {selectedKeys.length > 0 && (
        <div className="flex-shrink-0 flex items-center gap-3 px-3 py-2 bg-owl-blue-50 border-b border-owl-blue-200">
          <span className="text-xs text-owl-blue-700 font-medium">{selectedKeys.length} selected</span>
          <div className="flex items-center gap-1">
            <Tag className="w-3.5 h-3.5 text-owl-blue-600" />
            <span className="text-xs text-owl-blue-700">Categorize:</span>
            {['Suspicious', 'Legitimate', 'Under Review', 'Unknown'].map(cat => (
              <button
                key={cat}
                onClick={() => onBatchCategorize(selectedKeys, cat)}
                className="text-xs px-2 py-0.5 rounded hover:opacity-80"
                style={{
                  backgroundColor: `${cat === 'Suspicious' ? '#ef4444' : cat === 'Legitimate' ? '#22c55e' : cat === 'Under Review' ? '#f59e0b' : '#6b7280'}20`,
                  color: cat === 'Suspicious' ? '#ef4444' : cat === 'Legitimate' ? '#22c55e' : cat === 'Under Review' ? '#f59e0b' : '#6b7280',
                }}
              >
                {cat}
              </button>
            ))}
          </div>
          <button onClick={() => onSelectionChange([])} className="text-xs text-owl-blue-600 hover:underline ml-auto">
            Clear selection
          </button>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-light-50 z-10">
            <tr className="border-b border-light-200">
              <th className="px-2 py-2 text-left w-8">
                <input
                  type="checkbox"
                  checked={selectedKeys.length === sorted.length && sorted.length > 0}
                  onChange={toggleAll}
                  className="rounded border-light-300"
                />
              </th>
              {[
                { key: 'date', label: 'Date' },
                { key: 'time', label: 'Time' },
                { key: 'name', label: 'Name' },
                { key: 'from_to', label: 'From → To', sortable: false },
                { key: 'amount', label: 'Amount' },
                { key: 'type', label: 'Type' },
                { key: 'financial_category', label: 'Category' },
              ].map(col => (
                <th
                  key={col.key}
                  className={`px-2 py-2 text-left font-medium text-light-600 ${col.sortable !== false ? 'cursor-pointer hover:text-light-800' : ''}`}
                  onClick={col.sortable !== false ? () => handleSort(col.key) : undefined}
                >
                  <div className="flex items-center gap-1">
                    <span>{col.label}</span>
                    {col.sortable !== false && <SortIcon field={col.key} />}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map(txn => {
              const amount = parseFloat(txn.amount);
              const amountColor = amount >= 0 ? '#22c55e' : '#ef4444';
              const typeColor = TYPE_COLORS[txn.type] || TYPE_COLORS.Other;

              return (
                <tr
                  key={txn.key}
                  className={`border-b border-light-100 hover:bg-light-50 cursor-pointer group ${isSelected(txn.key) ? 'bg-owl-blue-50' : ''}`}
                  onClick={() => onNodeSelect && onNodeSelect(txn.key)}
                >
                  <td className="px-2 py-1.5">
                    <input
                      type="checkbox"
                      checked={isSelected(txn.key)}
                      onChange={(e) => { e.stopPropagation(); toggleSelection(txn.key); }}
                      className="rounded border-light-300"
                    />
                  </td>
                  <td className="px-2 py-1.5 text-light-700 whitespace-nowrap">{txn.date || '-'}</td>
                  <td className="px-2 py-1.5 text-light-500 whitespace-nowrap">{txn.time || '-'}</td>
                  <td className="px-2 py-1.5 text-light-900 font-medium truncate max-w-[180px]" title={txn.name}>{txn.name}</td>
                  <td className="px-2 py-1.5 relative">
                    <div className="flex items-center gap-1">
                      <EntityCell
                        entity={txn.from_entity}
                        isManual={txn.has_manual_from}
                        onEdit={() => setEditingFromTo({ key: txn.key, side: 'from' })}
                      />
                      <span className="text-light-400 flex-shrink-0">→</span>
                      <EntityCell
                        entity={txn.to_entity}
                        isManual={txn.has_manual_to}
                        onEdit={() => setEditingFromTo({ key: txn.key, side: 'to' })}
                      />
                    </div>
                    {editingFromTo && editingFromTo.key === txn.key && (
                      <EntityEditor
                        caseId={caseId}
                        side={editingFromTo.side}
                        currentEntity={editingFromTo.side === 'from' ? txn.from_entity : txn.to_entity}
                        onSave={(entity) => handleFromToSave(txn.key, editingFromTo.side, entity)}
                        onCancel={() => setEditingFromTo(null)}
                      />
                    )}
                  </td>
                  <td className="px-2 py-1.5 whitespace-nowrap font-mono font-medium" style={{ color: amountColor }}>
                    {formatAmount(txn.amount)}
                  </td>
                  <td className="px-2 py-1.5">
                    <span
                      className="text-xs px-1.5 py-0.5 rounded"
                      style={{ backgroundColor: `${typeColor}20`, color: typeColor }}
                    >
                      {txn.type}
                    </span>
                  </td>
                  <td className="px-2 py-1.5">
                    <CategoryBadge
                      category={txn.financial_category}
                      categories={categories}
                      onCategoryChange={(cat) => onCategoryChange(txn.key, cat)}
                    />
                  </td>
                </tr>
              );
            })}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-light-500">
                  No transactions match the current filters
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
