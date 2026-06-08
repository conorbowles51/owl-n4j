import React, { useMemo, useState } from 'react';
import {
  User, Smartphone, MapPin, Globe, Wifi, Radio, Users as UsersIcon,
  Mail, Phone, MessageSquare, Bookmark, Key, ShieldCheck, DollarSign,
  Bluetooth, Search as SearchIcon, ChevronRight, ChevronDown,
} from 'lucide-react';
import PhoneIdentityChip from '../PhoneIdentityChip';
import PersonName from '../PersonName';
import { useCellebriteSelection } from '../CellebriteSelectionContext';
import { usePerspective } from '../../../../context/PerspectiveContext';

/**
 * Rail accordion for Cross-Phone Graph selections.
 *
 * Two shapes of selection feed in here:
 *   - graph-selection : a multi-node pick (rubber-band) carrying
 *                       `nodes: [...]` plus per-type counts. The
 *                       accordion renders one info card per node.
 *   - person | phone-report | resource : a single node, but routed
 *                       here too so we use the same rich card layout
 *                       instead of the GenericAccordion key/value
 *                       table.
 *
 * Each card surfaces the meaningful fields the graph already carries
 * (no extra backend fetch) plus a "Drill" button that re-publishes
 * the single node so other surfaces can hook in.
 */
export default function GraphSelectionAccordion({ selection }) {
  const { selectEntity } = useCellebriteSelection();
  const perspective = usePerspective();
  const payload = selection?.payload || {};

  // Drill = re-anchor the graph on this node. For a Person that means
  // setting the perspective (which rebuilds the Cross-Phone Graph around
  // them) — that's the part that was missing, so the button looked dead.
  // We still republish the single node to the selection rail so other
  // surfaces stay in sync. Phones/resources can't anchor a person
  // perspective, so they just republish.
  const handleDrill = (node) => {
    if (!node) return;
    const kind = inferKind(node);
    if (kind === 'person' && perspective?.setPerspective) {
      const personKey =
        node.person_key
        || node.node_key
        || (typeof node.id === 'string' ? node.id.replace(/^person-/, '') : null);
      if (personKey) {
        perspective.setPerspective([personKey], node.name || personKey, 'graph.drill');
      }
    }
    publishSingle(selectEntity, node, selection?.caseId);
  };

  // Normalise to a list of nodes regardless of which selection shape
  // we received. Single-node selections fake a list of one so the
  // same render path serves both cases.
  const nodes = useMemo(() => {
    if (Array.isArray(payload.nodes) && payload.nodes.length > 0) {
      return payload.nodes;
    }
    // Single-node selection: synthesise a one-item list from the
    // top-level payload fields.
    if (selection?.type === 'person'
        || selection?.type === 'phone-report'
        || selection?.type === 'resource') {
      return [payload];
    }
    return [];
  }, [payload, selection]);

  // Buckets for the per-group header counts at the top.
  const buckets = useMemo(() => {
    const persons = [];
    const phones = [];
    const resources = [];
    for (const n of nodes) {
      if (n.type === 'phone-report' || n.kind === 'phone-report') phones.push(n);
      else if (n.type === 'resource' || n.kind === 'resource') resources.push(n);
      else persons.push(n);
    }
    return { persons, phones, resources };
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <div className="px-3 py-4 text-xs text-light-500 italic">
        Nothing selected.
      </div>
    );
  }

  // Single-node view → render just the card body (no header bar)
  if (nodes.length === 1) {
    return (
      <div className="px-2 py-2">
        <NodeCard node={nodes[0]} onDrill={handleDrill} />
      </div>
    );
  }

  return (
    <div className="px-2 py-2 space-y-2">
      <div className="px-1 pb-1 text-[11px] text-light-600 flex items-center gap-3 flex-wrap">
        <span className="font-semibold text-owl-blue-900">
          {nodes.length} selected
        </span>
        {buckets.persons.length > 0 && (
          <span><User className="inline w-3 h-3 mr-1" />{buckets.persons.length} {buckets.persons.length === 1 ? 'person' : 'people'}</span>
        )}
        {buckets.phones.length > 0 && (
          <span><Smartphone className="inline w-3 h-3 mr-1" />{buckets.phones.length} phone{buckets.phones.length === 1 ? '' : 's'}</span>
        )}
        {buckets.resources.length > 0 && (
          <span>{buckets.resources.length} resource{buckets.resources.length === 1 ? '' : 's'}</span>
        )}
      </div>

      {buckets.persons.length > 0 && (
        <Section title="People" icon={User} initialOpen>
          {buckets.persons.map((n) => (
            <NodeCard
              key={n.id || n.node_key || n.name}
              node={n}
              onDrill={handleDrill}
            />
          ))}
        </Section>
      )}

      {buckets.phones.length > 0 && (
        <Section title="Phones" icon={Smartphone} initialOpen>
          {buckets.phones.map((n) => (
            <NodeCard
              key={n.id || n.node_key || n.name}
              node={n}
              onDrill={handleDrill}
            />
          ))}
        </Section>
      )}

      {buckets.resources.length > 0 && (
        <Section title="Resources" icon={Globe} initialOpen>
          {buckets.resources.map((n) => (
            <NodeCard
              key={n.id || n.node_key || n.name}
              node={n}
              onDrill={handleDrill}
            />
          ))}
        </Section>
      )}
    </div>
  );
}

/* ────────────────────── Sub-components ────────────────────── */

function Section({ title, icon: Icon, children, initialOpen = false }) {
  const [open, setOpen] = useState(initialOpen);
  return (
    <div className="border border-light-200 rounded">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 text-[11px] text-light-700 hover:bg-light-50"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Icon className="w-3 h-3" />
        <span className="font-semibold uppercase tracking-wide">{title}</span>
        <span className="ml-auto text-light-400">
          {React.Children.count(children)}
        </span>
      </button>
      {open && <div className="px-2 pb-2 space-y-1.5">{children}</div>}
    </div>
  );
}

/**
 * NodeCard — one rich info card for a single graph node.
 *
 * Surfaces the data the graph node already carries (no extra fetch
 * required). Layout adapts to the node type so a Person card looks
 * meaningfully different from a Resource card.
 */
function NodeCard({ node, onDrill }) {
  if (!node) return null;
  const kind = inferKind(node);
  if (kind === 'phone') return <PhoneCard node={node} onDrill={onDrill} />;
  if (kind === 'resource') return <ResourceCard node={node} onDrill={onDrill} />;
  return <PersonCard node={node} onDrill={onDrill} />;
}

function PersonCard({ node, onDrill }) {
  return (
    <div className="border border-light-200 rounded bg-white px-2.5 py-2">
      <div className="flex items-center gap-2">
        <User className="w-3.5 h-3.5 text-owl-blue-600 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <PersonName
            name={node.name}
            personKey={node.person_key || node.node_key}
            number={node.phone}
            className="text-[12px] font-semibold text-owl-blue-900 truncate block"
            numberClassName="text-[10px]"
          />
          <div className="text-[10px] text-light-500 truncate flex items-center gap-1.5 flex-wrap">
            {node.device_count > 1 && (
              <span className="text-amber-700">
                <Smartphone className="inline w-2.5 h-2.5 mr-0.5" />
                on {node.device_count} phones
              </span>
            )}
            {node.shared && (
              <span className="text-amber-700">shared contact</span>
            )}
          </div>
        </div>
        {onDrill && (
          <button
            type="button"
            onClick={() => onDrill({ ...node, _drill: true })}
            className="text-[10px] text-owl-blue-600 hover:text-owl-blue-800 underline whitespace-nowrap"
            title="Re-anchor the graph on this person"
          >
            Drill
          </button>
        )}
      </div>

      {/* Activity counts — derived from the graph node's comm_count
          aggregate. We surface it as a simple chip strip since the
          full per-type breakdown isn't on the node itself. */}
      {Number(node.comm_count) > 0 && (
        <div className="mt-1.5 text-[10px] text-light-700 flex items-center gap-1.5">
          <MessageSquare className="w-2.5 h-2.5 text-light-500" />
          <span>{Number(node.comm_count).toLocaleString()} activity points</span>
        </div>
      )}

      {/* Phone identity badges — one chip per phone this Person
          touches. report_keys is set on multi-phone Persons; falls
          back to the single report_key the rest of the time. */}
      <PhoneStrip node={node} />
    </div>
  );
}

function PhoneCard({ node, onDrill }) {
  const name = node.name || node.device_model || node.reportKey || node.node_key || 'Phone';
  return (
    <div className="border border-light-200 rounded bg-white px-2.5 py-2">
      <div className="flex items-center gap-2">
        <Smartphone className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-[12px] font-semibold text-owl-blue-900 truncate">
            {name}
          </div>
          {node.phone_owner && (
            <div className="text-[10px] text-light-500 truncate">
              Owner: {node.phone_owner}
            </div>
          )}
        </div>
        <PhoneIdentityChip reportKey={node.reportKey || node.report_key} variant="dense" />
      </div>
    </div>
  );
}

function ResourceCard({ node, onDrill }) {
  const meta = RESOURCE_META[node.resource_type] || RESOURCE_META.default;
  const Icon = meta.icon;
  const name = node.name || node.bucket || node.node_key || meta.label;
  return (
    <div className="border border-light-200 rounded bg-white px-2.5 py-2">
      <div className="flex items-center gap-2">
        <Icon className="w-3.5 h-3.5 flex-shrink-0" style={{ color: meta.color }} />
        <div className="flex-1 min-w-0">
          <div className="text-[12px] font-semibold text-owl-blue-900 truncate" title={name}>
            {name}
          </div>
          <div className="text-[10px] text-light-500 truncate flex items-center gap-1.5 flex-wrap">
            <span style={{ color: meta.color }}>{meta.label}</span>
            {Number(node.hits) > 0 && (
              <span>· {Number(node.hits).toLocaleString()} occurrence{Number(node.hits) === 1 ? '' : 's'}</span>
            )}
            {Number(node.phone_count) > 1 && (
              <span className="text-amber-700">· shared across {node.phone_count} phones</span>
            )}
          </div>
        </div>
        {onDrill && (
          <button
            type="button"
            onClick={() => onDrill({ ...node, _drill: true })}
            className="text-[10px] text-owl-blue-600 hover:text-owl-blue-800 underline whitespace-nowrap"
            title="Centre the graph on this resource"
          >
            Focus
          </button>
        )}
      </div>

      {/* Owning phones */}
      {Array.isArray(node.phone_report_keys) && node.phone_report_keys.length > 0 && (
        <div className="mt-1.5 flex items-center gap-1 flex-wrap">
          <span className="text-[10px] text-light-500">On:</span>
          {node.phone_report_keys.map((rk) => (
            <PhoneIdentityChip key={rk} reportKey={rk} variant="dense" />
          ))}
        </div>
      )}
    </div>
  );
}

function PhoneStrip({ node }) {
  const keys = Array.isArray(node.report_keys)
    ? node.report_keys
    : (node.reportKey ? [node.reportKey] : (node.report_key ? [node.report_key] : []));
  if (keys.length === 0) return null;
  return (
    <div className="mt-1.5 flex items-center gap-1 flex-wrap">
      <span className="text-[10px] text-light-500">On:</span>
      {keys.map((rk) => (
        <PhoneIdentityChip key={rk} reportKey={rk} variant="dense" />
      ))}
    </div>
  );
}

/* ────────────────────── Helpers ────────────────────── */

const RESOURCE_META = {
  location:   { icon: MapPin,      color: '#06b6d4', label: 'Location' },
  wifi:       { icon: Wifi,        color: '#22c55e', label: 'WiFi' },
  cell_tower: { icon: Radio,       color: '#8b5cf6', label: 'Cell tower' },
  meeting:    { icon: UsersIcon,   color: '#f97316', label: 'Meeting' },
  visit:      { icon: Globe,       color: '#a855f7', label: 'Web domain' },
  search:     { icon: SearchIcon,  color: '#ec4899', label: 'Search' },
  bookmark:   { icon: Bookmark,    color: '#d946ef', label: 'Bookmark' },
  account:    { icon: ShieldCheck, color: '#0ea5e9', label: 'Account' },
  credential: { icon: Key,         color: '#eab308', label: 'Credential' },
  financial:  { icon: DollarSign,  color: '#16a34a', label: 'Financial' },
  pairing:    { icon: Bluetooth,   color: '#6366f1', label: 'Pairing' },
  default:    { icon: Mail,        color: '#64748b', label: 'Item' },
};

function inferKind(node) {
  // 'kind' wins (set by the graph payload builder); fall back to
  // type strings the rail might use; default to 'person'.
  if (node.kind === 'phone-report' || node.type === 'PhoneReport'
      || node.type === 'phone-report') return 'phone';
  if (node.kind === 'resource' || node.type === 'Resource'
      || node.type === 'resource') return 'resource';
  return 'person';
}

/**
 * Re-publish a node as a single-item selection so the rail's
 * existing routing picks it up. The "Drill" / "Focus" affordance.
 */
function publishSingle(selectEntity, node, caseId) {
  if (!selectEntity || !node) return;
  const kind = inferKind(node);
  const type = kind === 'phone' ? 'phone-report'
    : kind === 'resource' ? 'resource'
    : 'person';
  selectEntity({
    type,
    id: node.id || node.node_key,
    caseId,
    reportKey: node.reportKey || node.report_key || null,
    payload: { ...node, _drill: true },
    source: 'graph.selection.drill',
  });
}
