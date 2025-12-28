import React, { useState, useEffect } from 'react';
import { Archive, X, Trash2, Eye, Calendar, FileDown, Clock, DollarSign, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { snapshotsAPI } from '../services/api';
import { exportSnapshotToPDF } from '../utils/pdfExport';

/**
 * SnapshotList Component
 * 
 * Displays a list of saved snapshots
 */
export default function SnapshotList({ isOpen, onClose, onLoadSnapshot }) {
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSnapshot, setSelectedSnapshot] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadSnapshots();
    }
  }, [isOpen]);

  const loadSnapshots = async () => {
    setLoading(true);
    try {
      const data = await snapshotsAPI.list();
      setSnapshots(data);
    } catch (err) {
      console.error('Failed to load snapshots:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (snapshotId, e) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this snapshot?')) {
      return;
    }

    try {
      await snapshotsAPI.delete(snapshotId);
      await loadSnapshots();
      if (selectedSnapshot?.id === snapshotId) {
        setSelectedSnapshot(null);
      }
    } catch (err) {
      console.error('Failed to delete snapshot:', err);
      alert(`Failed to delete snapshot: ${err.message}`);
    }
  };

  const handleView = async (snapshot) => {
    try {
      const fullSnapshot = await snapshotsAPI.get(snapshot.id);
      setSelectedSnapshot({ ...snapshot, ...fullSnapshot });
    } catch (err) {
      console.error('Failed to load snapshot:', err);
      alert(`Failed to load snapshot: ${err.message}`);
    }
  };

  const handleLoad = () => {
    if (onLoadSnapshot && selectedSnapshot) {
      onLoadSnapshot(selectedSnapshot);
    }
  };

  const handleExportPDF = async () => {
    if (!selectedSnapshot) {
      alert('Please select a snapshot to export');
      return;
    }

    try {
      // Get full snapshot data if not already loaded
      let fullSnapshot = selectedSnapshot;
      if (!fullSnapshot.subgraph) {
        fullSnapshot = await snapshotsAPI.get(selectedSnapshot.id);
      }

      // Ensure timeline is included
      if (!fullSnapshot.timeline) {
        fullSnapshot.timeline = [];
      }

      // Export to PDF (no canvas available for saved snapshots, but we'll include the data)
      await exportSnapshotToPDF(fullSnapshot, null);
      alert('PDF exported successfully!');
    } catch (err) {
      console.error('Failed to export PDF:', err);
      alert(`Failed to export PDF: ${err.message}`);
    }
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const formatEventDate = (dateStr) => {
    if (!dateStr) return 'Unknown date';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  };

  const formatEventTime = (timeStr) => {
    if (!timeStr) return null;
    return timeStr;
  };

  // Group timeline events by date
  const groupTimelineEvents = (events) => {
    if (!events || !Array.isArray(events)) return [];
    const groups = {};
    events.forEach(event => {
      const date = event.date || 'unknown';
      if (!groups[date]) {
        groups[date] = [];
      }
      groups[date].push(event);
    });
    const sortedDates = Object.keys(groups).sort((a, b) => {
      if (a === 'unknown') return 1;
      if (b === 'unknown') return -1;
      return a.localeCompare(b);
    });
    return sortedDates.map(date => ({
      date,
      events: groups[date],
    }));
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg w-full max-w-4xl h-[80vh] flex flex-col border border-light-200 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <div className="flex items-center gap-2">
            <Archive className="w-5 h-5 text-owl-purple-500" />
            <h2 className="text-lg font-semibold text-owl-blue-900">Saved Snapshots</h2>
            <span className="text-xs text-light-600 bg-light-100 px-2 py-1 rounded">
              {snapshots.length} snapshot{snapshots.length !== 1 ? 's' : ''}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Snapshots List */}
          <div className="w-1/2 border-r border-light-200 overflow-y-auto">
            {loading ? (
              <div className="p-8 text-center text-light-600">Loading snapshots...</div>
            ) : snapshots.length === 0 ? (
              <div className="p-8 text-center text-light-600">
                <Archive className="w-12 h-12 mx-auto mb-3 text-light-400" />
                <p>No snapshots saved yet</p>
              </div>
            ) : (
              <div className="p-2">
                {snapshots.map((snapshot) => (
                  <div
                    key={snapshot.id}
                    onClick={() => handleView(snapshot)}
                    className={`p-3 mb-2 rounded-lg cursor-pointer transition-colors ${
                      selectedSnapshot?.id === snapshot.id
                        ? 'bg-owl-orange-100 border border-owl-orange-300'
                        : 'bg-light-50 hover:bg-light-100 border border-light-200'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-owl-blue-900 truncate">{snapshot.name}</h3>
                        {snapshot.ai_overview && (
                          <div className="mt-1 mb-1 p-1.5 bg-owl-blue-50 rounded border border-owl-blue-200">
                            <p className="text-xs font-medium text-owl-blue-900 mb-0.5">AI Overview:</p>
                            <div className="text-xs text-owl-blue-800 line-clamp-2 prose prose-sm max-w-none">
                              <ReactMarkdown>{snapshot.ai_overview}</ReactMarkdown>
                            </div>
                          </div>
                        )}
                        <p className="text-xs text-light-600 mt-1 line-clamp-2">{snapshot.notes || 'No notes'}</p>
                        <div className="flex items-center gap-3 mt-2 text-xs text-light-600">
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {formatDate(snapshot.created_at)}
                          </span>
                          <span>{snapshot.node_count} nodes</span>
                          <span>{snapshot.link_count} links</span>
                          {snapshot.timeline_count !== undefined && (
                            <span>{snapshot.timeline_count} events</span>
                          )}
                        </div>
                        {snapshot.case_name && (
                          <div className="mt-1 text-xs text-owl-blue-600">
                            Case: {snapshot.case_name}
                            {snapshot.case_version && ` (v${snapshot.case_version})`}
                          </div>
                        )}
                      </div>
                      <button
                        onClick={(e) => handleDelete(snapshot.id, e)}
                        className="p-1 hover:bg-light-200 rounded transition-colors ml-2"
                        title="Delete snapshot"
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Snapshot Details */}
          <div className="w-1/2 p-4 overflow-y-auto">
            {selectedSnapshot ? (
              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold text-owl-blue-900 mb-2">{selectedSnapshot.name}</h3>
                  {/* AI Overview - At the top */}
                  {selectedSnapshot.ai_overview && (
                    <div className="mb-3 p-3 bg-owl-blue-50 rounded-lg border border-owl-blue-200">
                      <p className="text-sm font-medium text-owl-blue-900 mb-1">AI Overview:</p>
                      <div className="text-sm text-owl-blue-800 prose prose-sm max-w-none">
                        <ReactMarkdown>{selectedSnapshot.ai_overview}</ReactMarkdown>
                      </div>
                    </div>
                  )}
                  <p className="text-sm text-light-700 whitespace-pre-wrap">{selectedSnapshot.notes || 'No notes'}</p>
                </div>

                <div className="text-xs text-light-600">
                  <p>Created: {formatDate(selectedSnapshot.created_at)}</p>
                  <p>Nodes: {selectedSnapshot.node_count || selectedSnapshot.subgraph?.nodes?.length || 0}</p>
                  <p>Links: {selectedSnapshot.link_count || selectedSnapshot.subgraph?.links?.length || 0}</p>
                  {selectedSnapshot.timeline && Array.isArray(selectedSnapshot.timeline) && selectedSnapshot.timeline.length > 0 && (
                    <p>Timeline Events: {selectedSnapshot.timeline.length}</p>
                  )}
                  {selectedSnapshot.case_name && (
                    <div className="mt-2 pt-2 border-t border-light-200">
                      <p className="font-medium text-owl-blue-700">Associated Case:</p>
                      <p>{selectedSnapshot.case_name}</p>
                      {selectedSnapshot.case_version && (
                        <p className="text-light-500">Version {selectedSnapshot.case_version}</p>
                      )}
                    </div>
                  )}
                </div>

                {selectedSnapshot.timeline && Array.isArray(selectedSnapshot.timeline) && selectedSnapshot.timeline.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-owl-blue-900 mb-2">Timeline Events</h4>
                    <div className="space-y-3 max-h-64 overflow-y-auto">
                      {groupTimelineEvents(selectedSnapshot.timeline).map((dateGroup, groupIdx) => (
                        <div key={groupIdx} className="bg-light-50 rounded p-2 border border-light-200">
                          <div className="flex items-center gap-2 mb-2">
                            <Calendar className="w-3 h-3 text-owl-orange-500" />
                            <span className="text-xs font-medium text-owl-blue-900">
                              {formatEventDate(dateGroup.date)}
                            </span>
                            <span className="text-xs text-light-600">
                              ({dateGroup.events.length} event{dateGroup.events.length !== 1 ? 's' : ''})
                            </span>
                          </div>
                          <div className="space-y-2 ml-5">
                            {dateGroup.events.map((event, eventIdx) => (
                              <div key={eventIdx} className="bg-white rounded p-2 text-xs border border-light-200">
                                <div className="flex items-start justify-between gap-2 mb-1">
                                  <span className="font-medium text-owl-blue-900">{event.name || event.key}</span>
                                  {event.type && (
                                    <span className="text-xs px-2 py-0.5 rounded bg-owl-purple-100 text-owl-purple-700 flex-shrink-0">
                                      {event.type}
                                    </span>
                                  )}
                                </div>
                                <div className="flex items-center gap-3 mt-1 text-light-600">
                                  {event.time && (
                                    <span className="flex items-center gap-1">
                                      <Clock className="w-3 h-3" />
                                      {formatEventTime(event.time)}
                                    </span>
                                  )}
                                  {event.amount && (
                                    <span className="flex items-center gap-1">
                                      <DollarSign className="w-3 h-3" />
                                      {event.amount}
                                    </span>
                                  )}
                                </div>
                                {event.summary && (
                                  <p className="text-light-700 mt-1 line-clamp-2">{event.summary}</p>
                                )}
                                {event.connections && event.connections.length > 0 && (
                                  <div className="flex flex-wrap gap-1 mt-2">
                                    {event.connections.slice(0, 3).map((conn, connIdx) => (
                                      <span
                                        key={connIdx}
                                        className="text-xs bg-light-100 text-light-700 px-2 py-0.5 rounded"
                                      >
                                        {conn.name || conn.key}
                                      </span>
                                    ))}
                                    {event.connections.length > 3 && (
                                      <span className="text-xs text-light-600">
                                        +{event.connections.length - 3} more
                                      </span>
                                    )}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {selectedSnapshot.citations && Object.keys(selectedSnapshot.citations).length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-owl-blue-900 mb-2">Source Citations</h4>
                    <div className="space-y-3 max-h-64 overflow-y-auto">
                      {Object.values(selectedSnapshot.citations).map((nodeCitation, idx) => (
                        <div key={idx} className="bg-light-50 rounded p-2 text-xs border border-light-200">
                          <div className="font-medium text-owl-blue-900 mb-1">
                            {nodeCitation.node_name} ({nodeCitation.node_type})
                          </div>
                          <div className="space-y-1">
                            {nodeCitation.citations.map((citation, cIdx) => (
                              <div key={cIdx} className="text-light-700 pl-2 border-l-2 border-owl-blue-300">
                                <div className="flex items-center gap-2">
                                  <FileText className="w-3 h-3 text-owl-blue-600" />
                                  <span className="font-medium">
                                    {citation.source_doc}
                                    {citation.page && `, page ${citation.page}`}
                                  </span>
                                  <span className="text-light-500">
                                    ({citation.type === 'verified_fact' ? 'Verified Fact' : citation.type === 'ai_insight' ? 'AI Insight' : 'Property'})
                                  </span>
                                </div>
                                {citation.fact_text && (
                                  <p className="text-light-600 mt-1 italic line-clamp-2">{citation.fact_text}</p>
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
                  </div>
                )}

                {selectedSnapshot.chat_history && selectedSnapshot.chat_history.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-owl-blue-900 mb-2">Chat History</h4>
                    <div className="space-y-2">
                      {selectedSnapshot.chat_history.map((msg, idx) => (
                        <div key={idx} className="bg-light-50 rounded p-2 text-xs border border-light-200">
                          <span className="font-medium text-owl-purple-600">{msg.role === 'user' ? 'User' : 'AI'}:</span>
                          <p className="text-light-700 mt-1">{msg.content}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={handleLoad}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-owl-orange-500 hover:bg-owl-orange-600 text-white rounded-lg transition-colors"
                  >
                    <Eye className="w-4 h-4" />
                    Load Snapshot
                  </button>
                  <button
                    onClick={handleExportPDF}
                    className="flex items-center justify-center gap-2 px-4 py-2 bg-light-100 hover:bg-light-200 text-light-700 rounded-lg transition-colors"
                    title="Export to PDF"
                  >
                    <FileDown className="w-4 h-4" />
                    Export PDF
                  </button>
                </div>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-light-600">
                <div className="text-center">
                  <Eye className="w-12 h-12 mx-auto mb-3 text-light-400" />
                  <p>Select a snapshot to view details</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

