import React, { useState, useEffect } from 'react';
import { FolderOpen, X, Trash2, Eye, Calendar, Clock, FileText } from 'lucide-react';
import { casesAPI } from '../services/api';

/**
 * CaseList Component
 * 
 * Displays a list of saved cases with version history
 */
export default function CaseList({ isOpen, onClose, onLoadCase }) {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCase, setSelectedCase] = useState(null);
  const [selectedVersion, setSelectedVersion] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadCases();
    }
  }, [isOpen]);

  const loadCases = async () => {
    setLoading(true);
    try {
      const data = await casesAPI.list();
      setCases(data);
    } catch (err) {
      console.error('Failed to load cases:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (caseId, e) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this case? This will delete all versions.')) {
      return;
    }

    try {
      await casesAPI.delete(caseId);
      await loadCases();
      if (selectedCase?.id === caseId) {
        setSelectedCase(null);
        setSelectedVersion(null);
      }
    } catch (err) {
      console.error('Failed to delete case:', err);
      alert(`Failed to delete case: ${err.message}`);
    }
  };

  const handleView = async (caseItem) => {
    try {
      const fullCase = await casesAPI.get(caseItem.id);
      setSelectedCase(fullCase);
      // Select latest version by default
      if (fullCase.versions && fullCase.versions.length > 0) {
        setSelectedVersion(fullCase.versions[0]);
      }
    } catch (err) {
      console.error('Failed to load case:', err);
      alert(`Failed to load case: ${err.message}`);
    }
  };

  const handleLoad = () => {
    if (onLoadCase && selectedCase && selectedVersion) {
      onLoadCase(selectedCase, selectedVersion);
    }
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg w-full max-w-5xl h-[85vh] flex flex-col border border-light-200 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <div className="flex items-center gap-2">
            <FolderOpen className="w-5 h-5 text-owl-blue-600" />
            <h2 className="text-lg font-semibold text-owl-blue-900">Saved Cases</h2>
            <span className="text-xs text-light-600 bg-light-100 px-2 py-1 rounded">
              {cases.length} case{cases.length !== 1 ? 's' : ''}
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
          {/* Cases List */}
          <div className="w-1/3 border-r border-light-200 overflow-y-auto">
            {loading ? (
              <div className="p-8 text-center text-light-600">Loading cases...</div>
            ) : cases.length === 0 ? (
              <div className="p-8 text-center text-light-600">
                <FolderOpen className="w-12 h-12 mx-auto mb-3 text-light-400" />
                <p>No cases saved yet</p>
              </div>
            ) : (
              <div className="p-2">
                {cases.map((caseItem) => (
                  <div
                    key={caseItem.id}
                    onClick={() => handleView(caseItem)}
                    className={`p-3 mb-2 rounded-lg cursor-pointer transition-colors ${
                      selectedCase?.id === caseItem.id
                        ? 'bg-owl-blue-100 border border-owl-blue-300'
                        : 'bg-light-50 hover:bg-light-100 border border-light-200'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-owl-blue-900 truncate">{caseItem.name}</h3>
                        <div className="flex items-center gap-3 mt-2 text-xs text-light-600">
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {formatDate(caseItem.updated_at)}
                          </span>
                          <span>{caseItem.version_count} version{caseItem.version_count !== 1 ? 's' : ''}</span>
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleDelete(caseItem.id, e)}
                        className="p-1 hover:bg-light-200 rounded transition-colors ml-2"
                        title="Delete case"
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Case Details */}
          <div className="flex-1 p-4 overflow-y-auto">
            {selectedCase ? (
              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold text-owl-blue-900 mb-2">{selectedCase.name}</h3>
                  <div className="text-xs text-light-600">
                    <p>Created: {formatDate(selectedCase.created_at)}</p>
                    <p>Updated: {formatDate(selectedCase.updated_at)}</p>
                    <p>Versions: {selectedCase.versions.length}</p>
                  </div>
                </div>

                {/* Version Selection */}
                <div>
                  <h4 className="text-sm font-semibold text-owl-blue-900 mb-2">Versions</h4>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {selectedCase.versions.map((version) => (
                      <div
                        key={version.version}
                        onClick={() => setSelectedVersion(version)}
                        className={`p-3 rounded-lg cursor-pointer transition-colors border ${
                          selectedVersion?.version === version.version
                            ? 'bg-owl-blue-100 border-owl-blue-300'
                            : 'bg-light-50 hover:bg-light-100 border-light-200'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4 text-owl-blue-600" />
                            <span className="font-medium text-owl-blue-900">Version {version.version}</span>
                          </div>
                          <span className="text-xs text-light-600">
                            {formatDate(version.timestamp)}
                          </span>
                        </div>
                        {version.save_notes && (
                          <p className="text-xs text-light-700 mt-1 line-clamp-2">{version.save_notes}</p>
                        )}
                        <div className="text-xs text-light-600 mt-1">
                          {version.snapshots?.length || 0} snapshot{(version.snapshots?.length || 0) !== 1 ? 's' : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Selected Version Details */}
                {selectedVersion && (
                  <div className="border-t border-light-200 pt-4">
                    <h4 className="text-sm font-semibold text-owl-blue-900 mb-2">
                      Version {selectedVersion.version} Details
                    </h4>
                    {selectedVersion.save_notes && (
                      <div className="mb-3">
                        <p className="text-xs font-medium text-light-700 mb-1">Save Notes:</p>
                        <p className="text-sm text-light-700 whitespace-pre-wrap bg-light-50 rounded p-2 border border-light-200">
                          {selectedVersion.save_notes}
                        </p>
                      </div>
                    )}
                    <div className="text-xs text-light-600 mb-3">
                      <p>Saved: {formatDate(selectedVersion.timestamp)}</p>
                      <p>Snapshots: {selectedVersion.snapshots?.length || 0}</p>
                      <p>Cypher queries: {selectedVersion.cypher_queries.split('\n\n').length} statements</p>
                    </div>
                    <button
                      onClick={handleLoad}
                      className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-owl-orange-500 hover:bg-owl-orange-600 text-white rounded-lg transition-colors"
                    >
                      <Eye className="w-4 h-4" />
                      Load This Version
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-light-600">
                <div className="text-center">
                  <Eye className="w-12 h-12 mx-auto mb-3 text-light-400" />
                  <p>Select a case to view details</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

