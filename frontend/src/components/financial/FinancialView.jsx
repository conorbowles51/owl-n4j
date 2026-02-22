import { useState, useEffect, useCallback, useMemo } from 'react';
import { Loader2, DollarSign, RefreshCw, AlertCircle, Download } from 'lucide-react';
import { financialAPI } from '../../services/api';
import FinancialSummaryCards from './FinancialSummaryCards';
import FinancialCharts from './FinancialCharts';
import FinancialTable from './FinancialTable';
import FinancialFilterPanel from './FinancialFilterPanel';
import AddCategoryModal from './AddCategoryModal';

export default function FinancialView({ caseId, onNodeSelect }) {
  const [transactions, setTransactions] = useState([]);
  const [volumeData, setVolumeData] = useState([]);
  const [categories, setCategories] = useState([]); // {name, color, builtin}[]
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filter state
  const [selectedTypes, setSelectedTypes] = useState(new Set());
  const [selectedCategories, setSelectedCategories] = useState(new Set());
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);
  const [entityFilter, setEntityFilter] = useState(null); // { key, name }
  const [filterExpanded, setFilterExpanded] = useState(true);

  // Selection state for batch operations
  const [selectedKeys, setSelectedKeys] = useState([]);

  // Add category modal
  const [showAddCategoryModal, setShowAddCategoryModal] = useState(false);

  // Derived helpers from category objects
  const categoryNames = useMemo(() => categories.map(c => c.name), [categories]);
  const categoryColorMap = useMemo(() => {
    const map = {};
    categories.forEach(c => { map[c.name] = c.color; });
    return map;
  }, [categories]);

  // Load all financial data
  const loadData = useCallback(async () => {
    if (!caseId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [txnRes, volumeRes, catRes] = await Promise.all([
        financialAPI.getTransactions({ caseId }),
        financialAPI.getVolume(caseId),
        financialAPI.getCategories(caseId),
      ]);
      setTransactions(txnRes.transactions || []);
      setVolumeData(volumeRes.data || []);
      const cats = catRes.categories || [];
      setCategories(cats);

      // Initialize filters with all types and categories selected
      const types = new Set((txnRes.transactions || []).map(t => t.type));
      setSelectedTypes(types);
      setSelectedCategories(new Set(cats.map(c => c.name)));
    } catch (err) {
      console.error('Failed to load financial data:', err);
      setError(err.message || 'Failed to load financial data');
    }
    setIsLoading(false);
  }, [caseId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Derive available transaction types from data
  const transactionTypes = useMemo(() => {
    const types = new Set(transactions.map(t => t.type));
    return [...types].sort();
  }, [transactions]);

  // Collect all unique entities referenced in from/to for the entity filter
  const allEntities = useMemo(() => {
    const map = new Map();
    transactions.forEach(t => {
      if (t.from_entity?.name) map.set(t.from_entity.key || t.from_entity.name, t.from_entity);
      if (t.to_entity?.name) map.set(t.to_entity.key || t.to_entity.name, t.to_entity);
    });
    return [...map.values()].sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  }, [transactions]);

  // Filter transactions client-side
  const filteredTransactions = useMemo(() => {
    return transactions.filter(t => {
      if (selectedTypes.size > 0 && !selectedTypes.has(t.type)) return false;
      if (selectedCategories.size > 0 && !selectedCategories.has(t.financial_category || 'Unknown')) return false;
      if (startDate && t.date && t.date < startDate) return false;
      if (endDate && t.date && t.date > endDate) return false;
      if (entityFilter) {
        const matchKey = entityFilter.key || entityFilter.name;
        const fromMatch = t.from_entity && (t.from_entity.key === matchKey || t.from_entity.name === matchKey);
        const toMatch = t.to_entity && (t.to_entity.key === matchKey || t.to_entity.name === matchKey);
        if (!fromMatch && !toMatch) return false;
      }
      return true;
    });
  }, [transactions, selectedTypes, selectedCategories, startDate, endDate, entityFilter]);

  // Compute summary from filtered transactions — context-aware based on entity filter
  const filteredSummary = useMemo(() => {
    const count = filteredTransactions.length;
    if (count === 0) {
      return entityFilter
        ? { transaction_count: 0, total_inflows: 0, total_outflows: 0, net_flow: 0 }
        : { transaction_count: 0, total_volume: 0, unique_entities: 0, avg_amount: 0 };
    }

    if (entityFilter) {
      // Entity mode: classify relative to the selected entity
      const matchKey = entityFilter.key || entityFilter.name;
      let inflows = 0, outflows = 0;
      filteredTransactions.forEach(t => {
        const amt = Math.abs(parseFloat(t.amount) || 0);
        const isTo = t.to_entity && (t.to_entity.key === matchKey || t.to_entity.name === matchKey);
        const isFrom = t.from_entity && (t.from_entity.key === matchKey || t.from_entity.name === matchKey);
        if (isTo) inflows += amt;
        if (isFrom) outflows += amt;
      });
      return {
        transaction_count: count,
        total_inflows: Math.round(inflows * 100) / 100,
        total_outflows: Math.round(outflows * 100) / 100,
        net_flow: Math.round((inflows - outflows) * 100) / 100,
      };
    } else {
      // Overview mode: aggregate metrics without directional flow
      let volume = 0;
      const entityKeys = new Set();
      filteredTransactions.forEach(t => {
        volume += Math.abs(parseFloat(t.amount) || 0);
        if (t.from_entity?.key) entityKeys.add(t.from_entity.key);
        else if (t.from_entity?.name) entityKeys.add(t.from_entity.name);
        if (t.to_entity?.key) entityKeys.add(t.to_entity.key);
        else if (t.to_entity?.name) entityKeys.add(t.to_entity.name);
      });
      return {
        transaction_count: count,
        total_volume: Math.round(volume * 100) / 100,
        unique_entities: entityKeys.size,
        avg_amount: Math.round((volume / count) * 100) / 100,
      };
    }
  }, [filteredTransactions, entityFilter]);

  // Compute volume data from filtered transactions so charts update with filters
  const filteredVolumeData = useMemo(() => {
    const groups = {};
    filteredTransactions.forEach(t => {
      if (!t.date) return;
      const cat = t.financial_category || 'Uncategorized';
      const key = `${t.date}|${cat}`;
      if (!groups[key]) groups[key] = { date: t.date, category: cat, total_amount: 0, count: 0 };
      groups[key].total_amount += Math.abs(parseFloat(t.amount) || 0);
      groups[key].count += 1;
    });
    return Object.values(groups).sort((a, b) => a.date.localeCompare(b.date) || a.category.localeCompare(b.category));
  }, [filteredTransactions]);

  // Handle category change on a single transaction
  const handleCategoryChange = useCallback(async (nodeKey, category) => {
    try {
      await financialAPI.categorize(nodeKey, category, caseId);
      setTransactions(prev =>
        prev.map(t => t.key === nodeKey ? { ...t, financial_category: category } : t)
      );
    } catch (err) {
      console.error('Failed to categorize:', err);
    }
  }, [caseId]);

  // Handle batch categorize
  const handleBatchCategorize = useCallback(async (nodeKeys, category) => {
    try {
      await financialAPI.batchCategorize(nodeKeys, category, caseId);
      setTransactions(prev =>
        prev.map(t => nodeKeys.includes(t.key) ? { ...t, financial_category: category } : t)
      );
      setSelectedKeys([]);
    } catch (err) {
      console.error('Failed to batch categorize:', err);
    }
  }, [caseId]);

  // Handle from/to change
  const handleFromToChange = useCallback(async (nodeKey, side, entity) => {
    try {
      const payload = { caseId };
      if (side === 'from') {
        payload.fromKey = entity.key;
        payload.fromName = entity.name;
      } else {
        payload.toKey = entity.key;
        payload.toName = entity.name;
      }
      await financialAPI.setFromTo(nodeKey, payload);
      setTransactions(prev =>
        prev.map(t => {
          if (t.key !== nodeKey) return t;
          if (side === 'from') {
            return { ...t, from_entity: entity, has_manual_from: true };
          }
          return { ...t, to_entity: entity, has_manual_to: true };
        })
      );
    } catch (err) {
      console.error('Failed to update from/to:', err);
    }
  }, [caseId]);

  // Handle details change (purpose, counterparty_details, notes)
  const handleDetailsChange = useCallback(async (nodeKey, details) => {
    try {
      await financialAPI.updateDetails(nodeKey, {
        caseId,
        purpose: details.purpose,
        counterpartyDetails: details.counterpartyDetails,
        notes: details.notes,
      });
      setTransactions(prev =>
        prev.map(t => {
          if (t.key !== nodeKey) return t;
          const updated = { ...t };
          if (details.purpose !== undefined) updated.purpose = details.purpose;
          if (details.counterpartyDetails !== undefined) updated.counterparty_details = details.counterpartyDetails;
          if (details.notes !== undefined) updated.notes = details.notes;
          return updated;
        })
      );
    } catch (err) {
      console.error('Failed to update details:', err);
    }
  }, [caseId]);

  const handleAmountChange = useCallback(async (nodeKey, newAmount, correctionReason) => {
    try {
      await financialAPI.updateAmount(nodeKey, {
        caseId: caseId,
        newAmount,
        correctionReason,
      });
      setTransactions(prev =>
        prev.map(t => t.key === nodeKey ? {
          ...t,
          amount: newAmount,
          amount_corrected: true,
          original_amount: t.original_amount ?? t.amount,
          correction_reason: correctionReason,
        } : t)
      );
    } catch (err) {
      console.error('Failed to update amount:', err);
      alert('Failed to update amount: ' + err.message);
    }
  }, [caseId]);

  // Handle batch from/to change
  const handleBatchFromTo = useCallback(async (nodeKeys, side, entity) => {
    try {
      const payload = { caseId };
      if (side === 'from') {
        payload.fromKey = entity.key;
        payload.fromName = entity.name;
      } else {
        payload.toKey = entity.key;
        payload.toName = entity.name;
      }
      await financialAPI.batchSetFromTo(nodeKeys, payload);
      setTransactions(prev =>
        prev.map(t => {
          if (!nodeKeys.includes(t.key)) return t;
          if (side === 'from') {
            return { ...t, from_entity: entity, has_manual_from: true };
          }
          return { ...t, to_entity: entity, has_manual_to: true };
        })
      );
      setSelectedKeys([]);
    } catch (err) {
      console.error('Failed to batch update from/to:', err);
    }
  }, [caseId]);

  // Handle creating a new custom category
  const handleCreateCategory = useCallback(async (name, color) => {
    await financialAPI.createCategory(name, color, caseId);
    // Refresh categories from backend to get accurate state
    const catRes = await financialAPI.getCategories(caseId);
    const cats = catRes.categories || [];
    setCategories(cats);
    // Auto-select the new category in filters
    setSelectedCategories(prev => {
      const next = new Set(prev);
      next.add(name);
      return next;
    });
  }, [caseId]);

  const handleExportPDF = () => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    params.append('case_name', 'Case');
    if (selectedCategories.size > 0 && selectedCategories.size < categoryNames.length) {
      params.append('categories', [...selectedCategories].join(','));
    }
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    window.open(`/api/financial/export/pdf?${params.toString()}`, '_blank');
  };

  // Filter handlers
  const toggleType = (type) => {
    setSelectedTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const toggleCategory = (cat) => {
    setSelectedCategories(prev => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex items-center gap-2 text-light-500">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="text-sm">Loading financial data...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <AlertCircle className="w-8 h-8 text-red-400 mx-auto mb-2" />
          <p className="text-sm text-light-600">{error}</p>
          <button onClick={loadData} className="mt-2 text-sm text-owl-blue-600 hover:underline flex items-center gap-1 mx-auto">
            <RefreshCw className="w-3.5 h-3.5" /> Retry
          </button>
        </div>
      </div>
    );
  }

  if (transactions.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <DollarSign className="w-8 h-8 text-light-300 mx-auto mb-2" />
          <p className="text-sm text-light-500">No financial data available</p>
          <p className="text-xs text-light-400 mt-1">This case has no entities with amount properties</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-2 border-b border-light-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-owl-blue-600" />
          <span className="text-sm font-medium text-light-800">Financial Analysis</span>
          <span className="text-xs text-light-500">
            {filteredTransactions.length} of {transactions.length} transactions
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleExportPDF}
            className="p-1 text-light-500 hover:text-owl-blue-600 rounded hover:bg-light-50"
            title="Export PDF"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={loadData}
            className="p-1 text-light-500 hover:text-owl-blue-600 rounded hover:bg-light-50"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Top: Filters + Summary Cards */}
      <div className="flex-shrink-0 px-4 py-3 space-y-3">
        <FinancialFilterPanel
          transactionTypes={transactionTypes}
          selectedTypes={selectedTypes}
          onToggleType={toggleType}
          onSelectAllTypes={() => setSelectedTypes(new Set(transactionTypes))}
          onClearAllTypes={() => setSelectedTypes(new Set())}
          categories={categoryNames}
          selectedCategories={selectedCategories}
          onToggleCategory={toggleCategory}
          onSelectAllCategories={() => setSelectedCategories(new Set(categoryNames))}
          onClearAllCategories={() => setSelectedCategories(new Set())}
          startDate={startDate}
          endDate={endDate}
          onStartDateChange={setStartDate}
          onEndDateChange={setEndDate}
          entityFilter={entityFilter}
          onEntityFilterChange={setEntityFilter}
          allEntities={allEntities}
          isExpanded={filterExpanded}
          onToggleExpand={() => setFilterExpanded(!filterExpanded)}
          categoryColorMap={categoryColorMap}
          onAddCategory={() => setShowAddCategoryModal(true)}
        />
        <FinancialSummaryCards summary={filteredSummary} entityFilter={entityFilter} />
      </div>

      {/* Bottom: Table (left) + Charts (right) side by side */}
      <div className="flex-1 min-h-0 flex border-t border-light-200">
        {/* Left: Transaction table */}
        <div className="w-[55%] min-w-0 border-r border-light-200">
          <FinancialTable
            transactions={filteredTransactions}
            categories={categoryNames}
            categoryColorMap={categoryColorMap}
            caseId={caseId}
            onNodeSelect={onNodeSelect}
            onCategoryChange={handleCategoryChange}
            onFromToChange={handleFromToChange}
            onDetailsChange={handleDetailsChange}
            onAmountChange={handleAmountChange}
            onBatchFromTo={handleBatchFromTo}
            selectedKeys={selectedKeys}
            onSelectionChange={setSelectedKeys}
            onBatchCategorize={handleBatchCategorize}
            onTransactionsRefresh={loadData}
          />
        </div>
        {/* Right: Charts */}
        <div className="w-[45%] min-w-0 overflow-y-auto p-3">
          <FinancialCharts volumeData={filteredVolumeData} transactions={filteredTransactions} categoryColorMap={categoryColorMap} />
        </div>
      </div>

      {/* Add Category Modal */}
      <AddCategoryModal
        isOpen={showAddCategoryModal}
        onClose={() => setShowAddCategoryModal(false)}
        onSubmit={handleCreateCategory}
        existingNames={categoryNames}
      />
    </div>
  );
}
