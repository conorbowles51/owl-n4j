import React, { useState, useEffect } from 'react';
import { Archive, X, Trash2, Eye, Calendar, FileDown, Clock, DollarSign } from 'lucide-react';
import { artifactsAPI } from '../services/api';
import { exportArtifactToPDF } from '../utils/pdfExport';

/**
 * ArtifactList Component
 * 
 * Displays a list of saved artifacts
 */
export default function ArtifactList({ isOpen, onClose, onLoadArtifact }) {
  const [artifacts, setArtifacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedArtifact, setSelectedArtifact] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadArtifacts();
    }
  }, [isOpen]);

  const loadArtifacts = async () => {
    setLoading(true);
    try {
      const data = await artifactsAPI.list();
      setArtifacts(data);
    } catch (err) {
      console.error('Failed to load artifacts:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (artifactId, e) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this artifact?')) {
      return;
    }

    try {
      await artifactsAPI.delete(artifactId);
      await loadArtifacts();
      if (selectedArtifact?.id === artifactId) {
        setSelectedArtifact(null);
      }
    } catch (err) {
      console.error('Failed to delete artifact:', err);
      alert(`Failed to delete artifact: ${err.message}`);
    }
  };

  const handleView = async (artifact) => {
    try {
      const fullArtifact = await artifactsAPI.get(artifact.id);
      setSelectedArtifact({ ...artifact, ...fullArtifact });
    } catch (err) {
      console.error('Failed to load artifact:', err);
      alert(`Failed to load artifact: ${err.message}`);
    }
  };

  const handleLoad = () => {
    if (onLoadArtifact && selectedArtifact) {
      onLoadArtifact(selectedArtifact);
    }
  };

  const handleExportPDF = async () => {
    if (!selectedArtifact) {
      alert('Please select an artifact to export');
      return;
    }

    try {
      // Get full artifact data if not already loaded
      let fullArtifact = selectedArtifact;
      if (!fullArtifact.subgraph) {
        fullArtifact = await artifactsAPI.get(selectedArtifact.id);
      }

      // Ensure timeline is included
      if (!fullArtifact.timeline) {
        fullArtifact.timeline = [];
      }

      // Export to PDF (no canvas available for saved artifacts, but we'll include the data)
      await exportArtifactToPDF(fullArtifact, null);
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
      <div className="bg-dark-800 rounded-lg w-full max-w-4xl h-[80vh] flex flex-col border border-dark-700">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-dark-700">
          <div className="flex items-center gap-2">
            <Archive className="w-5 h-5 text-cyan-400" />
            <h2 className="text-lg font-semibold text-dark-100">Saved Artifacts</h2>
            <span className="text-xs text-dark-400 bg-dark-700 px-2 py-1 rounded">
              {artifacts.length} artifact{artifacts.length !== 1 ? 's' : ''}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-dark-700 rounded transition-colors"
          >
            <X className="w-5 h-5 text-dark-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Artifacts List */}
          <div className="w-1/2 border-r border-dark-700 overflow-y-auto">
            {loading ? (
              <div className="p-8 text-center text-dark-400">Loading artifacts...</div>
            ) : artifacts.length === 0 ? (
              <div className="p-8 text-center text-dark-400">
                <Archive className="w-12 h-12 mx-auto mb-3 text-dark-600" />
                <p>No artifacts saved yet</p>
              </div>
            ) : (
              <div className="p-2">
                {artifacts.map((artifact) => (
                  <div
                    key={artifact.id}
                    onClick={() => handleView(artifact)}
                    className={`p-3 mb-2 rounded-lg cursor-pointer transition-colors ${
                      selectedArtifact?.id === artifact.id
                        ? 'bg-cyan-600/20 border border-cyan-500/50'
                        : 'bg-dark-900/50 hover:bg-dark-900 border border-dark-700'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-dark-100 truncate">{artifact.name}</h3>
                        <p className="text-xs text-dark-400 mt-1 line-clamp-2">{artifact.notes || 'No notes'}</p>
                        <div className="flex items-center gap-3 mt-2 text-xs text-dark-500">
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {formatDate(artifact.created_at)}
                          </span>
                          <span>{artifact.node_count} nodes</span>
                          <span>{artifact.link_count} links</span>
                          {artifact.timeline_count !== undefined && (
                            <span>{artifact.timeline_count} events</span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleDelete(artifact.id, e)}
                        className="p-1 hover:bg-dark-700 rounded transition-colors ml-2"
                        title="Delete artifact"
                      >
                        <Trash2 className="w-4 h-4 text-red-400" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Artifact Details */}
          <div className="w-1/2 p-4 overflow-y-auto">
            {selectedArtifact ? (
              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold text-dark-100 mb-2">{selectedArtifact.name}</h3>
                  <p className="text-sm text-dark-300 whitespace-pre-wrap">{selectedArtifact.notes || 'No notes'}</p>
                </div>

                <div className="text-xs text-dark-400">
                  <p>Created: {formatDate(selectedArtifact.created_at)}</p>
                  <p>Nodes: {selectedArtifact.node_count || selectedArtifact.subgraph?.nodes?.length || 0}</p>
                  <p>Links: {selectedArtifact.link_count || selectedArtifact.subgraph?.links?.length || 0}</p>
                  {selectedArtifact.timeline && Array.isArray(selectedArtifact.timeline) && selectedArtifact.timeline.length > 0 && (
                    <p>Timeline Events: {selectedArtifact.timeline.length}</p>
                  )}
                </div>

                {selectedArtifact.timeline && Array.isArray(selectedArtifact.timeline) && selectedArtifact.timeline.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-dark-200 mb-2">Timeline Events</h4>
                    <div className="space-y-3 max-h-64 overflow-y-auto">
                      {groupTimelineEvents(selectedArtifact.timeline).map((dateGroup, groupIdx) => (
                        <div key={groupIdx} className="bg-dark-900/50 rounded p-2">
                          <div className="flex items-center gap-2 mb-2">
                            <Calendar className="w-3 h-3 text-cyan-400" />
                            <span className="text-xs font-medium text-dark-200">
                              {formatEventDate(dateGroup.date)}
                            </span>
                            <span className="text-xs text-dark-500">
                              ({dateGroup.events.length} event{dateGroup.events.length !== 1 ? 's' : ''})
                            </span>
                          </div>
                          <div className="space-y-2 ml-5">
                            {dateGroup.events.map((event, eventIdx) => (
                              <div key={eventIdx} className="bg-dark-800 rounded p-2 text-xs">
                                <div className="flex items-start justify-between gap-2 mb-1">
                                  <span className="font-medium text-dark-100">{event.name || event.key}</span>
                                  {event.type && (
                                    <span className="text-xs px-2 py-0.5 rounded bg-cyan-600/20 text-cyan-400 flex-shrink-0">
                                      {event.type}
                                    </span>
                                  )}
                                </div>
                                <div className="flex items-center gap-3 mt-1 text-dark-400">
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
                                  <p className="text-dark-300 mt-1 line-clamp-2">{event.summary}</p>
                                )}
                                {event.connections && event.connections.length > 0 && (
                                  <div className="flex flex-wrap gap-1 mt-2">
                                    {event.connections.slice(0, 3).map((conn, connIdx) => (
                                      <span
                                        key={connIdx}
                                        className="text-xs bg-dark-700 text-dark-300 px-2 py-0.5 rounded"
                                      >
                                        {conn.name || conn.key}
                                      </span>
                                    ))}
                                    {event.connections.length > 3 && (
                                      <span className="text-xs text-dark-500">
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

                {selectedArtifact.chat_history && selectedArtifact.chat_history.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-dark-200 mb-2">Chat History</h4>
                    <div className="space-y-2">
                      {selectedArtifact.chat_history.map((msg, idx) => (
                        <div key={idx} className="bg-dark-900/50 rounded p-2 text-xs">
                          <span className="font-medium text-cyan-400">{msg.role === 'user' ? 'User' : 'AI'}:</span>
                          <p className="text-dark-300 mt-1">{msg.content}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={handleLoad}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors"
                  >
                    <Eye className="w-4 h-4" />
                    Load Artifact
                  </button>
                  <button
                    onClick={handleExportPDF}
                    className="flex items-center justify-center gap-2 px-4 py-2 bg-dark-700 hover:bg-dark-600 text-dark-300 rounded-lg transition-colors"
                    title="Export to PDF"
                  >
                    <FileDown className="w-4 h-4" />
                    Export PDF
                  </button>
                </div>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-dark-400">
                <div className="text-center">
                  <Eye className="w-12 h-12 mx-auto mb-3 text-dark-600" />
                  <p>Select an artifact to view details</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

