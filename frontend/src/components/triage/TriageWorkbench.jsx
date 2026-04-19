import React, { useState, useEffect, useCallback } from 'react';
import {
  ArrowLeft, Loader2, HardDrive, Play, RotateCcw,
  CheckCircle2, Circle, ChevronRight, AlertCircle, Plus,
  BookTemplate, Save, FolderInput,
} from 'lucide-react';
import { triageAPI, backgroundTasksAPI } from '../../services/api';
import ScanProgress from './ScanProgress';
import ClassificationProgress from './ClassificationProgress';
import TriageDashboard from './TriageDashboard';
import CustomStageView, { StageBuilderModal } from './CustomStageView';
import TriageAdvisor from './TriageAdvisor';
import { SaveTemplateModal, ApplyTemplateModal } from './TemplateManager';
import IngestToCase from './IngestToCase';

const STAGE_ICONS = {
  scan: HardDrive,
  classify: CheckCircle2,
  profile: CheckCircle2,
  custom: Circle,
};

function StageIndicator({ stages, activeStageIndex, onStageClick }) {
  return (
    <div className="flex items-center gap-1 bg-light-50 rounded-lg p-2 border border-light-200 overflow-x-auto">
      {stages.map((stage, i) => {
        const Icon = STAGE_ICONS[stage.type] || Circle;
        const isActive = i === activeStageIndex;
        const isCompleted = stage.status === 'completed';
        const isFailed = stage.status === 'failed';
        const isRunning = stage.status === 'running';

        return (
          <React.Fragment key={stage.id}>
            {i > 0 && <ChevronRight className="w-4 h-4 text-light-300 flex-shrink-0" />}
            <button
              onClick={() => onStageClick && onStageClick(i)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium flex-shrink-0 transition-colors cursor-pointer ${
                isActive
                  ? 'bg-owl-blue-600 text-white'
                  : isCompleted
                  ? 'bg-green-100 text-green-700 hover:bg-green-200'
                  : isFailed
                  ? 'bg-red-100 text-red-700 hover:bg-red-200'
                  : isRunning
                  ? 'bg-blue-100 text-blue-700'
                  : 'text-light-500 hover:bg-light-100'
              }`}
            >
              {isRunning ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : isCompleted ? (
                <CheckCircle2 className="w-3.5 h-3.5" />
              ) : isFailed ? (
                <AlertCircle className="w-3.5 h-3.5" />
              ) : (
                <Icon className="w-3.5 h-3.5" />
              )}
              {stage.name}
            </button>
          </React.Fragment>
        );
      })}
    </div>
  );
}

export default function TriageWorkbench({ caseId, onBack, authUsername }) {
  const [triageCase, setTriageCase] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeStageIndex, setActiveStageIndex] = useState(0);
  const [showStageBuilder, setShowStageBuilder] = useState(false);
  const [showSaveTemplate, setShowSaveTemplate] = useState(false);
  const [showApplyTemplate, setShowApplyTemplate] = useState(false);
  const [showIngest, setShowIngest] = useState(false);

  const loadCase = useCallback(async () => {
    try {
      const data = await triageAPI.getCase(caseId);
      setTriageCase(data);

      // Auto-select the first non-completed stage, or the last completed one
      const stages = data.stages || [];
      let idx = stages.findIndex((s) => s.status !== 'completed');
      if (idx === -1) idx = stages.length - 1;
      if (idx >= 0) setActiveStageIndex(idx);
    } catch (err) {
      console.error('Failed to load triage case:', err);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    loadCase();
  }, [loadCase]);

  // Poll for updates when a stage is running
  useEffect(() => {
    if (!triageCase) return;
    const stages = triageCase.stages || [];
    const hasRunning = stages.some((s) => s.status === 'running');
    if (!hasRunning) return;

    const interval = setInterval(loadCase, 3000);
    return () => clearInterval(interval);
  }, [triageCase, loadCase]);

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-light-50">
        <Loader2 className="w-8 h-8 animate-spin text-owl-blue-600" />
      </div>
    );
  }

  if (!triageCase) {
    return (
      <div className="h-screen flex items-center justify-center bg-light-50">
        <p className="text-light-600">Triage case not found</p>
      </div>
    );
  }

  const stages = triageCase.stages || [];
  const activeStage = stages[activeStageIndex] || null;
  const hasCustomStages = stages.some((s) => s.type === 'custom');

  return (
    <div className="h-screen flex flex-col bg-light-50">
      {/* Header */}
      <div className="h-16 border-b border-light-200 bg-white flex items-center justify-between px-6 shadow-sm">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="p-2 hover:bg-light-100 rounded-lg transition-colors"
            title="Back to triage cases"
          >
            <ArrowLeft className="w-5 h-5 text-light-600" />
          </button>
          <HardDrive className="w-5 h-5 text-owl-blue-600" />
          <div>
            <h1 className="text-base font-semibold text-owl-blue-900">{triageCase.name}</h1>
            <p className="text-xs text-light-500 font-mono">{triageCase.source_path}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {triageCase.scan_stats?.total_files > 0 && (
            <span className="text-xs text-light-500">
              {triageCase.scan_stats.total_files.toLocaleString()} files
            </span>
          )}
          <button
            onClick={() => setShowIngest(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-white bg-green-600 rounded-lg hover:bg-green-700 transition-colors"
            title="Ingest selected files into an Owl case"
          >
            <FolderInput className="w-3.5 h-3.5" />
            Ingest
          </button>
        </div>
      </div>

      {/* Stage pipeline indicator */}
      <div className="px-6 py-3 bg-white border-b border-light-200 flex items-center gap-3">
        <div className="flex-1">
          <StageIndicator stages={stages} activeStageIndex={activeStageIndex} onStageClick={setActiveStageIndex} />
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            onClick={() => setShowApplyTemplate(true)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-sm text-light-600 border border-light-200 rounded-lg hover:bg-light-50 transition-colors"
            title="Apply a workflow template"
          >
            <BookTemplate className="w-3.5 h-3.5" />
            Templates
          </button>
          {hasCustomStages && (
            <button
              onClick={() => setShowSaveTemplate(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-sm text-light-600 border border-light-200 rounded-lg hover:bg-light-50 transition-colors"
              title="Save stages as template"
            >
              <Save className="w-3.5 h-3.5" />
              Save
            </button>
          )}
          <button
            onClick={() => setShowStageBuilder(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-owl-blue-600 border border-owl-blue-200 rounded-lg hover:bg-owl-blue-50 transition-colors"
            title="Add custom processing stage"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Stage
          </button>
        </div>
      </div>

      {/* Active stage content */}
      <div className="flex-1 overflow-y-auto">
        {activeStage?.type === 'scan' && (
          <ScanProgress
            caseId={caseId}
            triageCase={triageCase}
            stage={activeStage}
            onRefresh={loadCase}
          />
        )}
        {activeStage?.type === 'classify' && (
          <ClassificationProgress
            caseId={caseId}
            triageCase={triageCase}
            stage={activeStage}
            onRefresh={loadCase}
          />
        )}
        {activeStage?.type === 'profile' && (
          <TriageDashboard
            caseId={caseId}
            triageCase={triageCase}
            stage={activeStage}
            onRefresh={loadCase}
          />
        )}
        {activeStage?.type === 'custom' && (
          <CustomStageView
            caseId={caseId}
            triageCase={triageCase}
            stage={activeStage}
            onRefresh={loadCase}
          />
        )}
      </div>

      {/* Triage Advisor floating button + chat */}
      <TriageAdvisor
        caseId={caseId}
        triageCase={triageCase}
        onAction={(suggestion) => {
          // If suggestion has a processor, open stage builder
          if (suggestion.processor) {
            setShowStageBuilder(true);
          }
        }}
      />

      {/* Stage Builder Modal */}
      {showStageBuilder && (
        <StageBuilderModal
          caseId={caseId}
          onCreated={() => {
            setShowStageBuilder(false);
            loadCase();
          }}
          onClose={() => setShowStageBuilder(false)}
        />
      )}

      {/* Save Template Modal */}
      {showSaveTemplate && (
        <SaveTemplateModal
          caseId={caseId}
          onSaved={() => {
            setShowSaveTemplate(false);
          }}
          onClose={() => setShowSaveTemplate(false)}
        />
      )}

      {/* Apply Template Modal */}
      {showApplyTemplate && (
        <ApplyTemplateModal
          caseId={caseId}
          onApplied={() => {
            setShowApplyTemplate(false);
            loadCase();
          }}
          onClose={() => setShowApplyTemplate(false)}
        />
      )}

      {/* Ingest to Case Modal */}
      {showIngest && (
        <IngestToCase
          caseId={caseId}
          triageCase={triageCase}
          onClose={() => setShowIngest(false)}
          onIngested={() => setShowIngest(false)}
        />
      )}
    </div>
  );
}
