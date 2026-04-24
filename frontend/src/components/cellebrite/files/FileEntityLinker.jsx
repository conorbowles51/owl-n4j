import React, { useEffect, useState, useRef } from 'react';
import { Plus, Link2 } from 'lucide-react';
import { evidenceTagsAPI, entitiesAPI } from '../../../services/api';
import EntityChip from '../../entities/EntityChip';
import EntityPickerCombobox from '../../entities/EntityPickerCombobox';
import EntityDetailDrawer from '../../entities/EntityDetailDrawer';

/**
 * Chip row showing a file's linked entities with add/remove and inline picker.
 *
 * Props:
 *   caseId
 *   evidenceId
 *   entityIds           — current linked ids
 *   onChange            — (ids) => void
 */
export default function FileEntityLinker({
  caseId,
  evidenceId,
  entityIds = [],
  onChange,
}) {
  const [entityMap, setEntityMap] = useState({});
  const [picking, setPicking] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState(null);
  const pickerWrapRef = useRef(null);

  // Resolve entity IDs to full entities for chip display
  useEffect(() => {
    const missing = entityIds.filter((id) => !entityMap[id]);
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.all(missing.map((id) => entitiesAPI.get(caseId, id).catch(() => null))).then(
      (results) => {
        if (cancelled) return;
        const next = { ...entityMap };
        results.forEach((ent, i) => {
          if (ent) next[missing[i]] = ent;
        });
        setEntityMap(next);
      }
    );
    return () => { cancelled = true; };
  }, [entityIds, caseId]);

  // Close picker on outside click
  useEffect(() => {
    if (!picking) return;
    const handler = (e) => {
      if (pickerWrapRef.current && !pickerWrapRef.current.contains(e.target)) {
        setPicking(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [picking]);

  const commitNext = async (nextIds) => {
    const prev = new Set(entityIds);
    const next = new Set(nextIds);
    const toAdd = [...next].filter((x) => !prev.has(x));
    const toRemove = [...prev].filter((x) => !next.has(x));
    try {
      if (toAdd.length > 0) {
        await evidenceTagsAPI.linkEntities(caseId, [evidenceId], toAdd);
      }
      if (toRemove.length > 0) {
        await evidenceTagsAPI.unlinkEntities(caseId, [evidenceId], toRemove);
      }
      onChange?.(nextIds);
    } catch (e) {
      console.error('entity link failed', e);
    }
  };

  const removeEntity = (ent) => {
    commitNext(entityIds.filter((id) => id !== ent.id));
  };

  return (
    <div className="relative">
      <div className="flex items-center gap-1 flex-wrap">
        {entityIds.map((id) => {
          const ent = entityMap[id];
          if (!ent) {
            return (
              <span
                key={id}
                className="text-[11px] px-2 py-0.5 rounded-full bg-light-100 text-light-500 border border-light-300"
              >
                …
              </span>
            );
          }
          return (
            <EntityChip
              key={id}
              entity={ent}
              onClick={() => setSelectedEntityId(id)}
              onRemove={() => removeEntity(ent)}
              size="xs"
            />
          );
        })}
        <button
          onClick={() => setPicking(!picking)}
          className="inline-flex items-center gap-0.5 text-[11px] text-owl-blue-600 hover:underline"
        >
          <Plus className="w-3 h-3" /> entity
        </button>
      </div>

      {picking && (
        <div ref={pickerWrapRef} className="absolute z-30 mt-1">
          <EntityPickerCombobox
            caseId={caseId}
            value={entityIds}
            onChange={commitNext}
            onClose={() => setPicking(false)}
            multi
          />
        </div>
      )}

      {selectedEntityId && (
        <EntityDetailDrawer
          caseId={caseId}
          entityId={selectedEntityId}
          onClose={() => setSelectedEntityId(null)}
        />
      )}
    </div>
  );
}
