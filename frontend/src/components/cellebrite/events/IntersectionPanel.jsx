import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import IntersectionMethodCard from './IntersectionMethodCard';

const METHODS = ['spatial', 'cell_tower', 'wifi', 'comm_hub', 'convoy'];

export default function IntersectionPanel({
  caseId,
  reportKeys,
  startDate,
  endDate,
  results,         // { [method]: { matches, params_used } }
  onResult,        // (method, result) => void
  onJumpToMatch,   // (match) => void
  collapsed = false,
  onToggleCollapsed,
}) {
  if (collapsed) {
    return (
      <div className="flex flex-col items-center border-l border-light-200 bg-light-50 w-8">
        <button
          onClick={() => onToggleCollapsed?.(false)}
          className="p-2 text-light-500 hover:text-owl-blue-700"
          title="Show intersection panel"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <div
          className="text-[10px] text-light-500 transform -rotate-90 whitespace-nowrap mt-6"
        >
          Intersections
        </div>
      </div>
    );
  }

  return (
    <div className="w-72 flex-shrink-0 border-l border-light-200 bg-light-50 flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-light-200 bg-white">
        <div className="text-xs font-semibold text-owl-blue-900">Intersections</div>
        <button
          onClick={() => onToggleCollapsed?.(true)}
          className="p-1 text-light-500 hover:text-owl-blue-700"
          title="Collapse panel"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {METHODS.map((m) => (
          <IntersectionMethodCard
            key={m}
            method={m}
            caseId={caseId}
            reportKeys={reportKeys}
            startDate={startDate}
            endDate={endDate}
            result={results?.[m] || null}
            onResult={onResult}
            onJumpToMatch={onJumpToMatch}
          />
        ))}
      </div>
    </div>
  );
}
