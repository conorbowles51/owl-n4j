import React, { useState, useMemo, useEffect } from 'react';
import { X, Merge, ChevronRight, ChevronLeft, Check, AlertTriangle, Loader2 } from 'lucide-react';
import { graphAPI } from '../services/api';

/**
 * BulkMergeModal — 3-step wizard for merging 3+ entities into one.
 *
 * Step 1: Select target entity (the survivor)
 * Step 2: Configure merged properties (name, type, summary, facts, insights)
 * Step 3: Review and confirm
 */
export default function BulkMergeModal({ isOpen, onClose, entities = [], graphLinks = [], caseId, onMergeComplete }) {
  const [step, setStep] = useState(1);
  const [targetKey, setTargetKey] = useState(null);
  const [mergedName, setMergedName] = useState('');
  const [mergedType, setMergedType] = useState('');
  const [mergedSummary, setMergedSummary] = useState('');
  const [summaryMode, setSummaryMode] = useState('target'); // 'target' | 'combine'
  const [factsWithMeta, setFactsWithMeta] = useState([]);
  const [insightsWithMeta, setInsightsWithMeta] = useState([]);
  const [isMerging, setIsMerging] = useState(false);
  const [error, setError] = useState(null);

  // Compute relationship counts per entity
  const relCounts = useMemo(() => {
    const counts = {};
    entities.forEach(e => { counts[e.key] = 0; });
    (graphLinks || []).forEach(l => {
      const src = typeof l.source === 'object' ? l.source?.key : l.source;
      const tgt = typeof l.target === 'object' ? l.target?.key : l.target;
      if (counts[src] !== undefined) counts[src]++;
      if (counts[tgt] !== undefined) counts[tgt]++;
    });
    return counts;
  }, [entities, graphLinks]);

  // Auto-select target with most relationships on open
  useEffect(() => {
    if (isOpen && entities.length > 0) {
      setStep(1);
      setError(null);
      const best = entities.reduce((a, b) => (relCounts[a.key] || 0) >= (relCounts[b.key] || 0) ? a : b);
      setTargetKey(best.key);
    }
  }, [isOpen, entities, relCounts]);

  // When target changes or step advances to 2, initialize merge properties
  useEffect(() => {
    if (step === 2 && targetKey) {
      const target = entities.find(e => e.key === targetKey);
      if (target) {
        setMergedName(target.name || '');
        setMergedType(target.type || '');
        const targetSummary = target.summary || '';
        setMergedSummary(targetSummary);
        setSummaryMode('target');

        // Build facts and insights from all entities
        const normalize = (s) => (s || '').toLowerCase().trim().replace(/\s+/g, ' ');
        const seenFacts = new Set();
        const allFacts = [];
        const seenInsights = new Set();
        const allInsights = [];

        entities.forEach(entity => {
          let facts = entity.verified_facts || [];
          if (typeof facts === 'string') try { facts = JSON.parse(facts); } catch { facts = []; }
          facts.forEach(f => {
            const text = typeof f === 'string' ? f : (f.text || JSON.stringify(f));
            const norm = normalize(text);
            const isDup = seenFacts.has(norm);
            seenFacts.add(norm);
            allFacts.push({ data: f, source: entity.name, selected: !isDup, isDuplicate: isDup });
          });

          let insights = entity.ai_insights || [];
          if (typeof insights === 'string') try { insights = JSON.parse(insights); } catch { insights = []; }
          insights.forEach(i => {
            const text = typeof i === 'string' ? i : (i.text || JSON.stringify(i));
            const norm = normalize(text);
            const isDup = seenInsights.has(norm);
            seenInsights.add(norm);
            allInsights.push({ data: i, source: entity.name, selected: !isDup, isDuplicate: isDup });
          });
        });

        setFactsWithMeta(allFacts);
        setInsightsWithMeta(allInsights);
      }
    }
  }, [step, targetKey, entities]);

  // Unique names and types for suggestion chips
  const uniqueNames = useMemo(() => {
    const seen = new Set();
    return entities.map(e => e.name).filter(n => {
      const lower = (n || '').toLowerCase().trim();
      if (!lower || seen.has(lower)) return false;
      seen.add(lower);
      return true;
    });
  }, [entities]);

  const uniqueTypes = useMemo(() => {
    const seen = new Set();
    return entities.map(e => e.type).filter(t => {
      const lower = (t || '').toLowerCase().trim();
      if (!lower || seen.has(lower)) return false;
      seen.add(lower);
      return true;
    });
  }, [entities]);

  // Combined summary
  const combinedSummary = useMemo(() => {
    const seen = new Set();
    return entities
      .map(e => (e.summary || '').trim())
      .filter(s => {
        if (!s) return false;
        const norm = s.toLowerCase();
        if (seen.has(norm)) return false;
        seen.add(norm);
        return true;
      })
      .join('\n\n---\n\n');
  }, [entities]);

  useEffect(() => {
    if (summaryMode === 'combine') {
      setMergedSummary(combinedSummary);
    } else if (summaryMode === 'target') {
      const target = entities.find(e => e.key === targetKey);
      setMergedSummary(target?.summary || '');
    }
  }, [summaryMode, combinedSummary, targetKey, entities]);

  const targetEntity = entities.find(e => e.key === targetKey);
  const sourceEntities = entities.filter(e => e.key !== targetKey);
  const selectedFactsCount = factsWithMeta.filter(f => f.selected).length;
  const selectedInsightsCount = insightsWithMeta.filter(i => i.selected).length;

  const handleMerge = async () => {
    if (!targetKey || sourceEntities.length === 0) return;
    setIsMerging(true);
    setError(null);

    try {
      const mergedData = {
        name: mergedName.trim(),
        summary: mergedSummary.trim() || null,
        type: mergedType || targetEntity?.type || 'Other',
        verified_facts: factsWithMeta.filter(f => f.selected).map(f => f.data),
        ai_insights: insightsWithMeta.filter(i => i.selected).map(i => i.data),
        properties: {},
      };

      await graphAPI.bulkMergeEntities(
        caseId,
        targetKey,
        sourceEntities.map(e => e.key),
        mergedData
      );

      window.dispatchEvent(new Event('entities-refresh'));
      if (onMergeComplete) onMergeComplete();
      onClose();
    } catch (err) {
      console.error('Bulk merge failed:', err);
      setError(err.message || 'Failed to merge entities');
    } finally {
      setIsMerging(false);
    }
  };

  if (!isOpen || entities.length < 2) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl mx-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200 bg-owl-blue-50">
          <div className="flex items-center gap-2">
            <Merge className="w-5 h-5 text-owl-blue-600" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              Merge {entities.length} Entities
            </h2>
            <span className="text-sm text-light-500 ml-2">Step {step} of 3</span>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded" disabled={isMerging}>
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-1 px-4 py-2 bg-light-50 border-b border-light-200">
          {['Select Target', 'Configure', 'Review'].map((label, i) => (
            <React.Fragment key={i}>
              {i > 0 && <ChevronRight className="w-3 h-3 text-light-400" />}
              <span className={`text-xs px-2 py-0.5 rounded ${step === i + 1 ? 'bg-owl-blue-600 text-white font-medium' : step > i + 1 ? 'text-owl-blue-600' : 'text-light-500'}`}>
                {label}
              </span>
            </React.Fragment>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <AlertTriangle className="w-4 h-4 inline mr-1" /> {error}
            </div>
          )}

          {/* STEP 1: Select Target */}
          {step === 1 && (
            <div>
              <p className="text-sm text-light-600 mb-3">
                Select which entity will be the <strong>target</strong> (survivor). All other entities will be merged into it and soft-deleted.
              </p>
              <table className="w-full text-sm">
                <thead className="bg-light-100">
                  <tr>
                    <th className="px-3 py-2 text-left w-10"></th>
                    <th className="px-3 py-2 text-left">Name</th>
                    <th className="px-3 py-2 text-left">Type</th>
                    <th className="px-3 py-2 text-right">Relationships</th>
                    <th className="px-3 py-2 text-right">Facts</th>
                  </tr>
                </thead>
                <tbody>
                  {entities.map(entity => {
                    const facts = Array.isArray(entity.verified_facts) ? entity.verified_facts : [];
                    return (
                      <tr
                        key={entity.key}
                        className={`border-b border-light-100 cursor-pointer hover:bg-owl-blue-50 transition-colors ${targetKey === entity.key ? 'bg-owl-blue-50' : ''}`}
                        onClick={() => setTargetKey(entity.key)}
                      >
                        <td className="px-3 py-2">
                          <input
                            type="radio"
                            checked={targetKey === entity.key}
                            onChange={() => setTargetKey(entity.key)}
                            className="text-owl-blue-600"
                          />
                        </td>
                        <td className="px-3 py-2 font-medium text-owl-blue-900">{entity.name}</td>
                        <td className="px-3 py-2 text-light-600">{entity.type}</td>
                        <td className="px-3 py-2 text-right text-light-600">{relCounts[entity.key] || 0}</td>
                        <td className="px-3 py-2 text-right text-light-600">{facts.length}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* STEP 2: Configure Properties */}
          {step === 2 && (
            <div className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-owl-blue-900 mb-1">Merged Name *</label>
                <input
                  type="text"
                  value={mergedName}
                  onChange={e => setMergedName(e.target.value)}
                  className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
                />
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {uniqueNames.map(name => (
                    <button
                      key={name}
                      onClick={() => setMergedName(name)}
                      className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                        mergedName === name
                          ? 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-800'
                          : 'bg-light-50 border-light-200 text-light-600 hover:bg-light-100'
                      }`}
                    >
                      {name}
                    </button>
                  ))}
                </div>
              </div>

              {/* Type */}
              <div>
                <label className="block text-sm font-medium text-owl-blue-900 mb-1">Entity Type</label>
                <input
                  type="text"
                  value={mergedType}
                  onChange={e => setMergedType(e.target.value)}
                  className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
                />
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {uniqueTypes.map(type => (
                    <button
                      key={type}
                      onClick={() => setMergedType(type)}
                      className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                        mergedType === type
                          ? 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-800'
                          : 'bg-light-50 border-light-200 text-light-600 hover:bg-light-100'
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>

              {/* Summary */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-sm font-medium text-owl-blue-900">Summary</label>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setSummaryMode('target')}
                      className={`text-xs px-2 py-0.5 rounded ${summaryMode === 'target' ? 'bg-owl-blue-600 text-white' : 'bg-light-100 text-light-600'}`}
                    >
                      Target only
                    </button>
                    <button
                      onClick={() => setSummaryMode('combine')}
                      className={`text-xs px-2 py-0.5 rounded ${summaryMode === 'combine' ? 'bg-owl-blue-600 text-white' : 'bg-light-100 text-light-600'}`}
                    >
                      Combine all
                    </button>
                  </div>
                </div>
                <textarea
                  value={mergedSummary}
                  onChange={e => setMergedSummary(e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                />
              </div>

              {/* Facts */}
              {factsWithMeta.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-sm font-medium text-owl-blue-900">
                      Verified Facts ({selectedFactsCount} of {factsWithMeta.length})
                    </label>
                    <div className="flex gap-1">
                      <button onClick={() => setFactsWithMeta(f => f.map(x => ({ ...x, selected: true })))} className="text-xs text-owl-blue-600 hover:underline">Select all</button>
                      <button onClick={() => setFactsWithMeta(f => f.map(x => ({ ...x, selected: false })))} className="text-xs text-light-500 hover:underline ml-2">Deselect all</button>
                    </div>
                  </div>
                  <div className="max-h-48 overflow-y-auto border border-light-200 rounded-lg">
                    {factsWithMeta.map((item, idx) => {
                      const text = typeof item.data === 'string' ? item.data : (item.data.text || JSON.stringify(item.data));
                      return (
                        <label
                          key={idx}
                          className={`flex items-start gap-2 px-3 py-1.5 border-b border-light-100 cursor-pointer hover:bg-light-50 ${!item.selected ? 'opacity-50' : ''}`}
                        >
                          <input
                            type="checkbox"
                            checked={item.selected}
                            onChange={() => setFactsWithMeta(f => f.map((x, i) => i === idx ? { ...x, selected: !x.selected } : x))}
                            className="mt-0.5 rounded border-light-300"
                          />
                          <span className="text-xs flex-1">
                            <span className={`inline-block px-1 py-0.5 rounded text-[10px] font-medium mr-1 ${item.isDuplicate ? 'bg-yellow-100 text-yellow-700' : 'bg-light-100 text-light-600'}`}>
                              {item.isDuplicate ? 'dup' : item.source?.slice(0, 12)}
                            </span>
                            {text.length > 120 ? text.slice(0, 120) + '...' : text}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Insights */}
              {insightsWithMeta.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-sm font-medium text-owl-blue-900">
                      AI Insights ({selectedInsightsCount} of {insightsWithMeta.length})
                    </label>
                    <div className="flex gap-1">
                      <button onClick={() => setInsightsWithMeta(f => f.map(x => ({ ...x, selected: true })))} className="text-xs text-owl-blue-600 hover:underline">Select all</button>
                      <button onClick={() => setInsightsWithMeta(f => f.map(x => ({ ...x, selected: false })))} className="text-xs text-light-500 hover:underline ml-2">Deselect all</button>
                    </div>
                  </div>
                  <div className="max-h-48 overflow-y-auto border border-light-200 rounded-lg">
                    {insightsWithMeta.map((item, idx) => {
                      const text = typeof item.data === 'string' ? item.data : (item.data.text || JSON.stringify(item.data));
                      return (
                        <label
                          key={idx}
                          className={`flex items-start gap-2 px-3 py-1.5 border-b border-light-100 cursor-pointer hover:bg-light-50 ${!item.selected ? 'opacity-50' : ''}`}
                        >
                          <input
                            type="checkbox"
                            checked={item.selected}
                            onChange={() => setInsightsWithMeta(f => f.map((x, i) => i === idx ? { ...x, selected: !x.selected } : x))}
                            className="mt-0.5 rounded border-light-300"
                          />
                          <span className="text-xs flex-1">
                            <span className={`inline-block px-1 py-0.5 rounded text-[10px] font-medium mr-1 ${item.isDuplicate ? 'bg-yellow-100 text-yellow-700' : 'bg-light-100 text-light-600'}`}>
                              {item.isDuplicate ? 'dup' : item.source?.slice(0, 12)}
                            </span>
                            {text.length > 120 ? text.slice(0, 120) + '...' : text}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* STEP 3: Review & Confirm */}
          {step === 3 && (
            <div className="space-y-4">
              <div className="p-4 bg-owl-blue-50 rounded-lg border border-owl-blue-200">
                <h3 className="text-sm font-semibold text-owl-blue-900 mb-2">Target Entity (will survive)</h3>
                <p className="text-sm"><strong>{mergedName}</strong> ({mergedType})</p>
                {mergedSummary && (
                  <p className="text-xs text-light-600 mt-1 line-clamp-3">{mergedSummary}</p>
                )}
              </div>

              <div className="p-4 bg-red-50 rounded-lg border border-red-200">
                <h3 className="text-sm font-semibold text-red-800 mb-2">
                  Will be merged and soft-deleted ({sourceEntities.length} entities)
                </h3>
                <div className="flex flex-wrap gap-1">
                  {sourceEntities.map(e => (
                    <span key={e.key} className="text-xs px-2 py-1 bg-red-100 rounded text-red-700">
                      {e.name} ({e.type})
                    </span>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="p-3 bg-light-50 rounded-lg border border-light-200">
                  <div className="text-lg font-bold text-owl-blue-600">{selectedFactsCount}</div>
                  <div className="text-xs text-light-600">Facts to keep</div>
                </div>
                <div className="p-3 bg-light-50 rounded-lg border border-light-200">
                  <div className="text-lg font-bold text-owl-blue-600">{selectedInsightsCount}</div>
                  <div className="text-xs text-light-600">Insights to keep</div>
                </div>
                <div className="p-3 bg-light-50 rounded-lg border border-light-200">
                  <div className="text-lg font-bold text-owl-blue-600">{entities.length}</div>
                  <div className="text-xs text-light-600">Entities merging</div>
                </div>
              </div>

              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <p className="text-xs text-amber-800">
                  <AlertTriangle className="w-3.5 h-3.5 inline mr-1" />
                  All relationships from the {sourceEntities.length} source entities will be migrated to the target.
                  Deleted entities can be recovered from the recycle bin.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer with navigation */}
        <div className="flex items-center justify-between p-4 border-t border-light-200 bg-light-50">
          <button
            onClick={() => step > 1 ? setStep(step - 1) : onClose()}
            disabled={isMerging}
            className="flex items-center gap-1 px-4 py-2 text-sm text-light-700 bg-white border border-light-300 rounded-lg hover:bg-light-50 disabled:opacity-50"
          >
            <ChevronLeft className="w-4 h-4" />
            {step === 1 ? 'Cancel' : 'Back'}
          </button>

          {step < 3 ? (
            <button
              onClick={() => setStep(step + 1)}
              disabled={step === 1 && !targetKey || step === 2 && !mergedName.trim()}
              className="flex items-center gap-1 px-4 py-2 text-sm font-medium text-white bg-owl-blue-600 rounded-lg hover:bg-owl-blue-700 disabled:opacity-50"
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleMerge}
              disabled={isMerging}
              className="flex items-center gap-2 px-6 py-2 text-sm font-medium text-white bg-owl-blue-600 rounded-lg hover:bg-owl-blue-700 disabled:opacity-50"
            >
              {isMerging ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Merging {entities.length} entities...
                </>
              ) : (
                <>
                  <Merge className="w-4 h-4" />
                  Merge All ({entities.length} entities)
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
