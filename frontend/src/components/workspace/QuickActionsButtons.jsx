import React, { useState } from 'react';
import { Camera, FileText, Link2 } from 'lucide-react';
import AddPhotoModal from './AddPhotoModal';
import AddNoteModal from './AddNoteModal';
import LinkEntityModal from './LinkEntityModal';

/**
 * Quick Actions Buttons
 *
 * Three always-visible buttons (Photo, Note, Link) with their modals.
 * Rendered underneath the Case Overview button.
 */
export default function QuickActionsButtons({ caseId, onUploaded }) {
  const [showPhotoModal, setShowPhotoModal] = useState(false);
  const [showNoteModal, setShowNoteModal] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);

  const handleUploaded = () => {
    if (onUploaded) onUploaded();
    window.dispatchEvent(new Event('documents-refresh'));
  };

  return (
    <>
      <div className="grid grid-cols-3 gap-2 mt-3">
        <button
          onClick={() => setShowPhotoModal(true)}
          className="flex flex-col items-center gap-1 p-2 bg-light-50 hover:bg-light-100 rounded-lg transition-colors"
          title="Add Photo"
        >
          <Camera className="w-4 h-4 text-owl-blue-600" />
          <span className="text-xs text-light-600">Photo</span>
        </button>
        <button
          onClick={() => setShowNoteModal(true)}
          className="flex flex-col items-center gap-1 p-2 bg-light-50 hover:bg-light-100 rounded-lg transition-colors"
          title="Add Note"
        >
          <FileText className="w-4 h-4 text-owl-blue-600" />
          <span className="text-xs text-light-600">Note</span>
        </button>
        <button
          onClick={() => setShowLinkModal(true)}
          className="flex flex-col items-center gap-1 p-2 bg-light-50 hover:bg-light-100 rounded-lg transition-colors"
          title="Add Link"
        >
          <Link2 className="w-4 h-4 text-owl-blue-600" />
          <span className="text-xs text-light-600">Link</span>
        </button>
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
