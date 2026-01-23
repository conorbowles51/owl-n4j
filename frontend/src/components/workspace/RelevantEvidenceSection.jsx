import React from 'react';
import { ChevronDown, ChevronRight, Filter, Focus } from 'lucide-react';

/**
 * Relevant Evidence Section
 * 
 * Displays evidence filtered by theory/context
 */
export default function RelevantEvidenceSection({
  caseId,
  isCollapsed,
  onToggle,
  onFocus,
}) {
  return (
    <div className="border-b border-light-200">
      <div
        className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
        onClick={(e) => onToggle && onToggle(e)}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900">Relevant Evidence</h3>
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
        <div className="px-4 pb-4">
          <p className="text-xs text-light-500 italic">
            Evidence filtered by selected theory/context will appear here
          </p>
        </div>
      )}
    </div>
  );
}
