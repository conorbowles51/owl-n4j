import React, { useState, useEffect, useCallback } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Archive,
  Trash2,
  Calendar,
  Focus,
  FileText,
  Link2,
  X,
  Loader2,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { casesAPI, snapshotsAPI, workspaceAPI } from '../../services/api';

function mergeSnapshot(caseSnap, apiSnap) {
  if (!apiSnap) return caseSnap;
  const hasContent = (v, pred) => v != null && pred(v);
  return {
    ...caseSnap,
    subgraph: hasContent(apiSnap.subgraph, (s) => (s?.nodes?.length || s?.links?.length)) ? apiSnap.subgraph : caseSnap.subgraph,
    overview: hasContent(apiSnap.overview, (o) => (o?.nodes?.length || (typeof o === 'object' && Object.keys(o || {}).length))) ? apiSnap.overview : caseSnap.overview,
    timeline: hasContent(apiSnap.timeline, (t) => Array.isArray(t) && t.length) ? apiSnap.timeline : caseSnap.timeline,
    citations: hasContent(apiSnap.citations, (c) => typeof c === 'object' && Object.keys(c || {}).length) ? apiSnap.citations : caseSnap.citations,
    chat_history: hasContent(apiSnap.chat_history, (h) => Array.isArray(h) && h.length) ? apiSnap.chat_history : caseSnap.chat_history,
    ai_overview: apiSnap.ai_overview && String(apiSnap.ai_overview).trim() ? apiSnap.ai_overview : caseSnap.ai_overview,
  };
}

/**
 * Snapshots Section
 *
 * Displays the actual snapshot list from the case (latest version).
 * Expandable/collapsible cards; when expanded, shows full snapshot like Case Overview.
 * Option to attach a snapshot to an investigation theory.
 */
export default function SnapshotsSection({
  caseId,
  isCollapsed,
  onToggle,
  onFocus,
  fullHeight = false, // When true, use full height for content panel
}) {
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [versionLabel, setVersionLabel] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [loadedFromApi, setLoadedFromApi] = useState({});
  const [loadingApi, setLoadingApi] = useState(new Set());
  const [attachModal, setAttachModal] = useState({ open: false, snapshotId: null, snapshotName: '' });
  const [theories, setTheories] = useState([]);
  const [theoriesLoading, setTheoriesLoading] = useState(false);
  const [attachLoading, setAttachLoading] = useState(false);

  const loadSnapshots = useCallback(async () => {
    if (!caseId) {
      setSnapshots([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const caseData = await casesAPI.get(caseId);
      const versions = caseData?.versions || [];
      const sorted = [...versions].sort((a, b) => (b.version ?? 0) - (a.version ?? 0));
      const latest = sorted[0];

      if (!latest) {
        setSnapshots([]);
        setVersionLabel(null);
        setLoading(false);
        return;
      }

      setVersionLabel(`V${latest.version}`);

      const raw = latest.snapshots || [];
      const withCounts = raw.map((s) => {
        const sub = s.subgraph || {};
        const nodes = sub.nodes || [];
        const links = sub.links || [];
        const timeline = s.timeline || [];
        return {
          ...s,
          node_count: s.node_count ?? nodes.length,
          link_count: s.link_count ?? links.length,
          timeline_count: s.timeline_count ?? timeline.length,
        };
      });

      const sortedSnapshots = withCounts.sort((a, b) => {
        const tA = new Date(a.timestamp || a.created_at || 0).getTime();
        const tB = new Date(b.timestamp || b.created_at || 0).getTime();
        return tB - tA;
      });

      setSnapshots(sortedSnapshots);
    } catch (err) {
      console.error('Failed to load case snapshots:', err);
      setError(err?.message || 'Failed to load snapshots');
      setSnapshots([]);
      setVersionLabel(null);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    loadSnapshots();
  }, [loadSnapshots]);

  const formatDate = (dateString) => {
    if (!dateString) return 'No date';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return String(dateString);
    }
  };

  const fetchAndMergeApi = useCallback(async (snapshot) => {
    const id = snapshot.id;
    if (loadingApi.has(id)) return;
    setLoadingApi((prev) => new Set(prev).add(id));
    try {
      const api = await snapshotsAPI.get(id);
      setLoadedFromApi((prev) => ({ ...prev, [id]: api }));
    } catch (e) {
      // If snapshot doesn't exist in storage (404), that's fine - we'll use case data
      // Only log non-404 errors
      if (e?.status !== 404 && !e?.message?.includes('not found') && !e?.message?.includes('doesn\'t exist')) {
        console.warn('Snapshot API fetch failed:', e);
      }
      // Mark as "loaded" (with null) so we don't keep trying
      setLoadedFromApi((prev) => ({ ...prev, [id]: null }));
    } finally {
      setLoadingApi((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }, [loadingApi]);

  const toggleExpand = useCallback(
    (snapshot) => {
      const id = snapshot.id;
      setExpandedId((prev) => {
        if (prev === id) return null;
        // Only fetch if we haven't tried yet (undefined), not if we got 404 (null)
        if (loadedFromApi[id] === undefined) fetchAndMergeApi(snapshot);
        return id;
      });
    },
    [fetchAndMergeApi, loadedFromApi]
  );

  const handleDelete = async (snapshotId, e) => {
    e?.stopPropagation?.();
    if (!confirm('Are you sure you want to delete this snapshot?')) return;

    try {
      await snapshotsAPI.delete(snapshotId);
      setExpandedId((prev) => (prev === snapshotId ? null : prev));
      setLoadedFromApi((prev) => {
        const next = { ...prev };
        delete next[snapshotId];
        return next;
      });
      await loadSnapshots();
    } catch (err) {
      // If snapshot doesn't exist in storage (404), remove it from case version instead
      if (err?.message?.includes('not found') || err?.message?.includes('doesn\'t exist') || err?.status === 404) {
        try {
          console.log(`Snapshot ${snapshotId} not found in storage, removing from case version...`);
          const caseData = await casesAPI.get(caseId);
          const versions = caseData?.versions || [];
          const sorted = [...versions].sort((a, b) => (b.version ?? 0) - (a.version ?? 0));
          const latest = sorted[0];

          if (latest && latest.snapshots) {
            const updatedSnapshots = latest.snapshots.filter((s) => s.id !== snapshotId);
            await casesAPI.save({
              case_id: caseId,
              case_name: caseData.name,
              snapshots: updatedSnapshots,
              save_notes: `Removed snapshot ${snapshotId}`,
            });
            setExpandedId((prev) => (prev === snapshotId ? null : prev));
            setLoadedFromApi((prev) => {
              const next = { ...prev };
              delete next[snapshotId];
              return next;
            });
            await loadSnapshots();
          } else {
            throw new Error('Could not find case version to update');
          }
        } catch (caseErr) {
          console.error('Failed to remove snapshot from case:', caseErr);
          alert('Snapshot not found in storage. Failed to remove from case version.');
        }
      } else {
        console.error('Failed to delete snapshot:', err);
        alert('Failed to delete snapshot');
      }
    }
  };

  const openAttachModal = (snapshot, e) => {
    e?.stopPropagation?.();
    setAttachModal({ open: true, snapshotId: snapshot.id, snapshotName: snapshot.name || 'Unnamed' });
    setTheories([]);
    setTheoriesLoading(true);
    workspaceAPI
      .getTheories(caseId)
      .then((r) => setTheories(r.theories || []))
      .catch(() => setTheories([]))
      .finally(() => setTheoriesLoading(false));
  };

  const closeAttachModal = () => {
    setAttachModal({ open: false, snapshotId: null, snapshotName: '' });
    setAttachLoading(false);
    setTheoriesLoading(false);
  };

  const attachToTheory = async (theory) => {
    if (!attachModal.snapshotId || !caseId) return;
    setAttachLoading(true);
    try {
      const existing = theory.attached_snapshot_ids || [];
      const ids = existing.includes(attachModal.snapshotId)
        ? existing
        : [...existing, attachModal.snapshotId];
      await workspaceAPI.updateTheory(caseId, theory.theory_id, {
        ...theory,
        attached_snapshot_ids: ids,
      });
      closeAttachModal();
    } catch (err) {
      console.error('Failed to attach snapshot to theory:', err);
      alert('Failed to attach snapshot to theory');
    } finally {
      setAttachLoading(false);
    }
  };

  return (
    <div className="border-b border-light-200">
      <div
        className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
        onClick={(e) => onToggle?.(e)}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900 flex items-center gap-2">
          <Archive className="w-4 h-4 text-owl-blue-600" />
          Snapshots
          {versionLabel && (
            <span className="text-xs font-normal text-light-600">{versionLabel}</span>
          )}
          <span className="text-xs font-normal text-light-600">
            ({loading ? '…' : snapshots.length})
          </span>
        </h3>
        <div className="flex items-center gap-2">
          {onFocus && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onFocus(e);
              }}
              className="p-1 hover:bg-light-100 rounded"
              title="Focus on this section"
            >
              <Focus className="w-4 h-4 text-owl-blue-600" />
            </button>
          )}
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4 text-light-600" />
          ) : (
            <ChevronDown className="w-4 h-4 text-light-600" />
          )}
        </div>
      </div>

      {!isCollapsed && (
        <div className={`px-4 pb-4 ${fullHeight ? 'flex flex-col h-full' : ''}`}>
          {loading ? (
            <p className="text-xs text-light-500">Loading snapshots…</p>
          ) : error ? (
            <p className="text-xs text-red-600">{error}</p>
          ) : snapshots.length === 0 ? (
            <p className="text-xs text-light-500 italic">No snapshots saved for this case</p>
          ) : (
            <div className={`space-y-2 overflow-y-auto ${fullHeight ? 'flex-1 min-h-0' : 'max-h-[32rem]'}`}>
              {snapshots.map((snapshot) => {
                const isExpanded = expandedId === snapshot.id;

                return (
                  <div
                    key={snapshot.id}
                    className="rounded-lg border border-light-200 bg-light-50 hover:bg-light-100 transition-colors"
                  >
                    {/* Header row: click to expand/collapse */}
                    <div
                      className="p-3 cursor-pointer flex items-start justify-between gap-2"
                      onClick={() => toggleExpand(snapshot)}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="text-sm font-medium text-owl-blue-900 truncate">
                            {snapshot.name || 'Unnamed snapshot'}
                          </h4>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(snapshot);
                            }}
                            className="text-xs text-owl-blue-600 hover:text-owl-blue-700"
                          >
                            {isExpanded ? 'Collapse' : 'Expand'}
                          </button>
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-xs text-light-600">
                          <Calendar className="w-3 h-3 flex-shrink-0" />
                          <span>{formatDate(snapshot.timestamp || snapshot.created_at)}</span>
                          <span>•</span>
                          <span>{snapshot.node_count ?? 0} nodes</span>
                          <span>•</span>
                          <span>{snapshot.link_count ?? 0} links</span>
                          {snapshot.timeline_count > 0 && (
                            <>
                              <span>•</span>
                              <span>{snapshot.timeline_count} timeline</span>
                            </>
                          )}
                        </div>
                        {!isExpanded && snapshot.notes && (
                          <p className="text-xs text-light-600 mt-1 line-clamp-2">{snapshot.notes}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={(e) => openAttachModal(snapshot, e)}
                          className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors"
                          title="Attach to theory"
                        >
                          <Link2 className="w-3.5 h-3.5 text-owl-blue-600" />
                        </button>
                        <button
                          onClick={(e) => handleDelete(snapshot.id, e)}
                          className="p-1.5 hover:bg-red-100 rounded transition-colors"
                          title="Delete snapshot"
                        >
                          <Trash2 className="w-3.5 h-3.5 text-red-600" />
                        </button>
                      </div>
                    </div>

                    {/* Collapsed summary: AI overview from case snapshot if present */}
                    {!isExpanded && snapshot.ai_overview && (
                      <div className="px-3 pb-3 pt-0" onClick={() => toggleExpand(snapshot)}>
                        <div className="p-2 bg-owl-blue-50 rounded border border-owl-blue-200">
                          <p className="text-xs font-medium text-owl-blue-900 mb-1">AI Overview:</p>
                          <div className="text-xs text-owl-blue-800 line-clamp-3 prose prose-sm max-w-none">
                            <ReactMarkdown>{snapshot.ai_overview}</ReactMarkdown>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Expanded: full snapshot detail (case + API merge) */}
                    {isExpanded && (
                      <div className="px-3 pb-4 pt-0 border-t border-light-200 mt-0">
                        {loadingApi.has(snapshot.id) && loadedFromApi[snapshot.id] === undefined ? (
                          <div className="flex items-center gap-2 py-4 text-sm text-light-600">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            Loading snapshot details…
                          </div>
                        ) : (
                          <SnapshotDetailContent
                            full={mergeSnapshot(snapshot, loadedFromApi[snapshot.id] || null)}
                            snapshot={snapshot}
                            formatDate={formatDate}
                          />
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Attach to theory modal */}
      {attachModal.open && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={closeAttachModal}
        >
          <div
            className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 max-h-[80vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-light-200">
              <h3 className="text-lg font-semibold text-owl-blue-900">
                Attach snapshot to theory
              </h3>
              <button
                onClick={closeAttachModal}
                className="p-1 hover:bg-light-100 rounded"
              >
                <X className="w-5 h-5 text-light-600" />
              </button>
            </div>
            <p className="px-4 pt-2 text-sm text-light-600">
              Attach &quot;{attachModal.snapshotName}&quot; to a theory:
            </p>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {theoriesLoading ? (
                <p className="text-sm text-light-500">Loading theories…</p>
              ) : theories.length === 0 ? (
                <p className="text-sm text-light-500 italic">No theories found. Create one in the Theories section.</p>
              ) : (
                theories.map((t) => (
                  <button
                    key={t.theory_id}
                    onClick={() => attachToTheory(t)}
                    disabled={attachLoading}
                    className="w-full text-left p-3 rounded-lg border border-light-200 hover:bg-owl-blue-50 hover:border-owl-blue-200 transition-colors disabled:opacity-50"
                  >
                    <span className="font-medium text-owl-blue-900">{t.title}</span>
                    {t.type && (
                      <span className="ml-2 text-xs text-light-600">{t.type}</span>
                    )}
                  </button>
                ))
              )}
            </div>
            <div className="p-4 border-t border-light-200">
              <button
                onClick={closeAttachModal}
                className="w-full px-4 py-2 bg-light-200 text-light-700 rounded-lg hover:bg-light-300"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Full snapshot detail (mirrors Case Overview expanded view).
 * Renders metadata, AI overview, notes, node overview, citations, timeline, chat history, subgraph stats.
 * All sections always visible; no truncation; full chat content.
 */
function SnapshotDetailContent({ full, snapshot, formatDate }) {
  const overviewNodes = full.overview?.nodes ?? (Array.isArray(full.overview) ? full.overview : null);
  const subgraphNodes = full.subgraph?.nodes;
  const nodes = overviewNodes && overviewNodes.length ? overviewNodes : (subgraphNodes && subgraphNodes.length ? subgraphNodes : []);
  const timeline = Array.isArray(full.timeline) ? full.timeline : [];
  const citations = full.citations && typeof full.citations === 'object' ? full.citations : {};
  const citationValues = Object.values(citations);
  const chatHistory = Array.isArray(full.chat_history) ? full.chat_history : [];

  return (
    <div className="mt-4 space-y-4">
      <div className="p-3 bg-light-50 rounded-lg border border-light-200">
        <h5 className="text-sm font-semibold text-owl-blue-900 mb-2">Snapshot information</h5>
        <div className="space-y-1 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-light-600 w-20">Name:</span>
            <span className="font-medium text-owl-blue-900">{full.name || snapshot.name}</span>
          </div>
          {(full.timestamp || full.created_at || snapshot.timestamp) && (
            <div className="flex items-center gap-2">
              <span className="text-light-600 w-20">Created:</span>
              <span className="text-light-700">
                {formatDate(full.timestamp || full.created_at || snapshot.timestamp)}
              </span>
            </div>
          )}
          {full.case_name && (
            <div className="flex items-center gap-2">
              <span className="text-light-600 w-20">Case:</span>
              <span className="text-light-700">{full.case_name}</span>
            </div>
          )}
          {full.case_version != null && (
            <div className="flex items-center gap-2">
              <span className="text-light-600 w-20">Version:</span>
              <span className="text-light-700">{full.case_version}</span>
            </div>
          )}
        </div>
      </div>

      {full.ai_overview ? (
        <div className="p-3 bg-owl-blue-50 rounded-lg border border-owl-blue-200">
          <p className="text-sm font-medium text-owl-blue-900 mb-1">AI Overview</p>
          <div className="text-sm text-owl-blue-800 prose prose-sm max-w-none">
            <ReactMarkdown>{full.ai_overview}</ReactMarkdown>
          </div>
        </div>
      ) : (
        <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
          <p className="text-xs text-yellow-800 italic">No AI overview available for this snapshot.</p>
        </div>
      )}

      {full.notes && (
        <div className="p-3 bg-light-50 rounded-lg border border-light-200">
          <p className="text-sm font-medium text-owl-blue-900 mb-1">Notes</p>
          <p className="text-sm text-light-700 whitespace-pre-wrap">{full.notes}</p>
        </div>
      )}

      <div>
        <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
          <FileText className="w-4 h-4" />
          Node overview {nodes.length > 0 && `(${nodes.length} nodes)`}
        </h5>
        {nodes.length === 0 ? (
          <p className="text-xs text-light-500 italic p-2 bg-light-50 rounded border border-light-200">
            No node data available for this snapshot.
          </p>
        ) : (
          <div className="space-y-3">
            {nodes.map((node, i) => (
              <div key={i} className="bg-light-50 rounded p-3 border border-light-200">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <h6 className="font-medium text-owl-blue-900 text-sm">
                    {node.name || node.key}
                  </h6>
                  {node.type && (
                    <span className="text-xs px-2 py-0.5 rounded bg-owl-purple-100 text-owl-purple-700 flex-shrink-0">
                      {node.type}
                    </span>
                  )}
                </div>
                {node.summary && (
                  <p className="text-xs text-light-700 mt-1">{node.summary}</p>
                )}
                {node.notes && (
                  <p className="text-xs text-light-600 mt-1 italic">{node.notes}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
          <FileText className="w-4 h-4" />
          Source citations
          {citationValues.length > 0 && ` (${citationValues.length} nodes)`}
        </h5>
        {citationValues.length === 0 ? (
          <p className="text-xs text-light-500 italic p-2 bg-light-50 rounded border border-light-200">
            No citations available for this snapshot.
          </p>
        ) : (
          <div className="space-y-3">
            {citationValues.map((nodeCitation, idx) => (
              <div key={idx} className="bg-light-50 rounded p-3 border border-light-200">
                <div className="font-medium text-owl-blue-900 text-sm mb-2">
                  {nodeCitation.node_name} ({nodeCitation.node_type})
                </div>
                <div className="space-y-2">
                  {(nodeCitation.citations || []).map((citation, cIdx) => (
                    <div
                      key={cIdx}
                      className="text-xs text-light-700 pl-2 border-l-2 border-owl-blue-300"
                    >
                      <div className="flex items-center gap-2 flex-wrap">
                        <FileText className="w-3 h-3 text-owl-blue-600" />
                        <span className="font-medium">
                          {citation.source_doc}
                          {citation.page != null && `, page ${citation.page}`}
                        </span>
                        <span className="text-light-500">
                          ({citation.type === 'verified_fact' ? 'Verified fact' : citation.type === 'ai_insight' ? 'AI insight' : 'Property'})
                        </span>
                      </div>
                      {citation.fact_text && (
                        <p className="text-light-600 mt-1 italic">{citation.fact_text}</p>
                      )}
                      {citation.verified_by && (
                        <p className="text-light-500 text-xs mt-0.5">Verified by: {citation.verified_by}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
          <Calendar className="w-4 h-4" />
          Timeline events
          {timeline.length > 0 && ` (${timeline.length} events)`}
        </h5>
        {timeline.length === 0 ? (
          <p className="text-xs text-light-500 italic p-2 bg-light-50 rounded border border-light-200">
            No timeline events available for this snapshot.
          </p>
        ) : (
          <div className="space-y-3">
            {timeline.map((event, i) => (
              <div key={i} className="bg-light-50 rounded p-3 border border-light-200">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <span className="font-medium text-owl-blue-900 text-sm">
                    {event.name || event.key}
                  </span>
                  {event.type && (
                    <span className="text-xs px-2 py-0.5 rounded bg-owl-purple-100 text-owl-purple-700 flex-shrink-0">
                      {event.type}
                    </span>
                  )}
                </div>
                {event.date && (
                  <p className="text-xs text-light-600 mt-1">
                    {formatDate(event.date)}
                    {event.time && ` at ${event.time}`}
                  </p>
                )}
                {event.summary && (
                  <p className="text-xs text-light-700 mt-1">{event.summary}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
          <FileText className="w-4 h-4" />
          Chat history
          {chatHistory.length > 0 && ` (${chatHistory.length} messages)`}
        </h5>
        {chatHistory.length === 0 ? (
          <p className="text-xs text-light-500 italic p-2 bg-light-50 rounded border border-light-200">
            No chat messages for this snapshot.
          </p>
        ) : (
          <div className="space-y-3">
            {chatHistory.map((msg, i) => (
              <div key={i} className="bg-light-50 rounded p-3 border border-light-200">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-owl-purple-600">
                    {msg.role === 'user' ? 'User' : 'Assistant'}
                  </span>
                  {msg.timestamp && (
                    <span className="text-xs text-light-500">{formatDate(msg.timestamp)}</span>
                  )}
                </div>
                <div className="text-sm text-light-700 prose prose-sm max-w-none">
                  {msg.role === 'user' ? (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <ReactMarkdown>{msg.content || ''}</ReactMarkdown>
                  )}
                </div>
                {msg.cypherUsed && (
                  <p className="text-xs text-light-500 mt-1 italic">Cypher query used</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
          <FileText className="w-4 h-4" />
          Subgraph statistics
        </h5>
        <div className="bg-light-50 rounded p-3 border border-light-200 text-xs">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className="text-light-600">Nodes:</span>
              <span className="ml-2 font-medium text-owl-blue-900">
                {full.subgraph?.nodes?.length ?? full.node_count ?? snapshot.node_count ?? 0}
              </span>
            </div>
            <div>
              <span className="text-light-600">Links:</span>
              <span className="ml-2 font-medium text-owl-blue-900">
                {full.subgraph?.links?.length ?? full.link_count ?? snapshot.link_count ?? 0}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
