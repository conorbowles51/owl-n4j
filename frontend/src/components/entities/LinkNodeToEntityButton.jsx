import React, { useEffect, useRef, useState } from 'react';
import { Users, Plus } from 'lucide-react';
import { entitiesAPI } from '../../services/api';
import EntityPickerCombobox from './EntityPickerCombobox';
import EntityChip from './EntityChip';

/**
 * Button + popover that links a graph node to one or more CaseEntities.
 * Designed for use in Comms bubbles / Event detail drawers etc.
 *
 * Props:
 *   caseId
 *   nodeKey            — the graph node key to link
 *   compact            — boolean (smaller rendering for inline chips)
 */
export default function LinkNodeToEntityButton({ caseId, nodeKey, compact = false }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleLink = async (entityIds) => {
    if (!nodeKey || entityIds.length === 0) {
      setOpen(false);
      return;
    }
    setBusy(true);
    try {
      for (const id of entityIds) {
        try {
          await entitiesAPI.linkNode(caseId, id, nodeKey);
        } catch {
          /* ignore individual failures */
        }
      }
    } finally {
      setBusy(false);
      setOpen(false);
    }
  };

  return (
    <span ref={wrapRef} className="relative inline-flex">
      <button
        onClick={() => setOpen(!open)}
        disabled={!nodeKey || busy}
        className={
          compact
            ? 'inline-flex items-center gap-0.5 text-[10px] text-owl-blue-600 hover:underline'
            : 'inline-flex items-center gap-1 px-2 py-1 text-xs border border-light-300 rounded hover:bg-light-50 text-light-700'
        }
        title="Link to entity profile"
      >
        <Users className="w-3 h-3" />
        {compact ? '' : 'Link to entity'}
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-1 z-30">
          <EntityPickerCombobox
            caseId={caseId}
            value={[]}
            multi
            onChange={handleLink}
            onClose={() => setOpen(false)}
          />
        </div>
      )}
    </span>
  );
}
