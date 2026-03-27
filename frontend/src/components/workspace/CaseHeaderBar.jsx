import React from 'react';
import { ArrowLeft, Users, Search, Download, Settings } from 'lucide-react';
import { formatDate } from '../../utils/dateFormat';

/**
 * Case Header Bar Component
 * 
 * Displays case title, ID, type, due date, and online presence
 */
export default function CaseHeaderBar({
  caseName,
  caseId,
  caseType,
  trialDate,
  onlineUsers,
  onBack,
  onLogoClick,
}) {
  return (
    <div className="h-16 border-b border-light-200 bg-white flex items-center justify-between px-6 shadow-sm">
      <div className="flex items-center gap-4">
        <button
          onClick={onBack}
          className="p-2 hover:bg-light-100 rounded-lg transition-colors"
          title="Back to cases"
        >
          <ArrowLeft className="w-5 h-5 text-light-600" />
        </button>

        {/* Owl logo: same size and click as main app (account dropdown) */}
        <button
          type="button"
          onClick={onLogoClick || undefined}
          className="group focus:outline-none relative flex-shrink-0 overflow-hidden"
          title="Account"
        >
          <img
            src="/owl-logo.webp"
            alt="Owl Consultancy Group"
            className="w-10 h-10 object-contain"
          />
        </button>

        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-lg font-semibold text-owl-blue-900">{caseName}</h1>
            {caseId && (
              <p className="text-xs text-light-600">Case ID: {caseId}</p>
            )}
          </div>
          {caseType && (
            <span className="px-2 py-1 text-xs bg-owl-blue-100 text-owl-blue-700 rounded">
              {caseType}
            </span>
          )}
          {trialDate && (
            <span className="text-sm text-light-600">
              Trial: {formatDate(trialDate)}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Online Presence */}
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-light-600" />
          <span className="text-sm text-light-600">
            {onlineUsers.length} online
          </span>
        </div>

        {/* Quick Actions */}
        <button
          className="p-2 hover:bg-light-100 rounded-lg transition-colors"
          title="Search"
        >
          <Search className="w-5 h-5 text-light-600" />
        </button>
        <button
          className="p-2 hover:bg-light-100 rounded-lg transition-colors"
          title="Export"
        >
          <Download className="w-5 h-5 text-light-600" />
        </button>
        <button
          className="p-2 hover:bg-light-100 rounded-lg transition-colors"
          title="Settings"
        >
          <Settings className="w-5 h-5 text-light-600" />
        </button>
      </div>
    </div>
  );
}
