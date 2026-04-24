import React, { useEffect, useState, useRef } from 'react';
import { Plus, X, Tag as TagIcon } from 'lucide-react';
import { evidenceTagsAPI } from '../../../services/api';

/**
 * Inline chip editor for a file's tags, with autocomplete from case-wide tags.
 *
 * Props:
 *   caseId
 *   evidenceId
 *   tags            — current tags
 *   onChange        — (tags) => void
 *   caseTags        — optional array of {tag, count} for autocomplete
 */
export default function FileTagEditor({
  caseId,
  evidenceId,
  tags = [],
  onChange,
  caseTags = [],
}) {
  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const commit = async (next) => {
    try {
      await evidenceTagsAPI.setTags(caseId, evidenceId, next);
      onChange?.(next);
    } catch (e) {
      console.error('tag set failed', e);
    }
  };

  const addTag = async (raw) => {
    const t = (raw || '').trim();
    if (!t) return;
    if (tags.includes(t)) return;
    const next = [...tags, t].sort();
    setInput('');
    await commit(next);
  };

  const removeTag = async (t) => {
    const next = tags.filter((x) => x !== t);
    await commit(next);
  };

  const suggestions = caseTags
    .filter((c) => !tags.includes(c.tag))
    .filter((c) => !input || c.tag.toLowerCase().includes(input.toLowerCase()))
    .slice(0, 6);

  return (
    <div>
      <div className="flex items-center gap-1 flex-wrap">
        {tags.map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded-full bg-amber-100 text-amber-800 border border-amber-300"
          >
            <TagIcon className="w-2.5 h-2.5" />
            {t}
            <button
              onClick={() => removeTag(t)}
              className="opacity-70 hover:opacity-100"
              title={`Remove "${t}"`}
            >
              <X className="w-2.5 h-2.5" />
            </button>
          </span>
        ))}
        {editing ? (
          <div className="relative">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addTag(input);
                } else if (e.key === 'Escape') {
                  setEditing(false);
                  setInput('');
                }
              }}
              onBlur={() => {
                // Delay so the suggestion click can register
                setTimeout(() => setEditing(false), 150);
              }}
              placeholder="Add tag"
              className="px-1.5 py-0.5 text-[11px] border border-light-300 rounded"
            />
            {suggestions.length > 0 && (
              <div className="absolute top-full left-0 mt-0.5 bg-white border border-light-200 rounded shadow-lg z-10 min-w-[120px]">
                {suggestions.map((s) => (
                  <button
                    key={s.tag}
                    onMouseDown={() => addTag(s.tag)}
                    className="block w-full text-left px-2 py-1 text-[11px] hover:bg-light-100"
                  >
                    {s.tag}
                    <span className="text-light-400 ml-1">({s.count})</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="inline-flex items-center gap-0.5 text-[11px] text-owl-blue-600 hover:underline"
          >
            <Plus className="w-3 h-3" /> tag
          </button>
        )}
      </div>
    </div>
  );
}
