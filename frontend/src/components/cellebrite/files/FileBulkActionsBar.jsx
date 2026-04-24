import React, { useState, useRef, useEffect } from 'react';
import { Tag, Users, CheckCircle2, Pin, Sparkles, X } from 'lucide-react';
import { evidenceTagsAPI, evidenceAPI, workspaceAPI } from '../../../services/api';
import EntityPickerCombobox from '../../entities/EntityPickerCombobox';

/**
 * Bulk action toolbar that appears when >=1 file is selected.
 *
 * Props:
 *   caseId
 *   selectedIds         — Set<string>
 *   caseTags            — [{tag, count}]
 *   onClear
 *   onChanged           — refresh trigger for the list
 */
export default function FileBulkActionsBar({
  caseId,
  selectedIds,
  caseTags = [],
  onClear,
  onChanged,
}) {
  const [showTagInput, setShowTagInput] = useState(false);
  const [tagInput, setTagInput] = useState('');
  const [showEntityPicker, setShowEntityPicker] = useState(false);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const entityWrap = useRef(null);
  const tagWrap = useRef(null);
  const count = selectedIds?.size || 0;

  useEffect(() => {
    if (!showEntityPicker && !showTagInput) return;
    const handler = (e) => {
      if (showEntityPicker && entityWrap.current && !entityWrap.current.contains(e.target)) {
        setShowEntityPicker(false);
      }
      if (showTagInput && tagWrap.current && !tagWrap.current.contains(e.target)) {
        setShowTagInput(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showEntityPicker, showTagInput]);

  if (count === 0) return null;

  const run = async (fn, successMsg) => {
    setStatus(null);
    setError(null);
    try {
      await fn();
      setStatus(successMsg);
      onChanged?.();
    } catch (e) {
      setError(e.message || 'Failed');
    }
  };

  const addTag = async () => {
    const t = tagInput.trim();
    if (!t) return;
    await run(
      () => evidenceTagsAPI.addTags(caseId, [...selectedIds], [t]),
      `Tagged ${count} with "${t}"`
    );
    setTagInput('');
    setShowTagInput(false);
  };

  const linkEntities = async (entityIds) => {
    await run(
      () => evidenceTagsAPI.linkEntities(caseId, [...selectedIds], entityIds),
      `Linked ${count} files to ${entityIds.length} entities`
    );
    setShowEntityPicker(false);
  };

  const markRelevant = async () => {
    await run(
      () => evidenceAPI.setRelevance([...selectedIds], true),
      `Marked ${count} relevant`
    );
  };

  const pinAll = async () => {
    const ids = [...selectedIds];
    await run(
      async () => {
        for (const id of ids) {
          try {
            await workspaceAPI.pinItem(caseId, 'evidence', id);
          } catch { /* ignore individual failures */ }
        }
      },
      `Pinned ${count} files`
    );
  };

  const processLLM = async () => {
    await run(
      () => evidenceAPI.process(caseId, [...selectedIds]),
      `LLM processing started on ${count} files`
    );
  };

  return (
    <div className="flex items-center gap-1 px-3 py-1.5 border-b border-light-200 bg-owl-blue-50 text-xs">
      <span className="font-semibold text-owl-blue-900 mr-1">{count} selected</span>

      <div ref={tagWrap} className="relative">
        <button
          onClick={() => setShowTagInput(!showTagInput)}
          className="flex items-center gap-1 px-2 py-1 rounded hover:bg-owl-blue-100 text-owl-blue-800"
        >
          <Tag className="w-3 h-3" /> Add tag
        </button>
        {showTagInput && (
          <div className="absolute top-full left-0 mt-1 bg-white border border-light-200 rounded shadow-lg p-2 z-20 w-64">
            <input
              autoFocus
              type="text"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') addTag();
                if (e.key === 'Escape') setShowTagInput(false);
              }}
              placeholder="New tag"
              className="w-full px-1.5 py-1 text-xs border border-light-300 rounded"
            />
            {caseTags.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {caseTags.slice(0, 12).map((t) => (
                  <button
                    key={t.tag}
                    onClick={() => {
                      setTagInput(t.tag);
                      setTimeout(() => addTag(), 0);
                    }}
                    className="px-1.5 py-0.5 text-[10px] rounded-full bg-amber-50 text-amber-700 border border-amber-200"
                  >
                    {t.tag} ({t.count})
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div ref={entityWrap} className="relative">
        <button
          onClick={() => setShowEntityPicker(!showEntityPicker)}
          className="flex items-center gap-1 px-2 py-1 rounded hover:bg-owl-blue-100 text-owl-blue-800"
        >
          <Users className="w-3 h-3" /> Link to entity
        </button>
        {showEntityPicker && (
          <div className="absolute top-full left-0 mt-1 z-20">
            <EntityPickerCombobox
              caseId={caseId}
              value={[]}
              onChange={linkEntities}
              onClose={() => setShowEntityPicker(false)}
              multi
            />
          </div>
        )}
      </div>

      <button
        onClick={markRelevant}
        className="flex items-center gap-1 px-2 py-1 rounded hover:bg-owl-blue-100 text-owl-blue-800"
      >
        <CheckCircle2 className="w-3 h-3" /> Mark relevant
      </button>
      <button
        onClick={pinAll}
        className="flex items-center gap-1 px-2 py-1 rounded hover:bg-owl-blue-100 text-owl-blue-800"
      >
        <Pin className="w-3 h-3" /> Pin
      </button>
      <button
        onClick={processLLM}
        className="flex items-center gap-1 px-2 py-1 rounded hover:bg-owl-blue-100 text-owl-blue-800"
      >
        <Sparkles className="w-3 h-3" /> LLM
      </button>

      <div className="flex-1" />
      {status && <span className="text-emerald-700">{status}</span>}
      {error && <span className="text-red-600">{error}</span>}
      <button onClick={onClear} className="p-0.5 text-light-500 hover:text-light-800" title="Clear selection">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
