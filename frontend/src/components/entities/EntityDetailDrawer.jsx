import React, { useEffect, useState } from 'react';
import { X, Edit2, Archive, Trash2, Loader2, MapPin, Mail, Phone, Tag } from 'lucide-react';
import { entitiesAPI } from '../../services/api';
import { entityMeta, entityColorClasses } from './entityUtils';
import EntityEditorModal from './EntityEditorModal';

const TABS = ['overview', 'linked', 'evidence', 'timeline'];

/**
 * Slide-in drawer: entity dossier with tabs.
 *
 * Props:
 *   caseId
 *   entityId
 *   onClose
 *   onEntityChanged — called after edit/archive/delete
 */
export default function EntityDetailDrawer({ caseId, entityId, onClose, onEntityChanged }) {
  const [context, setContext] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    if (!caseId || !entityId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await entitiesAPI.getContext(caseId, entityId);
      setContext(data);
    } catch (e) {
      setError(e.message || 'Failed to load entity');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [caseId, entityId]);

  // Esc closes
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleArchive = async () => {
    if (!confirm('Archive this entity?')) return;
    await entitiesAPI.archive(caseId, entityId);
    onEntityChanged?.();
    onClose?.();
  };

  const handleDelete = async () => {
    if (!confirm('Permanently delete this entity and its links? This cannot be undone.')) return;
    await entitiesAPI.delete(caseId, entityId);
    onEntityChanged?.();
    onClose?.();
  };

  const entity = context?.entity;
  const meta = entity ? entityMeta(entity.entity_type) : null;
  const cls = entity ? entityColorClasses(entity.entity_type) : null;
  const Icon = meta?.icon;

  return (
    <div className="fixed inset-y-0 right-0 w-[32vw] min-w-[420px] max-w-[640px] bg-white shadow-2xl border-l border-light-200 z-40 flex flex-col">
      {/* Header */}
      <div className={`flex items-center gap-2 px-4 py-3 border-b border-light-200 ${cls?.bgSoft || ''}`}>
        {Icon && (
          <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${cls?.bg}`}>
            <Icon className={`w-4 h-4 ${cls?.icon}`} />
          </div>
        )}
        <div className="flex-1 min-w-0">
          {entity && (
            <>
              <div className="text-sm font-semibold text-owl-blue-900 truncate">{entity.name}</div>
              <div className="text-[11px] text-light-600">
                {meta.label}
                {entity.status === 'archived' ? ' · archived' : ''}
              </div>
            </>
          )}
        </div>
        <button
          onClick={() => setEditing(true)}
          className="p-1 text-light-500 hover:text-owl-blue-700"
          title="Edit"
          disabled={!entity}
        >
          <Edit2 className="w-4 h-4" />
        </button>
        <button
          onClick={handleArchive}
          className="p-1 text-light-500 hover:text-amber-700"
          title="Archive"
          disabled={!entity}
        >
          <Archive className="w-4 h-4" />
        </button>
        <button
          onClick={handleDelete}
          className="p-1 text-light-500 hover:text-red-700"
          title="Delete"
          disabled={!entity}
        >
          <Trash2 className="w-4 h-4" />
        </button>
        <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800" title="Close (Esc)">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center border-b border-light-200 bg-light-50 px-3 flex-shrink-0">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
              activeTab === t
                ? 'border-owl-blue-500 text-owl-blue-700'
                : 'border-transparent text-light-600 hover:text-owl-blue-900'
            }`}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
        {context?.stats && (
          <div className="ml-auto text-[10px] text-light-500">
            {context.stats.graph_node_count} linked · {context.stats.evidence_count} evidence
          </div>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="p-6 flex items-center justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-light-400" />
          </div>
        )}
        {error && <div className="p-4 text-xs text-red-600">{error}</div>}
        {context && activeTab === 'overview' && <OverviewTab entity={context.entity} />}
        {context && activeTab === 'linked' && <LinkedNodesTab nodes={context.linked_graph_nodes || []} stats={context.stats} />}
        {context && activeTab === 'evidence' && <EvidenceTab evidence={context.linked_evidence || []} />}
        {context && activeTab === 'timeline' && <TimelineTab items={context.timeline || []} />}
      </div>

      {editing && (
        <EntityEditorModal
          caseId={caseId}
          entity={entity}
          onClose={() => setEditing(false)}
          onSaved={async () => {
            await load();
            onEntityChanged?.();
          }}
        />
      )}
    </div>
  );
}

function OverviewTab({ entity }) {
  if (!entity) return null;
  return (
    <div className="p-4 space-y-3 text-sm">
      {entity.description && (
        <Section title="Description">
          <p className="text-light-800 whitespace-pre-wrap">{entity.description}</p>
        </Section>
      )}
      {entity.notes && (
        <Section title="Notes">
          <p className="text-light-800 whitespace-pre-wrap">{entity.notes}</p>
        </Section>
      )}
      {(entity.aliases || []).length > 0 && (
        <Section title="Aliases">
          <div className="flex flex-wrap gap-1">
            {entity.aliases.map((a) => (
              <span key={a} className="px-2 py-0.5 text-[11px] bg-light-100 rounded-full text-light-700">
                {a}
              </span>
            ))}
          </div>
        </Section>
      )}
      {(entity.tags || []).length > 0 && (
        <Section title="Tags">
          <div className="flex flex-wrap gap-1">
            {entity.tags.map((t) => (
              <span
                key={t}
                className="flex items-center gap-1 px-2 py-0.5 text-[11px] bg-owl-blue-50 text-owl-blue-800 rounded-full"
              >
                <Tag className="w-2.5 h-2.5" />
                {t}
              </span>
            ))}
          </div>
        </Section>
      )}
      {(entity.phone_numbers || []).length > 0 && (
        <Section title="Phone numbers">
          <ul className="text-light-800 space-y-0.5">
            {entity.phone_numbers.map((p) => (
              <li key={p} className="flex items-center gap-1.5">
                <Phone className="w-3 h-3 text-light-500" /> {p}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {(entity.emails || []).length > 0 && (
        <Section title="Emails">
          <ul className="text-light-800 space-y-0.5">
            {entity.emails.map((e) => (
              <li key={e} className="flex items-center gap-1.5">
                <Mail className="w-3 h-3 text-light-500" /> {e}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {entity.address && (
        <Section title="Address">
          <p className="text-light-800 flex items-start gap-1.5">
            <MapPin className="w-3 h-3 text-light-500 mt-1 flex-shrink-0" />
            <span>
              {entity.address}
              {entity.coordinates_lat != null && entity.coordinates_lon != null && (
                <span className="text-[11px] text-light-500 block font-mono">
                  {Number(entity.coordinates_lat).toFixed(5)}, {Number(entity.coordinates_lon).toFixed(5)}
                </span>
              )}
            </span>
          </p>
        </Section>
      )}
      {entity.entity_type === 'device' && (entity.device_model || entity.imei) && (
        <Section title="Device">
          {entity.device_model && <div>Model: {entity.device_model}</div>}
          {entity.imei && <div>IMEI: {entity.imei}</div>}
        </Section>
      )}
      {entity.entity_type === 'vehicle' && (
        <Section title="Vehicle">
          {entity.registration && <div>Reg: {entity.registration}</div>}
          {(entity.vehicle_make || entity.vehicle_model) && (
            <div>
              {entity.vehicle_make} {entity.vehicle_model}
            </div>
          )}
          {entity.vehicle_color && <div>Colour: {entity.vehicle_color}</div>}
        </Section>
      )}
      <Section title="Metadata">
        <div className="text-[11px] text-light-500">
          Created {entity.created_at?.slice(0, 19) || ''}
          {entity.created_by ? ` by ${entity.created_by}` : ''}
        </div>
      </Section>
    </div>
  );
}

function LinkedNodesTab({ nodes, stats }) {
  if (!nodes.length) {
    return <div className="p-4 text-xs text-light-500 italic">No linked graph nodes yet.</div>;
  }
  // Group by label
  const byLabel = {};
  for (const n of nodes) {
    const l = n.label || 'Node';
    (byLabel[l] = byLabel[l] || []).push(n);
  }
  return (
    <div className="p-4 space-y-4">
      {Object.entries(byLabel).map(([label, items]) => (
        <div key={label}>
          <div className="text-xs font-semibold text-owl-blue-900 mb-1">
            {label} ({items.length})
          </div>
          <ul className="space-y-0.5">
            {items.map((n) => (
              <li key={n.key} className="text-xs text-light-800 flex gap-2">
                <span className="truncate flex-1">{n.name || n.key}</span>
                {n.timestamp && (
                  <span className="text-light-500 flex-shrink-0 text-[10px]">{n.timestamp.slice(0, 16)}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function EvidenceTab({ evidence }) {
  if (!evidence.length) {
    return <div className="p-4 text-xs text-light-500 italic">No evidence linked yet.</div>;
  }
  return (
    <div className="p-3 grid grid-cols-3 gap-2">
      {evidence.map((ev) => {
        const cat = (ev.cellebrite_category || '').toLowerCase();
        const url = ev.id ? `/api/evidence/${ev.id}/file` : null;
        return (
          <div
            key={ev.id}
            className="aspect-square border border-light-200 rounded overflow-hidden bg-light-50 flex items-center justify-center"
            title={ev.original_filename}
          >
            {cat === 'image' && url ? (
              <img src={url} alt={ev.original_filename} className="w-full h-full object-cover" loading="lazy" />
            ) : (
              <span className="text-[10px] text-light-600 p-2 text-center break-all">
                {ev.original_filename || ev.id}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function TimelineTab({ items }) {
  if (!items.length) {
    return <div className="p-4 text-xs text-light-500 italic">No timed links to plot.</div>;
  }
  return (
    <div className="p-3 space-y-2">
      {items.map((it) => (
        <div key={it.key} className="flex items-start gap-2 text-xs border-b border-light-100 pb-2">
          <span className="text-[10px] text-light-500 tabular-nums w-32 flex-shrink-0">
            {(it.timestamp || '').slice(0, 16)}
          </span>
          <div className="flex-1 min-w-0">
            <div className="font-medium text-light-900 truncate">{it.name || it.key}</div>
            <div className="text-[10px] text-light-500">
              {it.label}
              {it.source_app ? ` · ${it.source_app}` : ''}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-light-500 mb-1">{title}</div>
      {children}
    </div>
  );
}
