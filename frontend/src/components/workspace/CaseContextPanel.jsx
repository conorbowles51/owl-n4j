import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Focus } from 'lucide-react';
import { workspaceAPI } from '../../services/api';
import QuickActionsSection from './QuickActionsSection';
import PinnedEvidenceSection from './PinnedEvidenceSection';
import ClientProfileSection from './ClientProfileSection';
import WitnessMatrixSection from './WitnessMatrixSection';
import CaseDeadlinesSection from './CaseDeadlinesSection';
import TasksSection from './TasksSection';
import DocumentsSection from './DocumentsSection';
import AuditLogSection from './AuditLogSection';
import TheoriesSection from './TheoriesSection';
import InvestigativeNotesSection from './InvestigativeNotesSection';
import AllEvidenceSection from './AllEvidenceSection';
import SnapshotsSection from './SnapshotsSection';
import InvestigationTimelineSection from './InvestigationTimelineSection';

/**
 * Case Context Panel Component
 * 
 * Left sidebar with all case context sections
 */
export default function CaseContextPanel({
  caseId,
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
    'quick-actions',
    'pinned-evidence',
    'client-profile',
    'witness-matrix',
    'deadlines',
    'investigative-notes',
    'tasks',
    'all-evidence',
    'documents',
    'audit-log',
    'snapshots',
    'investigation-timeline',
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
      {/* Case Overview Toggle */}
      <div className="p-4 border-b border-light-200">
        <button
          onClick={() => {
            if (selectedSection === 'case-overview') {
              // Turn off - clear selection to show graph/text view
              onSectionSelect && onSectionSelect(null);
            } else {
              // Turn on - show case overview
              onSectionSelect && onSectionSelect('case-overview');
            }
          }}
          className={`w-full px-3 py-2 text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2 ${
            selectedSection === 'case-overview'
              ? 'bg-owl-blue-500 text-white'
              : 'bg-light-100 text-owl-blue-900 hover:bg-light-200'
          }`}
        >
          <span>📋</span>
          <span>Case Overview</span>
          {selectedSection === 'case-overview' && (
            <span className="text-xs">ON</span>
          )}
        </button>
      </div>

      {/* Theories */}
      <div className={`border-b border-light-200 ${selectedSection === 'theories' ? 'bg-owl-blue-50' : ''}`}>
        <TheoriesSection
          caseId={caseId}
          authUsername={authUsername}
          isCollapsed={isCollapsed('theories')}
          onToggle={(e) => toggleSection('theories', e)}
          onFocus={(e) => focusSection('theories', e)}
        />
      </div>

      {/* Quick Actions */}
      <div className={`border-b border-light-200 ${selectedSection === 'quick-actions' ? 'bg-owl-blue-50' : ''}`}>
        <div
          className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
          onClick={(e) => toggleSection('quick-actions', e)}
        >
          <h3 className="text-sm font-semibold text-owl-blue-900">Quick Actions</h3>
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => focusSection('quick-actions', e)}
              className="p-1 hover:bg-light-100 rounded transition-colors"
              title="Focus on this section"
            >
              <Focus className="w-4 h-4 text-owl-blue-600" />
            </button>
            {isCollapsed('quick-actions') ? (
              <ChevronRight className="w-4 h-4 text-light-600" />
            ) : (
              <ChevronDown className="w-4 h-4 text-light-600" />
            )}
          </div>
        </div>
        {!isCollapsed('quick-actions') && (
          <div className="px-4 pb-4">
            <QuickActionsSection 
              caseId={caseId} 
              onUploaded={() => {
                // Trigger refresh of documents section
                window.dispatchEvent(new Event('documents-refresh'));
              }}
            />
          </div>
        )}
      </div>

      {/* Pinned Evidence */}
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

      {/* Client Profile & Exposure */}
      <div className={selectedSection === 'client-profile' ? 'bg-owl-blue-50' : ''}>
        <ClientProfileSection
          caseContext={caseContext}
          onUpdate={onUpdateContext}
          isCollapsed={isCollapsed('client-profile')}
          onToggle={(e) => toggleSection('client-profile', e)}
          onFocus={(e) => focusSection('client-profile', e)}
        />
      </div>

      {/* Witness Matrix */}
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

      {/* Case Deadlines & Trial Info */}
      <div className={selectedSection === 'deadlines' ? 'bg-owl-blue-50' : ''}>
        <CaseDeadlinesSection
          caseId={caseId}
          onRefresh={() => {
            // Component loads its own data, but we can trigger a refresh if needed
          }}
          isCollapsed={isCollapsed('deadlines')}
          onToggle={(e) => toggleSection('deadlines', e)}
          onFocus={(e) => focusSection('deadlines', e)}
        />
      </div>

      {/* Investigative Notes */}
      <div className={selectedSection === 'investigative-notes' ? 'bg-owl-blue-50' : ''}>
        <InvestigativeNotesSection
          caseId={caseId}
          isCollapsed={isCollapsed('investigative-notes')}
          onToggle={(e) => toggleSection('investigative-notes', e)}
          onFocus={(e) => focusSection('investigative-notes', e)}
        />
      </div>

      {/* Pending Tasks */}
      <div className={selectedSection === 'tasks' ? 'bg-owl-blue-50' : ''}>
        <TasksSection
          caseId={caseId}
          onRefresh={() => {
            // Component loads its own data, but we can trigger a refresh if needed
          }}
          isCollapsed={isCollapsed('tasks')}
          onToggle={(e) => toggleSection('tasks', e)}
          onFocus={(e) => focusSection('tasks', e)}
        />
      </div>

      {/* All Evidence */}
      <div className={selectedSection === 'all-evidence' ? 'bg-owl-blue-50' : ''}>
        <AllEvidenceSection
          caseId={caseId}
          pinnedItems={externalPinnedItems !== undefined ? externalPinnedItems : pinnedItems}
          onRefreshPinned={externalOnRefreshPinned || (async () => {
            const data = await workspaceAPI.getPinnedItems(caseId);
            setPinnedItems(data.pinned_items || []);
          })}
          isCollapsed={isCollapsed('all-evidence')}
          onToggle={(e) => toggleSection('all-evidence', e)}
          onFocus={(e) => focusSection('all-evidence', e)}
        />
      </div>

      {/* Case Documents */}
      <div className={selectedSection === 'documents' ? 'bg-owl-blue-50' : ''}>
        <DocumentsSection
          caseId={caseId}
          isCollapsed={isCollapsed('documents')}
          onToggle={(e) => toggleSection('documents', e)}
          onFocus={(e) => focusSection('documents', e)}
        />
      </div>

      {/* Audit Log */}
      <div className={selectedSection === 'audit-log' ? 'bg-owl-blue-50' : ''}>
        <AuditLogSection
          caseId={caseId}
          isCollapsed={isCollapsed('audit-log')}
          onToggle={(e) => toggleSection('audit-log', e)}
          onFocus={(e) => focusSection('audit-log', e)}
        />
      </div>

      {/* Snapshots */}
      <div className={selectedSection === 'snapshots' ? 'bg-owl-blue-50' : ''}>
        <SnapshotsSection
          caseId={caseId}
          isCollapsed={isCollapsed('snapshots')}
          onToggle={(e) => toggleSection('snapshots', e)}
          onFocus={(e) => focusSection('snapshots', e)}
        />
      </div>

      {/* Investigation Timeline */}
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
