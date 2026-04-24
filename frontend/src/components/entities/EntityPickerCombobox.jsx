import React, { useEffect, useMemo, useState } from 'react';
import { Search, Plus, Loader2, X } from 'lucide-react';
import { entitiesAPI } from '../../services/api';
import { entityMeta, entityColorClasses, ENTITY_TYPES } from './entityUtils';
import EntityEditorModal from './EntityEditorModal';

/**
 * Reusable entity picker combobox. Fetches entities for the case, filters by
 * free-text, and offers an inline "Create new" shortcut.
 *
 * Props:
 *   caseId
 *   value       — selected entity IDs (Array<string>)
 *   onChange    — (nextIds: string[]) => void
 *   multi       — allow multiple selections (default true)
 *   onClose     — close handler (for popover use)
 */
export default function EntityPickerCombobox({
  caseId,
  value = [],
  onChange,
  multi = true,
  onClose,
}) {
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const [typeFilter, setTypeFilter] = useState('all');

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setLoading(true);
    entitiesAPI
      .list(caseId, { limit: 500 })
      .then((d) => {
        if (!cancelled) {
          setEntities(d.entities || []);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setEntities([]);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return entities.filter((e) => {
      if (typeFilter !== 'all' && e.entity_type !== typeFilter) return false;
      if (!q) return true;
      if ((e.name || '').toLowerCase().includes(q)) return true;
      if ((e.description || '').toLowerCase().includes(q)) return true;
      if ((e.aliases || []).some((a) => a.toLowerCase().includes(q))) return true;
      return false;
    });
  }, [entities, query, typeFilter]);

  const selectedSet = useMemo(() => new Set(value || []), [value]);

  const toggle = (id) => {
    if (multi) {
      const next = new Set(selectedSet);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      onChange?.([...next]);
    } else {
      onChange?.([id]);
      onClose?.();
    }
  };

  const handleCreated = (newEnt) => {
    if (!newEnt) return;
    setEntities((prev) => [newEnt, ...prev]);
    if (onChange) {
      const next = new Set(selectedSet);
      next.add(newEnt.id);
      onChange([...next]);
    }
  };

  return (
    <div className="bg-white border border-light-200 rounded-lg shadow-lg w-80 overflow-hidden flex flex-col max-h-[60vh]">
      <div className="flex items-center gap-2 p-2 border-b border-light-200">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
          <input
            autoFocus
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find or create an entity…"
            className="w-full pl-7 pr-2 py-1 text-sm border border-light-300 rounded focus:outline-none focus:border-owl-blue-400"
          />
        </div>
        <button
          onClick={() => setCreating(true)}
          title="Create new entity"
          className="p-1.5 text-owl-blue-600 hover:bg-owl-blue-50 rounded"
        >
          <Plus className="w-4 h-4" />
        </button>
        {onClose && (
          <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Type filter */}
      <div className="flex items-center gap-1 px-2 py-1 border-b border-light-100 overflow-x-auto">
        <button
          onClick={() => setTypeFilter('all')}
          className={`text-[10px] px-2 py-0.5 rounded-full border ${
            typeFilter === 'all'
              ? 'bg-light-200 border-light-400 text-light-900'
              : 'bg-white border-light-300 text-light-500'
          }`}
        >
          All
        </button>
        {ENTITY_TYPES.map((t) => {
          const active = typeFilter === t.key;
          const cls = entityColorClasses(t.key);
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setTypeFilter(t.key)}
              className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border flex-shrink-0 ${
                active ? cls.pill : 'bg-white border-light-300 text-light-500'
              }`}
            >
              <Icon className="w-2.5 h-2.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="p-3 flex items-center justify-center text-light-400">
            <Loader2 className="w-4 h-4 animate-spin" />
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="p-3 text-xs text-light-500 italic text-center">
            No matching entities. Use + to create one.
          </div>
        )}
        {!loading &&
          filtered.map((ent) => {
            const meta = entityMeta(ent.entity_type);
            const Icon = meta.icon;
            const cls = entityColorClasses(ent.entity_type);
            const selected = selectedSet.has(ent.id);
            return (
              <button
                key={ent.id}
                onClick={() => toggle(ent.id)}
                className={`w-full flex items-center gap-2 px-2 py-1.5 text-left hover:bg-light-50 ${
                  selected ? cls.bgSoft : ''
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected}
                  readOnly
                  className="flex-shrink-0"
                />
                <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${cls.bg}`}>
                  <Icon className={`w-3 h-3 ${cls.icon}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-light-900 truncate">{ent.name}</div>
                  <div className="text-[10px] text-light-500 truncate">
                    {meta.label}
                    {ent.description ? ` · ${ent.description}` : ''}
                  </div>
                </div>
                {(ent.graph_node_count || ent.evidence_count) && (
                  <span className="text-[10px] text-light-500 flex-shrink-0">
                    {(ent.graph_node_count || 0) + (ent.evidence_count || 0)}
                  </span>
                )}
              </button>
            );
          })}
      </div>

      {creating && (
        <EntityEditorModal
          caseId={caseId}
          defaultType={typeFilter !== 'all' ? typeFilter : 'person'}
          onClose={() => setCreating(false)}
          onSaved={handleCreated}
        />
      )}
    </div>
  );
}
