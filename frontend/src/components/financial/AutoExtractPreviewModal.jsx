import { useState, useMemo } from 'react';
import { X, Loader2, CheckCircle2, AlertCircle, Search, Wand2, Sparkles, Link2, Tag } from 'lucide-react';

/**
 * AutoExtractPreviewModal
 *
 * Shows a preview of auto-extracted from/to and category proposals before applying.
 * Displays stats, a searchable table with match badges, and apply/cancel actions.
 */
export default function AutoExtractPreviewModal({
  isOpen,
  onClose,
  preview,       // result from dry_run=true API call
  loading,       // true while dry-run is in progress
  applying,      // true while apply is in progress
  onApply,       // () => void — apply all proposals
  error,         // string|null
}) {
  const [searchFilter, setSearchFilter] = useState('');
  const [expandedCell, setExpandedCell] = useState(null); // "row-col" key

  const toggleCell = (rowIdx, col) => {
    const key = `${rowIdx}-${col}`;
    setExpandedCell(prev => prev === key ? null : key);
  };
  const isCellExpanded = (rowIdx, col) => expandedCell === `${rowIdx}-${col}`;

  const proposals = preview?.proposals || [];

  const filtered = useMemo(() => {
    if (!searchFilter.trim()) return proposals;
    const q = searchFilter.toLowerCase();
    return proposals.filter(p =>
      (p.txn_name || '').toLowerCase().includes(q) ||
      (p.from || '').toLowerCase().includes(q) ||
      (p.to || '').toLowerCase().includes(q) ||
      (p.proposed_category || '').toLowerCase().includes(q)
    );
  }, [proposals, searchFilter]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-[1200px] max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-light-200">
          <div className="flex items-center gap-2">
            <Wand2 className="w-4 h-4 text-owl-blue-600" />
            <span className="text-sm font-semibold text-light-800">Auto-Extract Senders, Beneficiaries & Categories</span>
          </div>
          <button onClick={onClose} className="p-1 text-light-400 hover:text-light-600 rounded" disabled={applying}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-owl-blue-500" />
              <p className="text-sm text-light-600">Analyzing transactions...</p>
              <p className="text-xs text-light-400">This may take a few minutes for large datasets</p>
            </div>
          )}

          {error && !loading && (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <AlertCircle className="w-6 h-6 text-red-400" />
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {!loading && !error && preview && (
            <>
              {/* Stats bar */}
              <div className="flex items-center gap-4 mb-4 p-3 bg-light-50 rounded-lg text-xs text-light-600 flex-wrap">
                <div><span className="font-semibold text-light-800">{preview.total}</span> total</div>
                <div><span className="font-semibold text-light-800">{preview.eligible}</span> eligible</div>
                <div><span className="font-semibold text-owl-blue-600">{preview.proposals_count}</span> proposals</div>
                <div className="flex items-center gap-1">
                  <Sparkles className="w-3 h-3 text-amber-500" />
                  <span>{preview.heuristic_count} heuristic</span>
                </div>
                <div className="flex items-center gap-1">
                  <Wand2 className="w-3 h-3 text-purple-500" />
                  <span>{preview.llm_count} AI</span>
                </div>
                <div className="flex items-center gap-1">
                  <Link2 className="w-3 h-3 text-green-500" />
                  <span>{preview.entity_matches} matched</span>
                </div>
                <div>{preview.custom_names} new names</div>
                {preview.category_proposals_count > 0 && (
                  <div className="flex items-center gap-1">
                    <Tag className="w-3 h-3 text-blue-500" />
                    <span>{preview.category_proposals_count} categories</span>
                  </div>
                )}
              </div>

              {proposals.length === 0 ? (
                <div className="text-center py-12 text-sm text-light-500">
                  No proposals could be generated from the eligible transactions.
                </div>
              ) : (
                <>
                  {/* Search */}
                  <div className="relative mb-3">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
                    <input
                      type="text"
                      placeholder="Filter proposals..."
                      value={searchFilter}
                      onChange={(e) => setSearchFilter(e.target.value)}
                      className="w-64 text-xs pl-8 pr-3 py-1.5 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
                    />
                    {searchFilter && (
                      <span className="ml-2 text-xs text-light-400">
                        {filtered.length} of {proposals.length}
                      </span>
                    )}
                  </div>

                  {/* Table */}
                  <div className="border border-light-200 rounded-lg overflow-hidden">
                    <table className="w-full text-xs table-fixed">
                      <thead className="bg-light-50">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium text-light-600 w-[28%]">Transaction</th>
                          <th className="text-left px-3 py-2 font-medium text-light-600 w-[20%]">From (Sender)</th>
                          <th className="text-left px-3 py-2 font-medium text-light-600 w-[20%]">To (Beneficiary)</th>
                          <th className="text-left px-3 py-2 font-medium text-light-600 w-[18%]">Category</th>
                          <th className="text-center px-3 py-2 font-medium text-light-600 w-[14%]">Source</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-light-100">
                        {filtered.map((p, i) => (
                          <tr key={p.txn_key + '-' + i} className="hover:bg-light-25">
                            <td
                              className={`px-3 py-2 text-light-700 max-w-0 cursor-pointer ${isCellExpanded(i, 'txn') ? 'break-words whitespace-normal' : 'truncate'}`}
                              onClick={() => toggleCell(i, 'txn')}
                              title={isCellExpanded(i, 'txn') ? undefined : p.txn_name}
                            >
                              {p.txn_name || '—'}
                            </td>
                            <td
                              className={`px-3 py-2 max-w-0 cursor-pointer ${isCellExpanded(i, 'from') ? '' : ''}`}
                              onClick={() => p.from && toggleCell(i, 'from')}
                            >
                              {p.from ? (
                                <div className={`flex items-center gap-1.5 min-w-0 ${isCellExpanded(i, 'from') ? 'flex-wrap' : ''}`}>
                                  <span className={`text-light-700 ${isCellExpanded(i, 'from') ? 'break-words whitespace-normal' : 'truncate'}`} title={isCellExpanded(i, 'from') ? undefined : p.from}>{p.from}</span>
                                  {p.from_matched ? (
                                    <span className="flex-shrink-0 px-1.5 py-0.5 bg-green-50 text-green-700 rounded text-[10px] font-medium">Match</span>
                                  ) : (
                                    <span className="flex-shrink-0 px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded text-[10px] font-medium">New</span>
                                  )}
                                </div>
                              ) : (
                                <span className="text-light-300">—</span>
                              )}
                            </td>
                            <td
                              className={`px-3 py-2 max-w-0 cursor-pointer`}
                              onClick={() => p.to && toggleCell(i, 'to')}
                            >
                              {p.to ? (
                                <div className={`flex items-center gap-1.5 min-w-0 ${isCellExpanded(i, 'to') ? 'flex-wrap' : ''}`}>
                                  <span className={`text-light-700 ${isCellExpanded(i, 'to') ? 'break-words whitespace-normal' : 'truncate'}`} title={isCellExpanded(i, 'to') ? undefined : p.to}>{p.to}</span>
                                  {p.to_matched ? (
                                    <span className="flex-shrink-0 px-1.5 py-0.5 bg-green-50 text-green-700 rounded text-[10px] font-medium">Match</span>
                                  ) : (
                                    <span className="flex-shrink-0 px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded text-[10px] font-medium">New</span>
                                  )}
                                </div>
                              ) : (
                                <span className="text-light-300">—</span>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              {p.proposed_category ? (
                                <span className="inline-flex items-center px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded text-[10px] font-medium">
                                  {p.proposed_category}
                                </span>
                              ) : (
                                <span className="text-light-300">—</span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-center">
                              {p.source === 'heuristic' ? (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded text-[10px]">
                                  <Sparkles className="w-2.5 h-2.5" /> Pattern
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-purple-50 text-purple-600 rounded text-[10px]">
                                  <Wand2 className="w-2.5 h-2.5" /> AI
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {!loading && preview && proposals.length > 0 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-light-200 bg-light-25">
            <p className="text-xs text-light-500">
              {preview.proposals_count} changes will be applied to your transactions
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                disabled={applying}
                className="px-3 py-1.5 text-xs text-light-600 border border-light-200 rounded hover:bg-light-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={onApply}
                disabled={applying}
                className="px-4 py-1.5 text-xs text-white bg-owl-blue-600 rounded hover:bg-owl-blue-700 disabled:opacity-50 flex items-center gap-1.5"
              >
                {applying ? (
                  <>
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Applying...
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-3 h-3" />
                    Apply All
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
