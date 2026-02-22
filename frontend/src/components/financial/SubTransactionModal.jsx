import { useState, useEffect, useMemo } from 'react';
import { X, Loader2, AlertTriangle, Check } from 'lucide-react';

function formatAmount(amount) {
  if (amount == null) return '-';
  const num = parseFloat(amount);
  const formatted = Math.abs(num).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return num >= 0 ? `$${formatted}` : `-$${formatted}`;
}

export default function SubTransactionModal({
  isOpen,
  onClose,
  parentTransaction,
  allTransactions,
  caseId,
  onSave,
}) {
  const [selectedChildKeys, setSelectedChildKeys] = useState(new Set());
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (isOpen) {
      setSelectedChildKeys(new Set());
      setSaving(false);
      setSearch('');
    }
  }, [isOpen]);

  const availableTransactions = useMemo(() => {
    if (!parentTransaction || !allTransactions) return [];
    return allTransactions.filter(t => {
      if (t.key === parentTransaction.key) return false;
      if (t.parent_transaction_key && t.parent_transaction_key !== parentTransaction.key) return false;
      return true;
    });
  }, [allTransactions, parentTransaction]);

  const filtered = useMemo(() => {
    if (!search.trim()) return availableTransactions;
    const q = search.toLowerCase();
    return availableTransactions.filter(t =>
      (t.name || '').toLowerCase().includes(q) ||
      (t.date || '').includes(q) ||
      (t.type || '').toLowerCase().includes(q)
    );
  }, [availableTransactions, search]);

  const selectedTotal = useMemo(() => {
    let sum = 0;
    availableTransactions.forEach(t => {
      if (selectedChildKeys.has(t.key)) {
        sum += Math.abs(parseFloat(t.amount) || 0);
      }
    });
    return Math.round(sum * 100) / 100;
  }, [availableTransactions, selectedChildKeys]);

  const parentAmount = parentTransaction ? Math.abs(parseFloat(parentTransaction.amount) || 0) : 0;
  const totalsMismatch = selectedChildKeys.size > 0 && Math.abs(selectedTotal - parentAmount) > 0.01;

  const toggleChild = (key) => {
    setSelectedChildKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleSave = async () => {
    if (selectedChildKeys.size === 0) return;
    setSaving(true);
    try {
      await onSave([...selectedChildKeys]);
      onClose();
    } catch {
      setSaving(false);
    }
  };

  if (!isOpen || !parentTransaction) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div
        className="bg-white rounded-lg shadow-xl w-[560px] max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-light-200">
          <span className="text-sm font-medium text-light-800">Group Sub-Transactions</span>
          <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Parent info */}
        <div className="px-4 py-3 bg-light-50 border-b border-light-200">
          <div className="text-xs text-light-500 font-medium mb-1">Parent Transaction</div>
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm font-medium text-light-800">{parentTransaction.name}</span>
              <span className="text-xs text-light-500 ml-2">{parentTransaction.date || ''}</span>
            </div>
            <span className="text-sm font-mono font-medium text-green-600">
              {formatAmount(parentTransaction.amount)}
            </span>
          </div>
        </div>

        {/* Search */}
        <div className="px-4 pt-3 pb-2">
          <input
            type="text"
            placeholder="Search transactions..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full text-xs px-3 py-1.5 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
          />
        </div>

        {/* Checkbox list */}
        <div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
          {filtered.length === 0 ? (
            <div className="text-xs text-light-500 text-center py-4">No available transactions</div>
          ) : (
            <div className="space-y-1">
              {filtered.map(t => {
                const checked = selectedChildKeys.has(t.key);
                const alreadyChild = t.parent_transaction_key === parentTransaction.key;
                return (
                  <label
                    key={t.key}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-light-50 ${
                      checked ? 'bg-owl-blue-50' : ''
                    } ${alreadyChild ? 'opacity-60' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked || alreadyChild}
                      disabled={alreadyChild}
                      onChange={() => toggleChild(t.key)}
                      className="rounded border-light-300"
                    />
                    <div className="flex-1 min-w-0 flex items-center gap-2">
                      <span className="text-xs text-light-500 w-[70px] flex-shrink-0">{t.date || '-'}</span>
                      <span className="text-xs text-light-800 truncate flex-1" title={t.name}>
                        {t.name}
                      </span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-light-100 text-light-600 flex-shrink-0">
                        {t.type}
                      </span>
                      <span className="text-xs font-mono text-light-700 flex-shrink-0 w-[80px] text-right">
                        {formatAmount(t.amount)}
                      </span>
                      {alreadyChild && (
                        <Check className="w-3 h-3 text-green-500 flex-shrink-0" title="Already linked" />
                      )}
                    </div>
                  </label>
                );
              })}
            </div>
          )}
        </div>

        {/* Totals + Warning */}
        <div className="px-4 py-3 border-t border-light-200 bg-light-50 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-light-600">
              Selected: <span className="font-medium">{selectedChildKeys.size}</span> transactions
            </span>
            <div className="flex items-center gap-3">
              <span className="text-light-600">
                Children total: <span className="font-mono font-medium">{formatAmount(selectedTotal)}</span>
              </span>
              <span className="text-light-600">
                Parent: <span className="font-mono font-medium">{formatAmount(parentAmount)}</span>
              </span>
            </div>
          </div>
          {totalsMismatch && (
            <div className="flex items-center gap-1.5 text-xs text-amber-600 bg-amber-50 px-2 py-1.5 rounded">
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
              <span>
                Children total ({formatAmount(selectedTotal)}) does not match parent amount ({formatAmount(parentAmount)})
              </span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-light-200">
          <button
            type="button"
            onClick={onClose}
            className="text-xs px-3 py-1.5 rounded border border-light-200 text-light-600 hover:bg-light-50"
            disabled={saving}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || selectedChildKeys.size === 0}
            className="text-xs px-3 py-1.5 rounded bg-owl-blue-600 text-white hover:bg-owl-blue-700 disabled:opacity-50 flex items-center gap-1"
          >
            {saving && <Loader2 className="w-3 h-3 animate-spin" />}
            Link {selectedChildKeys.size} Transaction{selectedChildKeys.size !== 1 ? 's' : ''}
          </button>
        </div>
      </div>
    </div>
  );
}
