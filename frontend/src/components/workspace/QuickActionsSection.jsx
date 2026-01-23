import React, { useState } from 'react';
import { Camera, FileText, Link2 } from 'lucide-react';
import AddPhotoModal from './AddPhotoModal';
import AddNoteModal from './AddNoteModal';
import LinkEntityModal from './LinkEntityModal';

/**
 * Quick Actions Section
 * 
 * Quick action buttons for adding photos, notes, and linking entities
 */
export default function QuickActionsSection({ caseId, onUploaded }) {
  const [showPhotoModal, setShowPhotoModal] = useState(false);
  const [showNoteModal, setShowNoteModal] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);

  const handleUploaded = () => {
    if (onUploaded) {
      onUploaded();
    }
  };

  return (
    <>
      <div className="p-4 border-b border-light-200">
        <h3 className="text-sm font-semibold text-owl-blue-900 mb-3">Quick Actions</h3>
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={() => setShowPhotoModal(true)}
            className="flex flex-col items-center gap-1 p-3 bg-light-50 hover:bg-light-100 rounded-lg transition-colors"
            title="Add Photo"
          >
            <Camera className="w-5 h-5 text-owl-blue-600" />
            <span className="text-xs text-light-600">Photo</span>
          </button>
          <button
            onClick={() => setShowNoteModal(true)}
            className="flex flex-col items-center gap-1 p-3 bg-light-50 hover:bg-light-100 rounded-lg transition-colors"
            title="Add Note"
          >
            <FileText className="w-5 h-5 text-owl-blue-600" />
            <span className="text-xs text-light-600">Note</span>
          </button>
          <button
            onClick={() => setShowLinkModal(true)}
            className="flex flex-col items-center gap-1 p-3 bg-light-50 hover:bg-light-100 rounded-lg transition-colors"
            title="Add Link"
          >
            <Link2 className="w-5 h-5 text-owl-blue-600" />
            <span className="text-xs text-light-600">Link</span>
          </button>
        </div>
      </div>

      <AddPhotoModal
        isOpen={showPhotoModal}
        onClose={() => setShowPhotoModal(false)}
        caseId={caseId}
        onUploaded={handleUploaded}
      />
      <AddNoteModal
        isOpen={showNoteModal}
        onClose={() => setShowNoteModal(false)}
        caseId={caseId}
        onUploaded={handleUploaded}
      />
      <LinkEntityModal
        isOpen={showLinkModal}
        onClose={() => setShowLinkModal(false)}
        caseId={caseId}
        onUploaded={handleUploaded}
      />
    </>
  );
}
