import React, { useEffect, useMemo, useState } from 'react';
import { X, Plus, Search, Loader2, Archive, ArchiveRestore } from 'lucide-react';
import { entitiesAPI } from '../../services/api';
import { ENTITY_TYPES, entityMeta, entityColorClasses } from './entityUtils';
import EntityEditorModal from './EntityEditorModal';
import EntityDetailDrawer from './EntityDetailDrawer';

/**
 * Full-screen list of all case entities with search, type filter, and create.
 *
 * Props:
 *   caseId
 *   onClose
 */
export default function EntityListModal({ caseId, onClose }) {
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('active');
  const [creating, setCreating] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState(null);

  const load = async () => {
    if (!caseId) return;
    setLoading(true);
    try {
      const data = await entitiesAPI.list(caseId, { status: statusFilter });
      setEntities(data.entities || []);
    } catch {
      setEntities([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [caseId, statusFilter]);

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

  return (
    <div className="fixed inset-0 bg-black/40 z-40 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h2 className="text-base font-semibold text-owl-blue-900">Case Entities</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCreating(true)}
              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-owl-blue-600 text-white rounded hover:bg-owl-blue-700"
            >
              <Plus className="w-3.5 h-3.5" />
              New
            </button>
            <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-light-200 bg-light-50 flex-wrap">
          <div className="relative flex-1 min-w-[240px] max-w-md">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, alias, description..."
              className="w-full pl-7 pr-2 py-1 text-sm border border-light-300 rounded focus:outline-none focus:border-owl-blue-400"
            />
          </div>

          <div className="flex items-center gap-1 flex-wrap">
            <button
              onClick={() => setTypeFilter('all')}
              className={`text-[11px] px-2 py-0.5 rounded-full border ${
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
                  className={`flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border ${
                    active ? cls.pill : 'bg-white border-light-300 text-light-500'
                  }`}
                >
                  <Icon className="w-3 h-3" />
                  {t.label}
                </button>
              );
            })}
          </div>

          <div className="ml-auto">
            <button
              onClick={() => setStatusFilter(statusFilter === 'active' ? 'archived' : 'active')}
              className="flex items-center gap-1 text-xs px-2 py-1 border border-light-300 rounded hover:bg-light-100"
            >
              {statusFilter === 'active' ? (
                <>
                  <Archive className="w-3 h-3" /> Showing active
                </>
              ) : (
                <>
                  <ArchiveRestore className="w-3 h-3" /> Showing archived
                </>
              )}
            </button>
          </div>
        </div>

        {/* Content grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="w-5 h-5 animate-spin text-light-400" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-10 text-sm text-light-500">
              {entities.length === 0
                ? 'No entities yet. Click "New" to create your first one.'
                : 'No entities match your filters.'}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {filtered.map((ent) => {
                const meta = entityMeta(ent.entity_type);
                const cls = entityColorClasses(ent.entity_type);
                const Icon = meta.icon;
                return (
                  <button
                    key={ent.id}
                    onClick={() => setSelectedEntityId(ent.id)}
                    className={`text-left border ${cls.border} rounded-lg p-3 hover:shadow-md transition-shadow bg-white`}
                  >
                    <div className="flex items-start gap-2 mb-1.5">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${cls.bg}`}>
                        <Icon className={`w-4 h-4 ${cls.icon}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-owl-blue-900 truncate">{ent.name}</div>
                        <div className="text-[10px] text-light-500">{meta.label}</div>
                      </div>
                    </div>
                    {ent.description && (
                      <p className="text-xs text-light-700 line-clamp-2 mb-1.5">{ent.description}</p>
                    )}
                    <div className="flex items-center gap-2 text-[10px] text-light-500">
                      <span>🔗 {ent.graph_node_count ?? 0} linked</span>
                      <span>📎 {ent.evidence_count ?? 0} evidence</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {creating && (
        <EntityEditorModal
          caseId={caseId}
          onClose={() => setCreating(false)}
          onSaved={(ent) => {
            setCreating(false);
            load();
            if (ent?.id) setSelectedEntityId(ent.id);
          }}
        />
      )}

      {selectedEntityId && (
        <EntityDetailDrawer
          caseId={caseId}
          entityId={selectedEntityId}
          onClose={() => setSelectedEntityId(null)}
          onEntityChanged={load}
        />
      )}
    </div>
  );
}
