import React, { useState, useEffect, useMemo } from 'react';
import { Loader2, Search, Users, Building2, Landmark, CreditCard, ChevronDown } from 'lucide-react';
import { graphAPI } from '../../services/api';

const TABS = [
  { key: 'All', label: 'All', icon: null },
  { key: 'Person', label: 'People', icon: Users },
  { key: 'Company', label: 'Companies', icon: Building2 },
  { key: 'Organisation', label: 'Organisations', icon: Building2 },
  { key: 'Bank', label: 'Banks', icon: Landmark },
  { key: 'BankAccount', label: 'Accounts', icon: CreditCard },
];

const SORT_OPTIONS = [
  { key: 'name', label: 'Name' },
  { key: 'type', label: 'Type' },
  { key: 'facts', label: 'Most Facts' },
  { key: 'insights', label: 'Most Insights' },
];

const TYPE_COLORS = {
  Person: 'bg-blue-500',
  Company: 'bg-emerald-500',
  Organisation: 'bg-purple-500',
  Bank: 'bg-amber-500',
  BankAccount: 'bg-rose-500',
};

export default function EntitySummarySection({ caseId }) {
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [sortOpen, setSortOpen] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    graphAPI.getEntitySummary(caseId)
      .then((data) => {
        if (!cancelled) setEntities(data.entities || []);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Failed to load entity summary');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [caseId]);

  const tabCounts = useMemo(() => {
    const counts = { All: entities.length };
    TABS.forEach((t) => {
      if (t.key !== 'All') counts[t.key] = entities.filter((e) => e.type === t.key).length;
    });
    return counts;
  }, [entities]);

  const filtered = useMemo(() => {
    let list = entities;
    if (activeTab !== 'All') list = list.filter((e) => e.type === activeTab);
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter((e) => e.name?.toLowerCase().includes(q));
    }
    const sorted = [...list];
    switch (sortBy) {
      case 'name': sorted.sort((a, b) => (a.name || '').localeCompare(b.name || '')); break;
      case 'type': sorted.sort((a, b) => (a.type || '').localeCompare(b.type || '') || (a.name || '').localeCompare(b.name || '')); break;
      case 'facts': sorted.sort((a, b) => (b.facts_count || 0) - (a.facts_count || 0)); break;
      case 'insights': sorted.sort((a, b) => (b.insights_count || 0) - (a.insights_count || 0)); break;
    }
    return sorted;
  }, [entities, activeTab, searchQuery, sortBy]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full py-12">
        <Loader2 className="w-5 h-5 animate-spin text-owl-blue-600" />
        <span className="ml-2 text-sm text-light-500">Loading entities…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full py-12 px-4">
        <p className="text-sm text-red-500">{error}</p>
      </div>
    );
  }

  if (entities.length === 0) {
    return (
      <div className="flex items-center justify-center h-full py-12 px-4">
        <p className="text-sm text-light-500">No key entities found for this case.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 px-3 py-2 border-b border-light-200">
        <h3 className="text-sm font-semibold text-owl-blue-900">Entity Summary</h3>
      </div>

      {/* Tabs */}
      <div className="flex-shrink-0 flex flex-wrap gap-1 px-3 py-2 border-b border-light-200 bg-light-50">
        {TABS.map((tab) => {
          const count = tabCounts[tab.key] || 0;
          if (tab.key !== 'All' && count === 0) return null;
          const active = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1 px-2 py-1 text-xs rounded-md transition-colors ${
                active
                  ? 'bg-owl-blue-100 text-owl-blue-700 font-medium'
                  : 'text-light-600 hover:bg-light-100'
              }`}
            >
              {tab.icon && <tab.icon className="w-3 h-3" />}
              {tab.label}
              <span className={`ml-0.5 px-1 py-0 rounded-full text-[10px] leading-4 ${
                active ? 'bg-owl-blue-200 text-owl-blue-800' : 'bg-light-200 text-light-500'
              }`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Search + Sort */}
      <div className="flex-shrink-0 flex items-center gap-2 px-3 py-2 border-b border-light-200">
        <div className="flex-1 flex items-center gap-1.5 px-2 py-1 bg-light-50 border border-light-200 rounded-md">
          <Search className="w-3.5 h-3.5 text-light-400 flex-shrink-0" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search entities…"
            className="flex-1 bg-transparent text-xs text-light-700 placeholder-light-400 outline-none"
          />
        </div>
        <div className="relative">
          <button
            onClick={() => setSortOpen(!sortOpen)}
            className="flex items-center gap-1 px-2 py-1 text-xs text-light-600 bg-light-50 border border-light-200 rounded-md hover:bg-light-100 transition-colors"
          >
            {SORT_OPTIONS.find((o) => o.key === sortBy)?.label}
            <ChevronDown className="w-3 h-3" />
          </button>
          {sortOpen && (
            <div className="absolute right-0 top-full mt-1 z-10 bg-white border border-light-200 rounded-md shadow-lg py-1 min-w-[120px]">
              {SORT_OPTIONS.map((opt) => (
                <button
                  key={opt.key}
                  onClick={() => { setSortBy(opt.key); setSortOpen(false); }}
                  className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                    sortBy === opt.key ? 'bg-owl-blue-50 text-owl-blue-700 font-medium' : 'text-light-700 hover:bg-light-50'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Entity List */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <p className="text-xs text-light-500">No matching entities.</p>
          </div>
        ) : (
          <div className="divide-y divide-light-100">
            {filtered.map((entity) => (
              <div
                key={entity.key}
                className="flex items-center gap-2.5 px-3 py-2 hover:bg-light-50 cursor-pointer transition-colors"
              >
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${TYPE_COLORS[entity.type] || 'bg-gray-400'}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-owl-blue-900 truncate">{entity.name}</p>
                  {entity.summary && (
                    <p className="text-[11px] text-light-500 truncate">{entity.summary}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {entity.facts_count > 0 && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-emerald-50 text-emerald-700 rounded-full">
                      {entity.facts_count}F
                    </span>
                  )}
                  {entity.insights_count > 0 && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded-full">
                      {entity.insights_count}I
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
