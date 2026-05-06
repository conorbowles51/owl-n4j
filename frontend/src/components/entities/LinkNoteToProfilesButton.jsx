import React, { useState, useEffect, useRef } from 'react';
import { Users } from 'lucide-react';
import EntityPickerCombobox from './EntityPickerCombobox';
import EntityChip from './EntityChip';
import { entitiesAPI, workspaceAPI } from '../../services/api';

/**
 * Link an investigative note to one or more Profiles (CaseEntity).
 *
 * Uses the existing EntityPickerCombobox + workspaceAPI.linkNoteProfiles
 * (additive). On open it loads the note's currently-linked profile ids
 * and renders them as chips so the user can deselect.
 *
 * Props:
 *   caseId
 *   noteId
 *   linkedProfileIds : string[]  — current ids on the note
 *   onChanged        : ()=>void  — fires after a successful link/unlink
 */
export default function LinkNoteToProfilesButton({
  caseId,
  noteId,
  linkedProfileIds = [],
  onChanged,
}) {
  const [open, setOpen] = useState(false);
  const [profiles, setProfiles] = useState([]);
  const [working, setWorking] = useState(false);
  const wrapperRef = useRef(null);

  // Hydrate the chips when the popover opens — fetch every profile in
  // the case and intersect with the note's linked ids.
  useEffect(() => {
    if (!open || !caseId) return;
    let cancelled = false;
    entitiesAPI
      .list(caseId, { limit: 500 })
      .then((data) => {
        if (cancelled) return;
        const all = data?.entities || [];
        const lookup = new Set(linkedProfileIds || []);
        setProfiles(all.filter((e) => lookup.has(e.id)));
      })
      .catch(() => {
        if (!cancelled) setProfiles([]);
      });
    return () => { cancelled = true; };
  }, [open, caseId, linkedProfileIds]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const handlePick = async (selected) => {
    if (!selected || working) return;
    const sel = Array.isArray(selected) ? selected : [selected];
    const newIds = sel.map((e) => e.id).filter(Boolean);
    if (newIds.length === 0) return;
    setWorking(true);
    try {
      await workspaceAPI.linkNoteProfiles(caseId, noteId, newIds);
      onChanged?.();
    } finally {
      setWorking(false);
    }
  };

  const handleRemove = async (profile) => {
    if (working || !profile?.id) return;
    setWorking(true);
    try {
      await workspaceAPI.unlinkNoteProfiles(caseId, noteId, [profile.id]);
      onChanged?.();
    } finally {
      setWorking(false);
    }
  };

  const count = profiles.length;

  return (
    <div ref={wrapperRef} className="relative inline-block">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors inline-flex items-center gap-1"
        title="Link this note to a profile"
      >
        <Users className="w-4 h-4 text-owl-blue-600" />
        {count > 0 && (
          <span className="text-[10px] text-owl-blue-700 font-semibold tabular-nums">{count}</span>
        )}
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-1 z-30 w-[320px] bg-white border border-light-300 rounded-md shadow-lg p-2">
          {profiles.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {profiles.map((p) => (
                <EntityChip
                  key={p.id}
                  entity={p}
                  removable
                  onRemove={() => handleRemove(p)}
                />
              ))}
            </div>
          )}
          <EntityPickerCombobox
            caseId={caseId}
            value={profiles}
            multi
            onChange={handlePick}
          />
        </div>
      )}
    </div>
  );
}
