import React, { useState, useEffect } from 'react';
import { FileText, Lightbulb } from 'lucide-react';
import AuditLogTab from './AuditLogTab';
import TheoriesTab from './TheoriesTab';

/**
 * Investigation Panel Component
 * 
 * Right sidebar with Audit Log and Theories tabs
 */
export default function InvestigationPanel({
  caseId,
  selectedNode,
  authUsername,
}) {
  const [activeTab, setActiveTab] = useState('audit');

  return (
    <div className="h-full flex flex-col">
      {/* Tab Header */}
      <div className="flex border-b border-light-200">
        <button
          onClick={() => setActiveTab('audit')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
            activeTab === 'audit'
              ? 'bg-owl-blue-50 text-owl-blue-900 border-b-2 border-owl-blue-600'
              : 'text-light-600 hover:bg-light-50'
          }`}
        >
          <FileText className="w-4 h-4" />
          Audit Log
        </button>
        <button
          onClick={() => setActiveTab('theories')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
            activeTab === 'theories'
              ? 'bg-owl-blue-50 text-owl-blue-900 border-b-2 border-owl-blue-600'
              : 'text-light-600 hover:bg-light-50'
          }`}
        >
          <Lightbulb className="w-4 h-4" />
          Theories
        </button>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'audit' && (
          <AuditLogTab caseId={caseId} />
        )}
        {activeTab === 'theories' && (
          <TheoriesTab caseId={caseId} authUsername={authUsername} />
        )}
      </div>
    </div>
  );
}
