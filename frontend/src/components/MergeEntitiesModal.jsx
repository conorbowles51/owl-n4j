import React, { useState, useEffect } from 'react';
import { X, Merge, ArrowRight, Plus, Trash2 } from 'lucide-react';

/**
 * MergeEntitiesModal Component
 *
 * Modal for merging two entities with side-by-side comparison
 */
export default function MergeEntitiesModal({
  isOpen,
  onClose,
  onSuccess,  // Called after successful merge with { entity1, entity2 }
  entity1,
  entity2,
  onMerge,
  similarity = null,
}) {
  const [mergedName, setMergedName] = useState('');
  const [mergedSummary, setMergedSummary] = useState('');
  const [mergedType, setMergedType] = useState('');
  const [nameMode, setNameMode] = useState('entity1'); // 'entity1', 'entity2', 'both'
  const [summaryMode, setSummaryMode] = useState('entity1'); // 'entity1', 'entity2', 'both'
  const [isMerging, setIsMerging] = useState(false);
  const [error, setError] = useState(null);

  // Track facts and insights with source and selection state
  // Each item: { data: original fact/insight object, source: 'entity1' | 'entity2', selected: boolean }
  const [factsWithMeta, setFactsWithMeta] = useState([]);
  const [insightsWithMeta, setInsightsWithMeta] = useState([]);
  const [customFields, setCustomFields] = useState([]); // Array of { name: '', value: '' } for new fields

  // Initialize form when modal opens
  useEffect(() => {
    if (isOpen && entity1 && entity2) {
      // Default to entity1's values
      setMergedName(entity1.name || '');
      setMergedSummary(entity1.summary || '');
      setMergedType(entity1.type || '');
      setNameMode('entity1');
      setSummaryMode('entity1');
      setError(null);

      // Build facts list with source tags, all selected by default
      const facts1 = (entity1.verified_facts || []).map(f => ({
        data: f,
        source: 'entity1',
        selected: true,
      }));
      const facts2 = (entity2.verified_facts || []).map(f => ({
        data: f,
        source: 'entity2',
        selected: true,
      }));
      setFactsWithMeta([...facts1, ...facts2]);

      // Build insights list with source tags, all selected by default
      const insights1 = (entity1.ai_insights || []).map(i => ({
        data: i,
        source: 'entity1',
        selected: true,
      }));
      const insights2 = (entity2.ai_insights || []).map(i => ({
        data: i,
        source: 'entity2',
        selected: true,
      }));
      setInsightsWithMeta([...insights1, ...insights2]);
      
      // Initialize custom fields as empty
      setCustomFields([]);
    }
  }, [isOpen, entity1, entity2]);

  // Update merged values when toggles change
  useEffect(() => {
    if (entity1 && entity2) {
      if (nameMode === 'entity1') {
        setMergedName(entity1.name || '');
      } else if (nameMode === 'entity2') {
        setMergedName(entity2.name || '');
      } else if (nameMode === 'both') {
        // Combine both names with a separator
        const name1 = entity1.name || '';
        const name2 = entity2.name || '';
        if (name1 && name2) {
          // Only combine if both exist and are different
          if (name1.toLowerCase() !== name2.toLowerCase()) {
            setMergedName(`${name1} / ${name2}`);
          } else {
            setMergedName(name1);
          }
        } else {
          setMergedName(name1 || name2);
        }
      }
    }
  }, [nameMode, entity1, entity2]);

  useEffect(() => {
    if (entity1 && entity2) {
      if (summaryMode === 'entity1') {
        setMergedSummary(entity1.summary || '');
      } else if (summaryMode === 'entity2') {
        setMergedSummary(entity2.summary || '');
      } else if (summaryMode === 'both') {
        // Combine both summaries
        const summary1 = entity1.summary || '';
        const summary2 = entity2.summary || '';
        if (summary1 && summary2) {
          setMergedSummary(`${summary1}\n\n---\n\n${summary2}`);
        } else {
          setMergedSummary(summary1 || summary2);
        }
      }
    }
  }, [summaryMode, entity1, entity2]);

  if (!isOpen || !entity1 || !entity2) return null;

  // Toggle fact selection
  const toggleFactSelection = (index) => {
    setFactsWithMeta(prev => prev.map((item, i) =>
      i === index ? { ...item, selected: !item.selected } : item
    ));
  };

  // Toggle insight selection
  const toggleInsightSelection = (index) => {
    setInsightsWithMeta(prev => prev.map((item, i) =>
      i === index ? { ...item, selected: !item.selected } : item
    ));
  };

  // Get text from fact/insight (handles both object and string formats)
  const getItemText = (item) => {
    if (typeof item === 'object' && item !== null) {
      return item.text || JSON.stringify(item);
    }
    return item;
  };

  const handleMerge = async () => {
    if (!mergedName.trim()) {
      setError('Name is required');
      return;
    }

    setError(null);
    setIsMerging(true);

    try {
      // Get only selected facts and insights (extract the original data)
      const selectedFacts = factsWithMeta
        .filter(f => f.selected)
        .map(f => f.data);
      const selectedInsights = insightsWithMeta
        .filter(i => i.selected)
        .map(i => i.data);

      // Build properties object with custom fields
      const properties = {};
      customFields.forEach(customField => {
        const fieldName = customField.name.trim();
        const fieldValue = customField.value.trim();
        if (fieldName && fieldValue) {
          // Try to parse as number or boolean, otherwise keep as string
          if (fieldValue === 'true' || fieldValue === 'false') {
            properties[fieldName] = fieldValue === 'true';
          } else if (!isNaN(fieldValue) && fieldValue !== '') {
            properties[fieldName] = parseFloat(fieldValue);
          } else {
            properties[fieldName] = fieldValue;
          }
        }
      });
      
      const mergedData = {
        name: mergedName.trim(),
        summary: mergedSummary.trim() || null,
        verified_facts: selectedFacts,
        ai_insights: selectedInsights,
        type: mergedType || entity1.type || entity2.type,
        properties: properties,
      };

      await onMerge(entity1.key, entity2.key, mergedData);
      if (onSuccess) onSuccess({ entity1, entity2 });
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to merge entities');
    } finally {
      setIsMerging(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  const selectedFactsCount = factsWithMeta.filter(f => f.selected).length;
  const selectedInsightsCount = insightsWithMeta.filter(i => i.selected).length;

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      onClick={onClose}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-labelledby="merge-entities-title"
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200 bg-owl-blue-50">
          <div className="flex items-center gap-2">
            <Merge className="w-5 h-5 text-owl-blue-600" />
            <h2 id="merge-entities-title" className="text-lg font-semibold text-owl-blue-900">
              Merge Entities
            </h2>
            {similarity !== null && (
              <span className="text-sm text-light-600 ml-2">
                ({Math.round(similarity * 100)}% similarity)
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Side-by-side comparison */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            {/* Entity 1 */}
            <div className="border border-light-200 rounded-lg p-4 bg-light-50">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-owl-blue-900">Entity 1 (Source - will be deleted)</h3>
                <span className="text-xs px-2 py-1 bg-red-100 text-red-800 rounded">Source</span>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Name</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm">
                    {entity1.name || <span className="text-light-400 italic">No name</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Type</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm">
                    {entity1.type || <span className="text-light-400 italic">No type</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Summary</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm max-h-32 overflow-y-auto whitespace-pre-wrap">
                    {entity1.summary || <span className="text-light-400 italic">No summary</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Verified Facts ({entity1.verified_facts?.length || 0})</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm max-h-32 overflow-y-auto">
                    {entity1.verified_facts?.length > 0 ? (
                      <ul className="list-disc list-inside space-y-1">
                        {entity1.verified_facts.map((fact, i) => (
                          <li key={i} className="text-light-700">{getItemText(fact)}</li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-light-400 italic">No verified facts</span>
                    )}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">AI Insights ({entity1.ai_insights?.length || 0})</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm max-h-32 overflow-y-auto">
                    {entity1.ai_insights?.length > 0 ? (
                      <ul className="list-disc list-inside space-y-1">
                        {entity1.ai_insights.map((insight, i) => (
                          <li key={i} className="text-light-700">{getItemText(insight)}</li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-light-400 italic">No AI insights</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Entity 2 */}
            <div className="border border-light-200 rounded-lg p-4 bg-light-50">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-owl-blue-900">Entity 2 (Target - will be kept)</h3>
                <span className="text-xs px-2 py-1 bg-green-100 text-green-800 rounded">Target</span>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Name</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm">
                    {entity2.name || <span className="text-light-400 italic">No name</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Type</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm">
                    {entity2.type || <span className="text-light-400 italic">No type</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Summary</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm max-h-32 overflow-y-auto whitespace-pre-wrap">
                    {entity2.summary || <span className="text-light-400 italic">No summary</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Verified Facts ({entity2.verified_facts?.length || 0})</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm max-h-32 overflow-y-auto">
                    {entity2.verified_facts?.length > 0 ? (
                      <ul className="list-disc list-inside space-y-1">
                        {entity2.verified_facts.map((fact, i) => (
                          <li key={i} className="text-light-700">{getItemText(fact)}</li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-light-400 italic">No verified facts</span>
                    )}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">AI Insights ({entity2.ai_insights?.length || 0})</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm max-h-32 overflow-y-auto">
                    {entity2.ai_insights?.length > 0 ? (
                      <ul className="list-disc list-inside space-y-1">
                        {entity2.ai_insights.map((insight, i) => (
                          <li key={i} className="text-light-700">{getItemText(insight)}</li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-light-400 italic">No AI insights</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Merge Configuration */}
          <div className="border-t border-light-200 pt-6">
            <h3 className="font-semibold text-owl-blue-900 mb-4 flex items-center gap-2">
              <ArrowRight className="w-4 h-4" />
              Merged Result
            </h3>
            <div className="space-y-4">
              {/* Name */}
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <label className="text-sm font-medium text-light-800">Name *</label>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setNameMode('entity1')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        nameMode === 'entity1'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Entity 1
                    </button>
                    <button
                      onClick={() => setNameMode('entity2')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        nameMode === 'entity2'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Entity 2
                    </button>
                    <button
                      onClick={() => setNameMode('both')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        nameMode === 'both'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Both
                    </button>
                  </div>
                </div>
                <input
                  type="text"
                  value={mergedName}
                  onChange={(e) => setMergedName(e.target.value)}
                  className="w-full p-2 border border-light-300 rounded-md focus:ring-owl-blue-500 focus:border-owl-blue-500"
                  placeholder="Merged entity name"
                />
                {nameMode === 'both' && (
                  <p className="mt-1 text-xs text-light-600">
                    Names will be combined with " / " separator. You can edit manually.
                  </p>
                )}
              </div>

              {/* Type */}
              <div>
                <label className="text-sm font-medium text-light-800 mb-2 block">Type</label>
                <input
                  type="text"
                  value={mergedType}
                  onChange={(e) => setMergedType(e.target.value)}
                  className="w-full p-2 border border-light-300 rounded-md focus:ring-owl-blue-500 focus:border-owl-blue-500"
                  placeholder="Entity type"
                />
              </div>

              {/* Summary */}
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <label className="text-sm font-medium text-light-800">Summary</label>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setSummaryMode('entity1')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        summaryMode === 'entity1'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Entity 1
                    </button>
                    <button
                      onClick={() => setSummaryMode('entity2')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        summaryMode === 'entity2'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Entity 2
                    </button>
                    <button
                      onClick={() => setSummaryMode('both')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        summaryMode === 'both'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Both
                    </button>
                  </div>
                </div>
                <textarea
                  value={mergedSummary}
                  onChange={(e) => setMergedSummary(e.target.value)}
                  className="w-full p-2 border border-light-300 rounded-md focus:ring-owl-blue-500 focus:border-owl-blue-500"
                  rows={4}
                  placeholder="Merged summary"
                />
                {summaryMode === 'both' && (
                  <p className="mt-1 text-xs text-light-600">
                    Summaries will be combined with a separator. You can edit manually.
                  </p>
                )}
              </div>

              {/* Verified Facts with checkboxes */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-light-800">Verified Facts</label>
                  <span className="text-xs text-light-600">
                    {selectedFactsCount} of {factsWithMeta.length} selected
                  </span>
                </div>
                <div className="border border-light-300 rounded-md bg-light-50 max-h-48 overflow-y-auto">
                  {factsWithMeta.length > 0 ? (
                    <div className="divide-y divide-light-200">
                      {factsWithMeta.map((item, index) => (
                        <label
                          key={index}
                          className={`flex items-start gap-3 p-3 cursor-pointer hover:bg-light-100 transition-colors ${
                            !item.selected ? 'opacity-50' : ''
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={item.selected}
                            onChange={() => toggleFactSelection(index)}
                            className="mt-1 h-4 w-4 text-owl-blue-600 rounded border-light-300 focus:ring-owl-blue-500"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                                item.source === 'entity1'
                                  ? 'bg-red-100 text-red-700'
                                  : 'bg-green-100 text-green-700'
                              }`}>
                                {item.source === 'entity1' ? 'E1' : 'E2'}
                              </span>
                            </div>
                            <p className={`text-sm text-light-700 ${!item.selected ? 'line-through' : ''}`}>
                              {getItemText(item.data)}
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <div className="p-3 text-sm text-light-400 italic">
                      No verified facts to merge
                    </div>
                  )}
                </div>
              </div>

              {/* AI Insights with checkboxes */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-light-800">AI Insights</label>
                  <span className="text-xs text-light-600">
                    {selectedInsightsCount} of {insightsWithMeta.length} selected
                  </span>
                </div>
                <div className="border border-light-300 rounded-md bg-light-50 max-h-48 overflow-y-auto">
                  {insightsWithMeta.length > 0 ? (
                    <div className="divide-y divide-light-200">
                      {insightsWithMeta.map((item, index) => (
                        <label
                          key={index}
                          className={`flex items-start gap-3 p-3 cursor-pointer hover:bg-light-100 transition-colors ${
                            !item.selected ? 'opacity-50' : ''
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={item.selected}
                            onChange={() => toggleInsightSelection(index)}
                            className="mt-1 h-4 w-4 text-owl-blue-600 rounded border-light-300 focus:ring-owl-blue-500"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                                item.source === 'entity1'
                                  ? 'bg-red-100 text-red-700'
                                  : 'bg-green-100 text-green-700'
                              }`}>
                                {item.source === 'entity1' ? 'E1' : 'E2'}
                              </span>
                            </div>
                            <p className={`text-sm text-light-700 ${!item.selected ? 'line-through' : ''}`}>
                              {getItemText(item.data)}
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <div className="p-3 text-sm text-light-400 italic">
                      No AI insights to merge
                    </div>
                  )}
                </div>
              </div>

              {/* Custom/New Fields */}
              <div className="border-t border-light-200 pt-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-owl-blue-900">
                    Custom Fields ({customFields.length})
                  </h3>
                  <button
                    type="button"
                    onClick={() => {
                      setCustomFields(prev => [...prev, { name: '', value: '' }]);
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-owl-blue-600 hover:text-owl-blue-700 hover:bg-owl-blue-50 rounded-md transition-colors"
                    disabled={isMerging}
                  >
                    <Plus className="w-4 h-4" />
                    Add Field
                  </button>
                </div>
                <div className="space-y-3">
                  {customFields.map((customField, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={customField.name}
                        onChange={(e) => {
                          setCustomFields(prev => {
                            const updated = [...prev];
                            updated[index] = { ...updated[index], name: e.target.value };
                            return updated;
                          });
                        }}
                        className="flex-1 px-3 py-2 border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
                        placeholder="Field name"
                        disabled={isMerging}
                      />
                      <input
                        type="text"
                        value={customField.value}
                        onChange={(e) => {
                          setCustomFields(prev => {
                            const updated = [...prev];
                            updated[index] = { ...updated[index], value: e.target.value };
                            return updated;
                          });
                        }}
                        className="flex-1 px-3 py-2 border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
                        placeholder="Field value"
                        disabled={isMerging}
                      />
                      <button
                        type="button"
                        onClick={() => {
                          setCustomFields(prev => prev.filter((_, i) => i !== index));
                        }}
                        className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-md transition-colors"
                        disabled={isMerging}
                        title="Remove field"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                  {customFields.length === 0 && (
                    <p className="text-xs text-light-500 italic">
                      No custom fields added. Click "Add Field" to create a new property.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>

          {error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* Warning */}
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-yellow-800 text-sm">
            <strong>Warning:</strong> This action will delete Entity 1 and merge all its relationships into Entity 2.
            This cannot be undone.
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-light-200 bg-light-50">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-light-200 text-light-800 rounded-md hover:bg-light-300 transition-colors"
            disabled={isMerging}
          >
            Cancel
          </button>
          <button
            onClick={handleMerge}
            disabled={isMerging || !mergedName.trim()}
            className="px-4 py-2 bg-owl-blue-600 text-white rounded-md hover:bg-owl-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <Merge className="w-4 h-4" />
            {isMerging ? 'Merging...' : 'Merge Entities'}
          </button>
        </div>
      </div>
    </div>
  );
}
