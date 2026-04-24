import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Focus } from 'lucide-react';
import { workspaceAPI } from '../../services/api';
import QuickActionsButtons from './QuickActionsButtons';
import PinnedEvidenceSection from './PinnedEvidenceSection';
import ClientProfileSection from './ClientProfileSection';
import WitnessMatrixSection from './WitnessMatrixSection';
import CaseDeadlinesSection from './CaseDeadlinesSection';
import FindingsSection from './FindingsSection';
import TasksSection from './TasksSection';
import AuditLogSection from './AuditLogSection';
import TheoriesSection from './TheoriesSection';
import InvestigativeNotesSection from './InvestigativeNotesSection';
import CaseFilesSection from './CaseFilesSection';
import EntitySummarySection from './EntitySummarySection';
import SnapshotsSection from './SnapshotsSection';
import InvestigationTimelineSection from './InvestigationTimelineSection';
import CellebritePhonesSection from '../cellebrite/CellebritePhonesSection';
import EntitiesPanelSection from '../entities/EntitiesPanelSection';

/**
 * Case Context Panel Component
 * 
 * Left sidebar with all case context sections
 */
export default function CaseContextPanel({
  caseId,
  caseName,
  caseContext,
  onUpdateContext,
  authUsername,
  selectedSection,
  onSectionSelect,
  pinnedItems: externalPinnedItems,
  onRefreshPinned: externalOnRefreshPinned,
}) {
  // Initialize with all sections collapsed by default
  const [collapsedSections, setCollapsedSections] = useState(new Set([
    'theories',
    'pinned-evidence',
    'client-profile',
    'witness-matrix',
    'deadlines',
    'findings',
    'investigative-notes',
    'tasks',
    'entity-summary',
    'case-files',
    'audit-log',
    'snapshots',
    'investigation-timeline',
    'entities',
    'cellebrite',
  ]));
  const [witnesses, setWitnesses] = useState([]);
  const [pinnedItems, setPinnedItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      if (!caseId) return;
      
      setLoading(true);
      try {
        const [witnessesData, pinnedData] = await Promise.all([
          workspaceAPI.getWitnesses(caseId),
          workspaceAPI.getPinnedItems(caseId),
        ]);

        setWitnesses(witnessesData.witnesses || []);
        // Use external pinned items if provided, otherwise use local state
        if (externalPinnedItems !== undefined) {
          setPinnedItems(externalPinnedItems);
        } else {
          setPinnedItems(pinnedData.pinned_items || []);
        }
      } catch (err) {
        console.error('Failed to load case context data:', err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [caseId]);

  // Sync with external pinned items if provided
  useEffect(() => {
    if (externalPinnedItems !== undefined) {
      setPinnedItems(externalPinnedItems);
    }
  }, [externalPinnedItems]);

  const toggleSection = (sectionName, e) => {
    // Stop propagation if this is called from a button click
    if (e) {
      e.stopPropagation();
    }
    setCollapsedSections(prev => {
      const next = new Set(prev);
      if (next.has(sectionName)) {
        next.delete(sectionName);
      } else {
        next.add(sectionName);
      }
      return next;
    });
  };

  const focusSection = (sectionName, e) => {
    e.stopPropagation();
    if (onSectionSelect) {
      onSectionSelect(sectionName);
    }
  };

  const isCollapsed = (sectionName) => collapsedSections.has(sectionName);

  if (loading) {
    return (
      <div className="p-4 text-center text-light-600">
        Loading case context...
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      {/* Case Overview Toggle + Quick Actions */}
      <div className="p-4 border-b border-light-200">
        <button
          onClick={() => {
            if (selectedSection === 'case-overview') {
              onSectionSelect && onSectionSelect(null);
            } else {
              onSectionSelect && onSectionSelect('case-overview');
            }
          }}
          className={`w-full px-3 py-2 text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2 ${
            selectedSection === 'case-overview'
              ? 'bg-owl-blue-500 text-white'
              : 'bg-light-100 text-owl-blue-900 hover:bg-light-200'
          }`}
        >
          <span>Case Overview</span>
          {selectedSection === 'case-overview' && (
            <span className="text-xs">ON</span>
          )}
        </button>
        <QuickActionsButtons caseId={caseId} />
      </div>

      {/* 1. Case Deadlines & Tasks */}
      <div className={selectedSection === 'deadlines' ? 'bg-owl-blue-50' : ''}>
        <CaseDeadlinesSection
          caseId={caseId}
          onRefresh={() => {}}
          isCollapsed={isCollapsed('deadlines')}
          onToggle={(e) => toggleSection('deadlines', e)}
          onFocus={(e) => focusSection('deadlines', e)}
        />
      </div>

      {/* 1b. Findings */}
      <div className={selectedSection === 'findings' ? 'bg-owl-blue-50' : ''}>
        <FindingsSection
          caseId={caseId}
          isCollapsed={isCollapsed('findings')}
          onToggle={(e) => toggleSection('findings', e)}
          onFocus={(e) => focusSection('findings', e)}
        />
      </div>

      {/* 2. Client Profile & Exposure */}
      <div className={selectedSection === 'client-profile' ? 'bg-owl-blue-50' : ''}>
        <ClientProfileSection
          caseContext={caseContext}
          onUpdate={onUpdateContext}
          isCollapsed={isCollapsed('client-profile')}
          onToggle={(e) => toggleSection('client-profile', e)}
          onFocus={(e) => focusSection('client-profile', e)}
        />
      </div>

      {/* 3. Investigative Theories */}
      <div className={`border-b border-light-200 ${selectedSection === 'theories' ? 'bg-owl-blue-50' : ''}`}>
        <TheoriesSection
          caseId={caseId}
          caseName={caseName}
          authUsername={authUsername}
          isCollapsed={isCollapsed('theories')}
          onToggle={(e) => toggleSection('theories', e)}
          onFocus={(e) => focusSection('theories', e)}
        />
      </div>

      {/* 4. Investigative Notes */}
      <div className={selectedSection === 'investigative-notes' ? 'bg-owl-blue-50' : ''}>
        <InvestigativeNotesSection
          caseId={caseId}
          isCollapsed={isCollapsed('investigative-notes')}
          onToggle={(e) => toggleSection('investigative-notes', e)}
          onFocus={(e) => focusSection('investigative-notes', e)}
        />
      </div>

      {/* 5. Tasks */}
      <div className={selectedSection === 'tasks' ? 'bg-owl-blue-50' : ''}>
        <TasksSection
          caseId={caseId}
          onRefresh={() => {}}
          isCollapsed={isCollapsed('tasks')}
          onToggle={(e) => toggleSection('tasks', e)}
          onFocus={(e) => focusSection('tasks', e)}
        />
      </div>

      {/* 6. Snapshots */}
      <div className={selectedSection === 'snapshots' ? 'bg-owl-blue-50' : ''}>
        <SnapshotsSection
          caseId={caseId}
          isCollapsed={isCollapsed('snapshots')}
          onToggle={(e) => toggleSection('snapshots', e)}
          onFocus={(e) => focusSection('snapshots', e)}
        />
      </div>

      {/* 7. Interviews & Statements (Witness Matrix) */}
      <div className={selectedSection === 'witness-matrix' ? 'bg-owl-blue-50' : ''}>
        <WitnessMatrixSection
          caseId={caseId}
          witnesses={witnesses}
          onRefresh={() => {
            workspaceAPI.getWitnesses(caseId).then(data => {
              setWitnesses(data.witnesses || []);
            });
          }}
          isCollapsed={isCollapsed('witness-matrix')}
          onToggle={(e) => toggleSection('witness-matrix', e)}
          onFocus={(e) => focusSection('witness-matrix', e)}
        />
      </div>

      {/* 8. Key Entities */}
      <div className={selectedSection === 'entity-summary' ? 'bg-owl-blue-50' : ''}>
        <div className="border-b border-light-200">
          <div
            className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
            onClick={(e) => toggleSection('entity-summary', e)}
          >
            <div>
              <h3 className="text-sm font-semibold text-owl-blue-900">Key Entities</h3>
              <p className="text-xs text-gray-500 mt-0.5">People, companies, banks, and accounts in this case</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={(e) => { e.stopPropagation(); focusSection('entity-summary', e); }}
                className="p-1 hover:bg-light-100 rounded"
                title="Focus on this section"
              >
                <Focus className="w-4 h-4 text-owl-blue-600" />
              </button>
              {isCollapsed('entity-summary') ? (
                <ChevronRight className="w-4 h-4 text-light-600" />
              ) : (
                <ChevronDown className="w-4 h-4 text-light-600" />
              )}
            </div>
          </div>
          {!isCollapsed('entity-summary') && (
            <div className="max-h-96 overflow-hidden">
              <EntitySummarySection caseId={caseId} />
            </div>
          )}
        </div>
      </div>

      {/* 9. Pinned Evidence */}
      <div className={selectedSection === 'pinned-evidence' ? 'bg-owl-blue-50' : ''}>
        <PinnedEvidenceSection
          caseId={caseId}
          pinnedItems={pinnedItems}
          onRefresh={() => {
            workspaceAPI.getPinnedItems(caseId).then(data => {
              setPinnedItems(data.pinned_items || []);
            });
          }}
          isCollapsed={isCollapsed('pinned-evidence')}
          onToggle={(e) => toggleSection('pinned-evidence', e)}
          onFocus={(e) => focusSection('pinned-evidence', e)}
        />
      </div>

      {/* Entities (case-wide investigator profiles) */}
      <div className={selectedSection === 'entities' ? 'bg-owl-blue-50' : ''}>
        <EntitiesPanelSection
          caseId={caseId}
          collapsed={isCollapsed('entities')}
          onToggle={(next) => {
            // The section signature passes collapsed; pass a synthetic event to
            // reuse the existing toggle handler.
            toggleSection('entities', { preventDefault: () => {} });
          }}
        />
      </div>

      {/* Phone Reports (Cellebrite) — only renders if reports exist */}
      <div className={selectedSection === 'cellebrite' ? 'bg-owl-blue-50' : ''}>
        <CellebritePhonesSection
          caseId={caseId}
          isCollapsed={isCollapsed('cellebrite')}
          onToggle={(e) => toggleSection('cellebrite', e)}
          onFocus={(e) => focusSection('cellebrite', e)}
        />
      </div>

      {/* 10. Case Documents */}
      <div className={selectedSection === 'case-files' ? 'bg-owl-blue-50' : ''}>
        <CaseFilesSection
          caseId={caseId}
          pinnedItems={externalPinnedItems !== undefined ? externalPinnedItems : pinnedItems}
          onRefreshPinned={externalOnRefreshPinned || (async () => {
            const data = await workspaceAPI.getPinnedItems(caseId);
            setPinnedItems(data.pinned_items || []);
          })}
          isCollapsed={isCollapsed('case-files')}
          onToggle={(e) => toggleSection('case-files', e)}
          onFocus={(e) => focusSection('case-files', e)}
        />
      </div>

      {/* 11. Audit Log */}
      <div className={selectedSection === 'audit-log' ? 'bg-owl-blue-50' : ''}>
        <AuditLogSection
          caseId={caseId}
          isCollapsed={isCollapsed('audit-log')}
          onToggle={(e) => toggleSection('audit-log', e)}
          onFocus={(e) => focusSection('audit-log', e)}
        />
      </div>

      {/* 12. Comprehensive Audit Log (Investigation Timeline) */}
      <div className={selectedSection === 'investigation-timeline' ? 'bg-owl-blue-50' : ''}>
        <InvestigationTimelineSection
          caseId={caseId}
          isCollapsed={isCollapsed('investigation-timeline')}
          onToggle={(e) => toggleSection('investigation-timeline', e)}
          onFocus={(e) => focusSection('investigation-timeline', e)}
        />
      </div>
    </div>
  );
}
