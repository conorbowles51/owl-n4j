import React from 'react';
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

/**
 * Case Overview View
 * 
 * Displays all sections side by side in a horizontal scrollable layout
 */
export default function CaseOverviewView({
  caseId,
  caseContext,
  onUpdateContext,
  authUsername,
  witnesses,
  tasks,
  deadlines,
  pinnedItems,
}) {
  const commonProps = {
    caseId,
    isCollapsed: false,
    onToggle: () => {},
  };

  return (
    <div className="h-full p-4 bg-light-50">
      <div className="flex gap-4 overflow-x-auto pb-4 h-full" style={{ minWidth: 'max-content' }}>
        {/* Each section in its own card */}
        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <TheoriesSection
              caseId={caseId}
              authUsername={authUsername}
              {...commonProps}
            />
          </div>
        </div>

        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <QuickActionsSection caseId={caseId} />
          </div>
        </div>

        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <PinnedEvidenceSection
              caseId={caseId}
              pinnedItems={pinnedItems}
              onRefresh={() => {}}
              {...commonProps}
            />
          </div>
        </div>

        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <ClientProfileSection
              caseContext={caseContext}
              onUpdate={onUpdateContext}
              {...commonProps}
            />
          </div>
        </div>

        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <WitnessMatrixSection
              caseId={caseId}
              witnesses={witnesses}
              onRefresh={() => {}}
              {...commonProps}
            />
          </div>
        </div>

        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <CaseDeadlinesSection
              caseId={caseId}
              deadlines={deadlines}
              onRefresh={() => {}}
              {...commonProps}
            />
          </div>
        </div>

        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <InvestigativeNotesSection
              caseId={caseId}
              {...commonProps}
            />
          </div>
        </div>

        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <TasksSection
              caseId={caseId}
              tasks={tasks}
              onRefresh={() => {}}
              {...commonProps}
            />
          </div>
        </div>

        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <AllEvidenceSection
              caseId={caseId}
              {...commonProps}
            />
          </div>
        </div>

        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <DocumentsSection
              caseId={caseId}
              {...commonProps}
            />
          </div>
        </div>

        <div className="flex-shrink-0 w-96 h-full">
          <div className="bg-white border border-light-200 rounded-lg p-4 h-full overflow-y-auto shadow-sm">
            <AuditLogSection
              caseId={caseId}
              {...commonProps}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
