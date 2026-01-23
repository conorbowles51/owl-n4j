import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Edit2, Focus } from 'lucide-react';
import ClientProfileEditorModal from './ClientProfileEditorModal';

/**
 * Client Profile Section
 * 
 * Displays client profile and exposure information in the requested format
 */
export default function ClientProfileSection({
  caseContext,
  onUpdate,
  isCollapsed,
  onToggle,
  onFocus,
}) {
  const [showEditor, setShowEditor] = useState(false);

  const handleSave = async (updateData) => {
    try {
      await onUpdate(updateData);
      setShowEditor(false);
    } catch (err) {
      console.error('Failed to save client profile:', err);
      throw err;
    }
  };

  const clientProfile = caseContext?.client_profile || {};
  const charges = caseContext?.charges || [];
  const allegations = caseContext?.allegations || [];
  const denials = caseContext?.denials || [];
  const legalExposure = caseContext?.legal_exposure || {};
  const defenseStrategy = caseContext?.defense_strategy || [];

  return (
    <div className="border-b border-light-200">
      <div
        className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
        onClick={(e) => onToggle && onToggle(e)}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900">Client Profile & Exposure</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowEditor(true);
            }}
            className="p-1 hover:bg-light-100 rounded"
            title="Edit client profile"
          >
            <Edit2 className="w-4 h-4 text-owl-blue-600" />
          </button>
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
        <div className="px-4 pb-4 space-y-4 text-sm">
          {/* Client */}
          {(clientProfile.name || clientProfile.role) && (
            <div>
              <span className="font-semibold text-owl-blue-900">Client: </span>
              <span className="text-light-700">
                {clientProfile.name}
                {clientProfile.role && `, ${clientProfile.role}`}
              </span>
            </div>
          )}

          {/* Charges */}
          {charges.length > 0 && (
            <div>
              <div className="font-semibold text-owl-blue-900 mb-1">Charges: </div>
              <div className="text-light-700">
                {charges.join(', ')}
              </div>
            </div>
          )}

          {/* Allegations */}
          {allegations.length > 0 && (
            <div>
              <div className="font-semibold text-owl-blue-900 mb-2">Allegations:</div>
              <div className="space-y-1 text-light-700">
                {allegations.map((allegation, idx) => (
                  <div key={idx}>{allegation}</div>
                ))}
              </div>
            </div>
          )}

          {/* Client Denies */}
          {denials.length > 0 && (
            <div>
              <div className="font-semibold text-owl-blue-900 mb-2">Client Denies:</div>
              <div className="space-y-1 text-light-700">
                {denials.map((denial, idx) => (
                  <div key={idx}>{denial}</div>
                ))}
              </div>
            </div>
          )}

          {/* Legal Exposure */}
          {Object.keys(legalExposure).length > 0 && (
            <div>
              <div className="font-semibold text-owl-blue-900 mb-2">Legal Exposure:</div>
              <div className="space-y-1 text-light-700">
                {Object.entries(legalExposure).map(([charge, penalty]) => (
                  <div key={charge}>
                    <span className="font-medium">{charge}:</span> {penalty}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Defense Strategy */}
          {defenseStrategy.length > 0 && (
            <div>
              <div className="font-semibold text-owl-blue-900 mb-2">🎯 Defense Strategy Points:</div>
              <div className="space-y-1 text-light-700">
                {defenseStrategy.map((strategy, idx) => (
                  <div key={idx}>{strategy}</div>
                ))}
              </div>
            </div>
          )}

          {/* Empty State */}
          {!clientProfile.name && charges.length === 0 && allegations.length === 0 && 
           denials.length === 0 && Object.keys(legalExposure).length === 0 && 
           defenseStrategy.length === 0 && (
            <div className="text-xs text-light-500 italic">
              No client profile information. Click the edit button to add information.
            </div>
          )}
        </div>
      )}

      {showEditor && (
        <ClientProfileEditorModal
          isOpen={showEditor}
          onClose={() => setShowEditor(false)}
          caseContext={caseContext}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
