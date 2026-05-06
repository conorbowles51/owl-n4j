import React from 'react';
import { Filter, Smartphone } from 'lucide-react';

import { usePhoneReports } from '../../../context/PhoneReportsContext';

/**
 * Empty-state shown inside any Cellebrite tab when the user has
 * deselected every phone in the global PhoneReportsContext.
 *
 * Without this, the tabs go silent (empty list / blank map) and the
 * user can't tell whether the case truly has no data or whether the
 * filter has hidden everything.
 *
 * Render conditionally:
 *   {ctx?.noneSelected && <NoPhonesSelectedEmptyState />}
 */
export default function NoPhonesSelectedEmptyState({
  message = 'No phones selected — choose at least one phone to see data.',
}) {
  const ctx = usePhoneReports();
  if (!ctx || !ctx.hasReports) return null;

  return (
    <div className="flex-1 flex flex-col items-center justify-center text-light-500 bg-light-50 p-8 text-center">
      <div className="relative mb-4">
        <Smartphone className="w-12 h-12 text-light-300" />
        <Filter className="w-5 h-5 text-amber-500 absolute -bottom-1 -right-1 bg-white rounded-full p-0.5" />
      </div>
      <div className="text-sm font-medium text-light-700 mb-1">
        Filtered out
      </div>
      <div className="text-xs text-light-500 max-w-sm mb-4">
        {message}
      </div>
      <button
        type="button"
        onClick={ctx.selectAll}
        className="px-3 py-1.5 text-xs font-medium border border-owl-blue-400 bg-owl-blue-50 text-owl-blue-700 rounded-md hover:bg-owl-blue-100 transition-colors"
      >
        Select all {ctx.reports.length} phones
      </button>
    </div>
  );
}
