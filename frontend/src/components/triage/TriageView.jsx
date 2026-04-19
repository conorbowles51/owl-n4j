import React, { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, Plus, Loader2, HardDrive } from 'lucide-react';
import { triageAPI } from '../../services/api';
import TriageCaseList from './TriageCaseList';
import TriageWorkbench from './TriageWorkbench';

export default function TriageView({ onBack, authUsername }) {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeCaseId, setActiveCaseId] = useState(null);

  const loadCases = useCallback(async () => {
    setLoading(true);
    try {
      const data = await triageAPI.listCases();
      setCases(data.cases || []);
    } catch (err) {
      console.error('Failed to load triage cases:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCases();
  }, [loadCases]);

  const handleOpenCase = useCallback((caseId) => {
    setActiveCaseId(caseId);
  }, []);

  const handleBackToList = useCallback(() => {
    setActiveCaseId(null);
    loadCases();
  }, [loadCases]);

  // Active triage case workbench
  if (activeCaseId) {
    return (
      <TriageWorkbench
        caseId={activeCaseId}
        onBack={handleBackToList}
        authUsername={authUsername}
      />
    );
  }

  // Case list view
  return (
    <div className="h-screen flex flex-col bg-light-50">
      {/* Header */}
      <div className="h-16 border-b border-light-200 bg-white flex items-center justify-between px-6 shadow-sm">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="p-2 hover:bg-light-100 rounded-lg transition-colors"
            title="Back to cases"
          >
            <ArrowLeft className="w-5 h-5 text-light-600" />
          </button>
          <HardDrive className="w-6 h-6 text-owl-blue-600" />
          <h1 className="text-lg font-semibold text-owl-blue-900">Evidence Triage</h1>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <TriageCaseList
          cases={cases}
          loading={loading}
          onRefresh={loadCases}
          onOpenCase={handleOpenCase}
          authUsername={authUsername}
        />
      </div>
    </div>
  );
}
