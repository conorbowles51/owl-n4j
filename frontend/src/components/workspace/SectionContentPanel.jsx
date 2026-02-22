import React from 'react';
import PinnedEvidenceSection from './PinnedEvidenceSection';
import ClientProfileSection from './ClientProfileSection';
import WitnessMatrixSection from './WitnessMatrixSection';
import CaseDeadlinesSection from './CaseDeadlinesSection';
import TasksSection from './TasksSection';
import AuditLogSection from './AuditLogSection';
import TheoriesSection from './TheoriesSection';
import InvestigativeNotesSection from './InvestigativeNotesSection';
import CaseFilesSection from './CaseFilesSection';
import EntitySummarySection from './EntitySummarySection';
import SnapshotsSection from './SnapshotsSection';
import InvestigationTimelineSection from './InvestigationTimelineSection';

/**
 * Section Content Panel
 * 
 * Displays the selected section content in the right panel
 */
export default function SectionContentPanel({
  selectedSection,
  caseId,
  caseContext,
  onUpdateContext,
  authUsername,
  witnesses,
  tasks,
  deadlines,
  pinnedItems,
  onRefreshWitnesses,
  onRefreshTasks,
  onRefreshDeadlines,
  onRefreshPinned,
}) {
  if (!selectedSection) {
    return (
      <div className="h-full flex items-center justify-center p-8">
        <p className="text-light-600 text-center">
          Select a section from the left sidebar to view its details
        </p>
      </div>
    );
  }

  const commonProps = {
    caseId,
    isCollapsed: false,
    onToggle: () => {},
  };

  switch (selectedSection) {
    case 'theories':
      return (
        <div className="h-full flex flex-col p-4">
          <TheoriesSection
            caseId={caseId}
            authUsername={authUsername}
            isCollapsed={false} // Always expanded in content panel
            onToggle={() => {}} // No-op in content panel
            fullHeight={true} // Indicate this is in the content panel
            {...commonProps}
          />
        </div>
      );
    
    case 'pinned-evidence':
      return (
        <div className="h-full flex flex-col p-4">
          <PinnedEvidenceSection
            caseId={caseId}
            pinnedItems={pinnedItems}
            onRefresh={onRefreshPinned}
            isCollapsed={false} // Always expanded in content panel
            onToggle={() => {}} // No-op in content panel
            fullHeight={true} // Indicate this is in the content panel
            {...commonProps}
          />
        </div>
      );
    
    case 'client-profile':
      return (
        <div className="h-full overflow-y-auto p-4">
          <ClientProfileSection
            caseContext={caseContext}
            onUpdate={onUpdateContext}
            {...commonProps}
          />
        </div>
      );
    
    case 'witness-matrix':
      return (
        <div className="h-full overflow-y-auto p-4">
          <WitnessMatrixSection
            caseId={caseId}
            witnesses={witnesses}
            onRefresh={onRefreshWitnesses}
            {...commonProps}
          />
        </div>
      );
    
    case 'deadlines':
      return (
        <div className="h-full overflow-y-auto p-4">
          <CaseDeadlinesSection
            caseId={caseId}
            onRefresh={() => {
              // Component loads its own data, but we can trigger a refresh if needed
            }}
            isCollapsed={false} // Always expanded in content panel
            onToggle={() => {}} // No-op in content panel
          />
        </div>
      );
    
    case 'investigative-notes':
      return (
        <div className="h-full overflow-y-auto p-4">
          <InvestigativeNotesSection
            caseId={caseId}
            {...commonProps}
          />
        </div>
      );
    
    case 'tasks':
      return (
        <div className="h-full overflow-y-auto p-4">
          <TasksSection
            caseId={caseId}
            onRefresh={() => {
              // Component loads its own data, but we can trigger a refresh if needed
            }}
            isCollapsed={false} // Always expanded in content panel
            onToggle={() => {}} // No-op in content panel
          />
        </div>
      );
    
    case 'entity-summary':
      return (
        <div className="h-full flex flex-col p-4">
          <EntitySummarySection caseId={caseId} />
        </div>
      );
    
    case 'case-files':
      return (
        <div className="h-full flex flex-col p-4">
          <CaseFilesSection
            caseId={caseId}
            pinnedItems={pinnedItems}
            onRefreshPinned={onRefreshPinned}
            isCollapsed={false}
            onToggle={() => {}}
            fullHeight={true}
            {...commonProps}
          />
        </div>
      );
    
    case 'audit-log':
      return (
        <div className="h-full flex flex-col p-4">
          <AuditLogSection
            caseId={caseId}
            isCollapsed={false} // Always expanded in content panel
            onToggle={() => {}} // No-op in content panel
            fullHeight={true} // Indicate this is in the content panel
            {...commonProps}
          />
        </div>
      );
    
    case 'snapshots':
      return (
        <div className="h-full flex flex-col p-4">
          <SnapshotsSection
            caseId={caseId}
            isCollapsed={false} // Always expanded in content panel
            onToggle={() => {}} // No-op in content panel
            fullHeight={true} // Indicate this is in the content panel
            {...commonProps}
          />
        </div>
      );
    
    case 'investigation-timeline':
      return (
        <div className="h-full flex flex-col p-4">
          <InvestigationTimelineSection
            caseId={caseId}
            isCollapsed={false} // Always expanded in content panel
            onToggle={() => {}} // No-op in content panel
            fullHeight={true} // Indicate this is in the content panel
            {...commonProps}
          />
        </div>
      );
    
    default:
      return (
        <div className="p-4">
          <p className="text-light-600">Section not found</p>
        </div>
      );
  }
}
