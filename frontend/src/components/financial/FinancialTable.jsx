import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { ArrowUpDown, ArrowUp, ArrowDown, Pencil, Search, X, Check, Tag, ChevronDown, ChevronRight, ArrowLeftRight, MoreHorizontal, Link2, Unlink, CornerDownRight } from 'lucide-react';
import CategoryBadge from './CategoryBadge';
import { CATEGORY_COLORS } from './constants';
import { graphAPI, financialAPI } from '../../services/api';
import SubTransactionModal from './SubTransactionModal';

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

function CategoryDropdown({ categories = [], categoryColorMap = {}, onSelect }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  return (
    <div className="relative inline-block" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-white border border-owl-blue-200 text-owl-blue-700 hover:bg-owl-blue-50"
      >
        <Tag className="w-3 h-3" />
        <span>Categorize</span>
        <ChevronDown className="w-3 h-3" />
      </button>
      {isOpen && (
        <div className="absolute z-50 mt-1 w-44 bg-white rounded-lg shadow-lg border border-light-200 py-1 left-0 max-h-60 overflow-y-auto">
          {categories.map(cat => {
            const color = categoryColorMap[cat] || CATEGORY_COLORS[cat] || '#6b7280';
            return (
              <button
                key={cat}
                onClick={() => { onSelect(cat); setIsOpen(false); }}
                className="w-full text-left px-3 py-1.5 text-xs hover:bg-light-50 flex items-center gap-2"
              >
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                <span>{cat}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function RowActionsDropdown({ txn, onGroupAsSubTransaction, onRemoveFromGroup }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  const isChild = !!txn.parent_transaction_key;

  return (
    <div className="relative inline-block" ref={dropdownRef}>
      <button
        onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen); }}
        className="p-1 text-light-500 hover:text-owl-blue-700 rounded hover:bg-owl-blue-50 transition-colors"
        title="Transaction actions"
      >
        <MoreHorizontal className="w-4 h-4" />
      </button>
      {isOpen && (
        <div className="absolute z-50 mt-1 right-0 w-48 bg-white rounded-lg shadow-lg border border-light-200 py-1">
          {!isChild && (
            <button
              onClick={(e) => { e.stopPropagation(); onGroupAsSubTransaction(txn); setIsOpen(false); }}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-light-50 flex items-center gap-2"
            >
              <Link2 className="w-3 h-3" />
              Group Sub-Transactions
            </button>
          )}
          {isChild && (
            <button
              onClick={(e) => { e.stopPropagation(); onRemoveFromGroup(txn.key); setIsOpen(false); }}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-light-50 flex items-center gap-2 text-red-600"
            >
              <Unlink className="w-3 h-3" />
              Remove from Group
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function TransactionDetailRow({ txn, onDetailsChange }) {
  const [purpose, setPurpose] = useState(txn.purpose || '');
  const [counterpartyDetails, setCounterpartyDetails] = useState(txn.counterparty_details || '');
  const [notes, setNotes] = useState(txn.notes || '');

  const handleBlur = (field, value) => {
    const original = field === 'purpose' ? (txn.purpose || '') :
                     field === 'counterpartyDetails' ? (txn.counterparty_details || '') :
                     (txn.notes || '');
    if (value !== original) {
      onDetailsChange(txn.key, { [field]: value });
    }
  };

  return (
    <tr className="bg-light-50 border-b border-light-200">
      <td colSpan={10} className="px-4 py-3">
        <div className="space-y-2 max-w-2xl">
          {txn.summary && (
            <div>
              <span className="text-xs text-light-500 font-medium">AI Summary:</span>
              <p className="text-xs text-light-700 mt-0.5">{txn.summary}</p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-light-500 font-medium block mb-0.5">Purpose</label>
              <input
                type="text"
                placeholder="What is this payment for?"
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                onBlur={() => handleBlur('purpose', purpose)}
                onClick={(e) => e.stopPropagation()}
                className="w-full text-xs px-2 py-1.5 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400 bg-white"
              />
            </div>
            <div>
              <label className="text-xs text-light-500 font-medium block mb-0.5">Counterparty Details</label>
              <input
                type="text"
                placeholder="Who is this for / background"
                value={counterpartyDetails}
                onChange={(e) => setCounterpartyDetails(e.target.value)}
                onBlur={() => handleBlur('counterpartyDetails', counterpartyDetails)}
                onClick={(e) => e.stopPropagation()}
                className="w-full text-xs px-2 py-1.5 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400 bg-white"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-light-500 font-medium block mb-0.5">Notes</label>
            <textarea
              placeholder="Investigation notes..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => handleBlur('notes', notes)}
              onClick={(e) => e.stopPropagation()}
              rows={2}
              className="w-full text-xs px-2 py-1.5 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400 bg-white resize-none"
            />
          </div>
        </div>
      </td>
    </tr>
  );
}

export default function FinancialTable({
  transactions = [],
  categories = [],
  categoryColorMap = {},
  caseId,
  onNodeSelect,
  onCategoryChange,
  onFromToChange,
  onDetailsChange,
  onBatchFromTo,
  selectedKeys = [],
  onSelectionChange,
  onBatchCategorize,
  onAmountChange,
  onTransactionsRefresh,
}) {
  const [sortField, setSortField] = useState('date');
  const [sortDir, setSortDir] = useState('asc');
  const [editingFromTo, setEditingFromTo] = useState(null); // { key, side: 'from'|'to' }
  const [expandedKey, setExpandedKey] = useState(null);
  const [batchFromToSide, setBatchFromToSide] = useState(null); // 'from' | 'to' | null
  const [editingAmount, setEditingAmount] = useState(null); // { key, value, step: 'amount'|'reason', reason }

  // Sub-transaction grouping state
  const [expandedParentKeys, setExpandedParentKeys] = useState(new Set());
  const [childrenCache, setChildrenCache] = useState({}); // { parentKey: [children] }
  const [loadingChildren, setLoadingChildren] = useState(new Set());
  const [subTxnModalOpen, setSubTxnModalOpen] = useState(false);
  const [subTxnModalParent, setSubTxnModalParent] = useState(null);

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

  const handleBatchFromToSave = (entity) => {
    if (onBatchFromTo && batchFromToSide) {
      onBatchFromTo(selectedKeys, batchFromToSide, entity);
    }
    setBatchFromToSide(null);
  };

  const toggleParentExpand = useCallback(async (parentKey) => {
    setExpandedParentKeys(prev => {
      const next = new Set(prev);
      if (next.has(parentKey)) {
        next.delete(parentKey);
      } else {
        next.add(parentKey);
      }
      return next;
    });

    if (!childrenCache[parentKey]) {
      setLoadingChildren(prev => new Set(prev).add(parentKey));
      try {
        const res = await financialAPI.getSubTransactions(parentKey, caseId);
        setChildrenCache(prev => ({ ...prev, [parentKey]: res.children || [] }));
      } catch (err) {
        console.error('Failed to fetch sub-transactions:', err);
      }
      setLoadingChildren(prev => {
        const next = new Set(prev);
        next.delete(parentKey);
        return next;
      });
    }
  }, [caseId, childrenCache]);

  const handleGroupAsSubTransaction = (txn) => {
    setSubTxnModalParent(txn);
    setSubTxnModalOpen(true);
  };

  const handleSubTxnSave = useCallback(async (childKeys) => {
    if (!subTxnModalParent) return;
    for (const childKey of childKeys) {
      await financialAPI.linkSubTransaction(subTxnModalParent.key, childKey, caseId);
    }
    // Invalidate cache and refresh
    setChildrenCache(prev => {
      const next = { ...prev };
      delete next[subTxnModalParent.key];
      return next;
    });
    setExpandedParentKeys(prev => new Set(prev).add(subTxnModalParent.key));
    if (onTransactionsRefresh) onTransactionsRefresh();
  }, [subTxnModalParent, caseId, onTransactionsRefresh]);

  const handleRemoveFromGroup = useCallback(async (childKey) => {
    try {
      const result = await financialAPI.unlinkSubTransaction(childKey, caseId);
      // Invalidate parent's cache
      if (result.parent_key) {
        setChildrenCache(prev => {
          const next = { ...prev };
          delete next[result.parent_key];
          return next;
        });
      }
      if (onTransactionsRefresh) onTransactionsRefresh();
    } catch (err) {
      console.error('Failed to unlink sub-transaction:', err);
    }
  }, [caseId, onTransactionsRefresh]);

  return (
    <div className="flex flex-col h-full">
      {/* Batch actions toolbar */}
      {selectedKeys.length > 0 && (
        <div className="flex-shrink-0 flex items-center gap-3 px-3 py-2 bg-owl-blue-50 border-b border-owl-blue-200 relative">
          <span className="text-xs text-owl-blue-700 font-medium">{selectedKeys.length} selected</span>
          <CategoryDropdown categories={categories} categoryColorMap={categoryColorMap} onSelect={(cat) => onBatchCategorize(selectedKeys, cat)} />
          <button
            onClick={() => setBatchFromToSide(batchFromToSide === 'from' ? null : 'from')}
            className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded border ${batchFromToSide === 'from' ? 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-800' : 'bg-white border-owl-blue-200 text-owl-blue-700 hover:bg-owl-blue-50'}`}
          >
            <ArrowLeftRight className="w-3 h-3" />
            Set From
          </button>
          <button
            onClick={() => setBatchFromToSide(batchFromToSide === 'to' ? null : 'to')}
            className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded border ${batchFromToSide === 'to' ? 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-800' : 'bg-white border-owl-blue-200 text-owl-blue-700 hover:bg-owl-blue-50'}`}
          >
            <ArrowLeftRight className="w-3 h-3" />
            Set To
          </button>
          <button onClick={() => onSelectionChange([])} className="text-xs text-owl-blue-600 hover:underline ml-auto">
            Clear selection
          </button>
          {batchFromToSide && (
            <div className="absolute top-full left-32 mt-1 z-50">
              <EntityEditor
                caseId={caseId}
                side={batchFromToSide}
                currentEntity={null}
                onSave={handleBatchFromToSave}
                onCancel={() => setBatchFromToSide(null)}
              />
            </div>
          )}
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
              <th className="px-1 py-2 w-6"></th>
              {[
                { key: 'date', label: 'Date' },
                { key: 'time', label: 'Time' },
                { key: 'name', label: 'Name' },
                { key: 'from_to', label: 'From \u2192 To', sortable: false },
                { key: 'amount', label: 'Amount' },
                { key: 'type', label: 'Type' },
                { key: 'financial_category', label: 'Category' },
                { key: 'actions', label: 'Actions', sortable: false },
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
              const isExpanded = expandedKey === txn.key;
              const isParent = txn.is_parent;
              const isChild = !!txn.parent_transaction_key;
              const isParentExpanded = expandedParentKeys.has(txn.key);
              const isLoadingChildren = loadingChildren.has(txn.key);
              const children = childrenCache[txn.key] || [];

              return (
                <React.Fragment key={txn.key}>
                  <tr
                    className={`border-b border-light-100 hover:bg-light-50 cursor-pointer group ${isSelected(txn.key) ? 'bg-owl-blue-50' : ''} ${isChild ? 'bg-indigo-50/30' : ''}`}
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
                    <td className="px-1 py-1.5">
                      <div className="flex items-center gap-0.5">
                        {isParent && (
                          <button
                            onClick={(e) => { e.stopPropagation(); toggleParentExpand(txn.key); }}
                            className="p-0.5 text-owl-blue-500 hover:text-owl-blue-700 rounded"
                            title="Expand sub-transactions"
                          >
                            {isParentExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                          </button>
                        )}
                        {!isParent && (
                          <button
                            onClick={(e) => { e.stopPropagation(); setExpandedKey(isExpanded ? null : txn.key); }}
                            className="p-0.5 text-light-400 hover:text-light-700 rounded"
                          >
                            {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="px-2 py-1.5 text-light-700 whitespace-nowrap">{txn.date || '-'}</td>
                    <td className="px-2 py-1.5 text-light-500 whitespace-nowrap">{txn.time || '-'}</td>
                    <td className="px-2 py-1.5 text-light-900 font-medium truncate max-w-[180px]" title={txn.name}>
                      <span className="flex items-center gap-1">
                        {isChild && <CornerDownRight className="w-3 h-3 text-light-400 flex-shrink-0" />}
                        {isParent && <Link2 className="w-3 h-3 text-owl-blue-500 flex-shrink-0" title="Parent transaction" />}
                        <span className="truncate">{txn.name}</span>
                      </span>
                    </td>
                    <td className="px-2 py-1.5 relative">
                      <div className="flex items-center gap-1">
                        <EntityCell
                          entity={txn.from_entity}
                          isManual={txn.has_manual_from}
                          onEdit={() => setEditingFromTo({ key: txn.key, side: 'from' })}
                        />
                        <span className="text-light-400 flex-shrink-0">{'\u2192'}</span>
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
                      {editingAmount && editingAmount.key === txn.key ? (
                        editingAmount.step === 'amount' ? (
                          <input
                            type="number"
                            step="0.01"
                            autoFocus
                            value={editingAmount.value}
                            onChange={(e) => setEditingAmount({ ...editingAmount, value: e.target.value })}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                const num = parseFloat(editingAmount.value);
                                if (num > 0) setEditingAmount({ ...editingAmount, step: 'reason', reason: '' });
                              }
                              if (e.key === 'Escape') setEditingAmount(null);
                            }}
                            className="w-24 text-xs px-1.5 py-0.5 border border-owl-blue-400 rounded font-mono bg-dark-800 text-light-100 focus:outline-none"
                          />
                        ) : (
                          <div className="flex flex-col gap-1">
                            <input
                              type="text"
                              autoFocus
                              placeholder="Correction reason…"
                              value={editingAmount.reason}
                              onChange={(e) => setEditingAmount({ ...editingAmount, reason: e.target.value })}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' && editingAmount.reason.trim()) {
                                  onAmountChange(txn.key, parseFloat(editingAmount.value), editingAmount.reason.trim());
                                  setEditingAmount(null);
                                }
                                if (e.key === 'Escape') setEditingAmount(null);
                              }}
                              className="w-32 text-xs px-1.5 py-0.5 border border-amber-400 rounded bg-dark-800 text-light-100 focus:outline-none"
                            />
                            <div className="flex gap-1">
                              <button
                                onClick={() => {
                                  if (editingAmount.reason.trim()) {
                                    onAmountChange(txn.key, parseFloat(editingAmount.value), editingAmount.reason.trim());
                                    setEditingAmount(null);
                                  }
                                }}
                                disabled={!editingAmount.reason.trim()}
                                className="text-[10px] px-1.5 py-0.5 bg-owl-blue-600 text-white rounded hover:bg-owl-blue-500 disabled:opacity-30"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => setEditingAmount(null)}
                                className="text-[10px] px-1.5 py-0.5 bg-dark-600 text-light-300 rounded hover:bg-dark-500"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )
                      ) : (
                        <span
                          className="cursor-pointer hover:underline inline-flex items-center gap-1"
                          onClick={() => setEditingAmount({ key: txn.key, value: parseFloat(txn.amount) || 0, step: 'amount' })}
                          title="Click to edit amount"
                        >
                          {formatAmount(txn.amount)}
                          {txn.amount_corrected && (
                            <span title={`Original: ${formatAmount(txn.original_amount)} — ${txn.correction_reason || ''}`}>
                              <Pencil className="w-3 h-3 text-amber-400 inline" />
                            </span>
                          )}
                        </span>
                      )}
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
                        categoryColorMap={categoryColorMap}
                        onCategoryChange={(cat) => onCategoryChange(txn.key, cat)}
                      />
                    </td>
                    <td className="px-1 py-1.5">
                      <RowActionsDropdown
                        txn={txn}
                        onGroupAsSubTransaction={handleGroupAsSubTransaction}
                        onRemoveFromGroup={handleRemoveFromGroup}
                      />
                    </td>
                  </tr>
                  {isExpanded && !isParent && (
                    <TransactionDetailRow
                      txn={txn}
                      onDetailsChange={onDetailsChange}
                    />
                  )}
                  {/* Sub-transaction children rows */}
                  {isParent && isParentExpanded && (
                    <>
                      {isLoadingChildren && (
                        <tr className="bg-indigo-50/30 border-b border-light-100">
                          <td colSpan={10} className="px-6 py-2 text-xs text-light-500">
                            Loading sub-transactions...
                          </td>
                        </tr>
                      )}
                      {!isLoadingChildren && children.length === 0 && (
                        <tr className="bg-indigo-50/30 border-b border-light-100">
                          <td colSpan={10} className="px-6 py-2 text-xs text-light-500">
                            No sub-transactions linked yet
                          </td>
                        </tr>
                      )}
                      {!isLoadingChildren && children.map(child => {
                        const childAmount = parseFloat(child.amount);
                        const childAmountColor = childAmount >= 0 ? '#22c55e' : '#ef4444';
                        const childTypeColor = TYPE_COLORS[child.type] || TYPE_COLORS.Other;
                        return (
                          <tr
                            key={`child-${child.key}`}
                            className="bg-indigo-50/30 border-b border-light-100 hover:bg-indigo-50/50 cursor-pointer group"
                            onClick={() => onNodeSelect && onNodeSelect(child.key)}
                          >
                            <td className="px-2 py-1.5"></td>
                            <td className="px-1 py-1.5"></td>
                            <td className="px-2 py-1.5 text-light-700 whitespace-nowrap">{child.date || '-'}</td>
                            <td className="px-2 py-1.5 text-light-500 whitespace-nowrap">{child.time || '-'}</td>
                            <td className="px-2 py-1.5 text-light-800 truncate max-w-[180px]" title={child.name}>
                              <span className="flex items-center gap-1">
                                <CornerDownRight className="w-3 h-3 text-light-400 flex-shrink-0" />
                                <span className="truncate">{child.name}</span>
                              </span>
                            </td>
                            <td className="px-2 py-1.5 text-xs text-light-500">
                              {child.from_name && child.to_name
                                ? `${child.from_name} → ${child.to_name}`
                                : child.from_name || child.to_name || '-'}
                            </td>
                            <td className="px-2 py-1.5 whitespace-nowrap font-mono font-medium" style={{ color: childAmountColor }}>
                              {formatAmount(child.amount)}
                            </td>
                            <td className="px-2 py-1.5">
                              <span
                                className="text-xs px-1.5 py-0.5 rounded"
                                style={{ backgroundColor: `${childTypeColor}20`, color: childTypeColor }}
                              >
                                {child.type}
                              </span>
                            </td>
                            <td className="px-2 py-1.5 text-xs text-light-500">
                              {child.financial_category || '-'}
                            </td>
                            <td className="px-1 py-1.5">
                              <button
                                onClick={(e) => { e.stopPropagation(); handleRemoveFromGroup(child.key); }}
                                className="p-0.5 text-light-400 hover:text-red-500 rounded hover:bg-light-100"
                                title="Remove from group"
                              >
                                <Unlink className="w-3 h-3" />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </>
                  )}
                </React.Fragment>
              );
            })}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-light-500">
                  No transactions match the current filters
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Sub-Transaction Grouping Modal */}
      <SubTransactionModal
        isOpen={subTxnModalOpen}
        onClose={() => { setSubTxnModalOpen(false); setSubTxnModalParent(null); }}
        parentTransaction={subTxnModalParent}
        allTransactions={transactions}
        caseId={caseId}
        onSave={handleSubTxnSave}
      />
    </div>
  );
}
