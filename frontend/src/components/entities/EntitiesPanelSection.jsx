import React, { useEffect, useState } from 'react';
import { Users, Plus, ChevronRight, ChevronDown, Loader2, Maximize2 } from 'lucide-react';
import { entitiesAPI } from '../../services/api';
import { entityMeta, entityColorClasses } from './entityUtils';
import EntityEditorModal from './EntityEditorModal';
import EntityDetailDrawer from './EntityDetailDrawer';
import EntityListModal from './EntityListModal';

/**
 * Sidebar section listing the case's top entity profiles. Opens the detail
 * drawer on click and the full list modal via "View all".
 *
 * Props:
 *   caseId
 *   collapsed      — boolean
 *   onToggle       — (boolean) => void
 *   onFocus        — optional: () => void for section focus / "View all"
 */
export default function EntitiesPanelSection({ caseId, collapsed = false, onToggle }) {
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showList, setShowList] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState(null);

  const load = async () => {
    if (!caseId) return;
    setLoading(true);
    try {
      const data = await entitiesAPI.list(caseId, { limit: 50 });
      setEntities(data.entities || []);
    } catch {
      setEntities([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!collapsed) load();
  }, [caseId, collapsed]);

  const topTen = entities.slice(0, 10);
  const total = entities.length;

  return (
    <div className="border-b border-light-200">
      <button
        onClick={() => onToggle?.(!collapsed)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-light-50 text-left"
      >
        {collapsed ? (
          <ChevronRight className="w-3.5 h-3.5 text-light-500 flex-shrink-0" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-light-500 flex-shrink-0" />
        )}
        <Users className="w-4 h-4 text-owl-blue-700 flex-shrink-0" />
        <span className="text-sm font-semibold text-owl-blue-900 flex-1">
          Entities
          {total > 0 && (
            <span className="ml-1.5 text-xs text-light-500 font-normal">({total})</span>
          )}
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setCreating(true);
          }}
          className="p-0.5 text-owl-blue-600 hover:bg-owl-blue-50 rounded"
          title="Create new entity"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </button>

      {!collapsed && (
        <div className="px-3 pb-2">
          {loading ? (
            <div className="flex items-center justify-center py-3">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-light-400" />
            </div>
          ) : entities.length === 0 ? (
            <div className="text-xs text-light-500 italic py-2">
              No entities yet. Track people, addresses, events, devices and more.
            </div>
          ) : (
            <>
              <ul className="space-y-0.5">
                {topTen.map((ent) => {
                  const meta = entityMeta(ent.entity_type);
                  const cls = entityColorClasses(ent.entity_type);
                  const Icon = meta.icon;
                  const links = (ent.graph_node_count ?? 0) + (ent.evidence_count ?? 0);
                  return (
                    <li key={ent.id}>
                      <button
                        onClick={() => setSelectedEntityId(ent.id)}
                        className="w-full flex items-center gap-2 px-2 py-1 text-left hover:bg-light-50 rounded"
                        title={ent.description || ent.name}
                      >
                        <div
                          className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${cls.bg}`}
                        >
                          <Icon className={`w-2.5 h-2.5 ${cls.icon}`} />
                        </div>
                        <span className="text-xs font-medium text-light-900 truncate flex-1">
                          {ent.name}
                        </span>
                        {links > 0 && (
                          <span className="text-[10px] text-light-500">{links}</span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
              <button
                onClick={() => setShowList(true)}
                className="w-full mt-1 flex items-center justify-center gap-1 text-xs text-owl-blue-700 hover:bg-owl-blue-50 py-1 rounded"
              >
                <Maximize2 className="w-3 h-3" />
                View all
              </button>
            </>
          )}
        </div>
      )}

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

      {showList && (
        <EntityListModal caseId={caseId} onClose={() => { setShowList(false); load(); }} />
      )}

      {selectedEntityId && (
        <EntityDetailDrawer
          caseId={caseId}
          entityId={selectedEntityId}
          onClose={() => { setSelectedEntityId(null); load(); }}
          onEntityChanged={load}
        />
      )}
    </div>
  );
}
