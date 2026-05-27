import React, { useState, useEffect, useMemo } from 'react';
import {
  Loader2, Search, ArrowUpDown, Smartphone, Users, ChevronRight,
  Home, X, Network, MessageSquare, MoreHorizontal,
} from 'lucide-react';
import { cellebriteAPI } from '../../services/api';
import CommsContactFeed from './comms/CommsContactFeed';
import NameActionMenu from './shared/NameActionMenu';
import PersonName from './shared/PersonName';
import { usePerspective } from '../../context/PerspectiveContext';
import { useCellebriteSelection } from './shared/CellebriteSelectionContext';
import { requestCellebriteTabSwitch } from '../../utils/commsHandoff';

/**
 * Communication analysis view with breadcrumbed drill-down.
 *
 * Root layer:
 *   - Contact frequency table (left) — every Person across every phone
 *     with their call/message/email counts.
 *   - Shared contacts panel (right) — Persons appearing on more than
 *     one phone.
 *
 * Drilled layers (one frame per click):
 *   - Replace the layout with a full-width breadcrumb header + the
 *     CommsContactFeed for that contact.
 *   - Names inside the feed are still clickable (NameActionMenu)
 *     so the investigator can keep stepping in: A → B → C → …
 *   - Breadcrumb crumbs are clickable to walk back to any prior step.
 *
 * Perspective:
 *   - Every drill ALSO pushes onto the global PerspectiveContext, so
 *     other tabs (Cross-Phone Graph, Comms Center, Timeline, etc.)
 *     can rebuild from the same lens via the PerspectivePill actions.
 */
export default function CellebriteCommunicationView({ caseId }) {
  const [data, setData] = useState({ contacts: [], shared_contacts: [] });
  const [loading, setLoading] = useState(true);
  // Track the real error so the user can see WHY the view is empty —
  // previously the .catch silently set data to empty and the UI just
  // showed "no contacts", which the user (correctly) reported as
  // "unknown error / nothing loads".
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortField, setSortField] = useState('call_count');
  const [sortDir, setSortDir] = useState('desc');

  // Drill stack — unlimited depth. Each entry is the contact row the
  // user clicked to enter that layer ({ person_key, name, phone, … }).
  // [] = root layer (frequency table); [...3 items] = three levels deep.
  const [drillStack, setDrillStack] = useState([]);

  // The perspective context mirrors the drill stack: every push here
  // also pushes a perspective frame so the rest of the app can rebuild
  // from the active person.
  const perspective = usePerspective();
  const { selectEntity } = useCellebriteSelection();

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setLoading(true);

    cellebriteAPI.getCommunicationNetwork(caseId).then(result => {
      if (!cancelled) {
        setData(result || { contacts: [], shared_contacts: [] });
        setError(null);
        setLoading(false);
      }
    }).catch((e) => {
      if (!cancelled) {
        setData({ contacts: [], shared_contacts: [] });
        console.error('[CellebriteCommunicationView] failed', e);
        setError(e?.message || String(e) || 'Failed to load contacts');
        setLoading(false);
      }
    });

    return () => { cancelled = true; };
  }, [caseId]);

  const filteredContacts = useMemo(() => {
    let list = data.contacts || [];
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      list = list.filter(c =>
        (c.name || '').toLowerCase().includes(term) ||
        (c.phone || '').includes(term) ||
        (c.person_key || '').toLowerCase().includes(term)
      );
    }
    list.sort((a, b) => {
      const aVal = a[sortField] || 0;
      const bVal = b[sortField] || 0;
      return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
    });
    return list;
  }, [data.contacts, searchTerm, sortField, sortDir]);

  const toggleSort = (field) => {
    if (sortField === field) {
      setSortDir(prev => prev === 'desc' ? 'asc' : 'desc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  /**
   * Drill into a contact: push a new layer locally AND a perspective
   * frame globally. The two stacks track each other for as long as
   * the user stays inside Communications.
   */
  const drillInto = (contact) => {
    if (!contact?.person_key) return;
    setDrillStack((prev) => [...prev, contact]);
    if (perspective) {
      perspective.pushFrame(
        [contact.person_key],
        contact.name || contact.person_key,
        'communications.drill',
      );
    }
  };

  /**
   * Walk back to a specific drill depth. depth=-1 returns to the root
   * (no contact opened). Pop the perspective stack to match so the
   * pill mirrors the breadcrumb the user actually sees.
   */
  const drillTo = (depth) => {
    if (depth < -1 || depth >= drillStack.length) return;
    setDrillStack((prev) => (depth < 0 ? [] : prev.slice(0, depth + 1)));
    if (perspective) {
      perspective.popToFrame(depth);
    }
  };

  /**
   * Re-anchor the perspective on the currently-drilled contact and
   * jump to the Cross-Phone Graph. Used by the "View Cross-Phone
   * Graph from this perspective" button on the drill toolbar.
   */
  const openInGraph = () => {
    if (drillStack.length === 0) return;
    const head = drillStack[drillStack.length - 1];
    if (perspective) {
      // setPerspective resets the stack to this single frame so the
      // graph rebuilds with a clean lens — drilling further afterward
      // re-pushes naturally.
      perspective.setPerspective([head.person_key], head.name || head.person_key, 'communications.open-graph');
    }
    requestCellebriteTabSwitch('graph');
  };

  /**
   * Filter the Comms Center by the active drill. Re-uses the existing
   * `_filter_intent: 'comms'` plumbing so the Comms Center seeds its
   * participants filter the same way it does for Overview drill-downs.
   */
  const openInComms = () => {
    if (drillStack.length === 0) return;
    const head = drillStack[drillStack.length - 1];
    if (perspective) {
      perspective.setPerspective([head.person_key], head.name || head.person_key, 'communications.open-comms');
    }
    selectEntity({
      type: 'name-action',
      id: `name-action-${head.person_key}-${Date.now()}`,
      caseId,
      payload: { _filter_intent: 'comms', person_keys: [head.person_key] },
      source: 'communications.drill',
    });
    requestCellebriteTabSwitch('comms');
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-light-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-sm text-red-700 gap-2">
        <div className="font-semibold">Couldn't load contacts</div>
        <div className="text-xs text-red-600 max-w-md text-center break-words">
          {error}
        </div>
        <div className="text-xs text-light-500">
          See the browser console for the full failure.
        </div>
      </div>
    );
  }

  // -------- Drilled layer -----------------------------------------
  if (drillStack.length > 0) {
    return (
      <div className="h-full flex flex-col min-h-0">
        <DrillBreadcrumbBar
          stack={drillStack}
          onDrillTo={drillTo}
          onOpenInGraph={openInGraph}
          onOpenInComms={openInComms}
        />
        <div className="flex-1 min-h-0">
          <CommsContactFeed
            caseId={caseId}
            contact={drillStack[drillStack.length - 1]}
            onDrillName={(personKey, name) => drillInto({ person_key: personKey, name })}
          />
        </div>
      </div>
    );
  }

  // -------- Root layer -----------------------------------------
  return (
    <div className="h-full flex min-h-0">
      {/* Left: Contact Frequency Table */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-light-200">
        {/* Search */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
            <input
              type="text"
              placeholder="Search contacts..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs border border-light-300 rounded bg-white focus:outline-none focus:ring-1 focus:ring-emerald-400"
            />
          </div>
          <span className="text-xs text-light-500 flex-shrink-0">
            {filteredContacts.length} contacts
          </span>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto min-h-0">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-light-50 z-10">
              <tr className="border-b border-light-200">
                <th className="text-left px-3 py-2 font-medium text-light-600">Contact</th>
                <SortHeader field="call_count" label="Calls" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                <SortHeader field="message_count" label="Messages" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                <SortHeader field="email_count" label="Emails" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                <th className="text-center px-3 py-2 font-medium text-light-600">Devices</th>
                <th className="text-center px-3 py-2 font-medium text-light-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredContacts.map((contact) => {
                return (
                  <tr
                    key={contact.person_key}
                    className="border-b border-light-100 cursor-pointer hover:bg-light-50 group"
                    onClick={() => drillInto(contact)}
                    title="Click to drill into this contact's communications"
                  >
                    <td className="px-3 py-2 font-medium text-owl-blue-900 max-w-[260px] truncate">
                      <PersonName
                        name={contact.name}
                        personKey={contact.person_key}
                        number={contact.phone}
                      />
                    </td>
                    <td className="px-3 py-2 text-center">
                      {contact.call_count > 0 && (
                        <span className="px-1.5 py-0.5 bg-green-50 text-green-700 rounded">
                          {contact.call_count}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {contact.message_count > 0 && (
                        <span className="px-1.5 py-0.5 bg-purple-50 text-purple-700 rounded">
                          {contact.message_count}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {contact.email_count > 0 && (
                        <span className="px-1.5 py-0.5 bg-red-50 text-red-700 rounded">
                          {contact.email_count}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className="inline-flex items-center gap-1 text-light-500">
                        <span>{(contact.devices || []).length}</span>
                        <ChevronRight className="w-3 h-3 text-light-300 group-hover:text-owl-blue-500 transition-colors" />
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center relative">
                      {/* Suppress row click on the action menu — the menu's
                          own buttons publish their own intents. */}
                      <span onClick={(e) => e.stopPropagation()}>
                        <NameActionMenu
                          personKey={contact.person_key}
                          name={contact.name}
                          onDrill={() => drillInto(contact)}
                          compact
                        />
                      </span>
                    </td>
                  </tr>
                );
              })}
              {filteredContacts.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-8 text-center text-light-400">
                    No contacts found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right: Shared Contacts */}
      <div className="w-80 flex-shrink-0 flex flex-col min-h-0 bg-light-50">
        <div className="px-4 py-2.5 border-b border-light-200 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-amber-500" />
            <h3 className="text-sm font-semibold text-owl-blue-900">
              Shared Contacts
            </h3>
            <span className="text-xs text-light-500 ml-auto">
              {(data.shared_contacts || []).length}
            </span>
          </div>
          <p className="text-[10px] text-light-500 mt-0.5">
            Contacts appearing on multiple devices
          </p>
        </div>

        <div className="flex-1 overflow-y-auto min-h-0 px-4 py-2 space-y-2">
          {(data.shared_contacts || []).length === 0 ? (
            <div className="text-xs text-light-400 text-center py-8">
              No shared contacts found.
              {data.contacts?.length > 0 && ' Contacts only appear on one device.'}
            </div>
          ) : (
            (data.shared_contacts || []).map(sc => (
              <div
                key={sc.person_key}
                className="p-2.5 bg-white rounded border border-light-200 hover:border-light-300 cursor-pointer transition-colors"
                onClick={() => {
                  const full = (data.contacts || []).find((c) => c.person_key === sc.person_key) || sc;
                  drillInto(full);
                }}
                title="Click to drill into this contact's communications"
              >
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 bg-amber-100 rounded-full flex items-center justify-center flex-shrink-0">
                    <Users className="w-3 h-3 text-amber-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <PersonName
                      name={sc.name}
                      personKey={sc.person_key}
                      number={sc.phone}
                      className="text-xs font-medium text-owl-blue-900 truncate block"
                      numberClassName="text-[10px]"
                    />
                  </div>
                  <span onClick={(e) => e.stopPropagation()}>
                    <NameActionMenu
                      personKey={sc.person_key}
                      name={sc.name}
                      onDrill={() => {
                        const full = (data.contacts || []).find((c) => c.person_key === sc.person_key) || sc;
                        drillInto(full);
                      }}
                      compact
                    />
                  </span>
                </div>
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {(sc.devices || []).map((dk, i) => (
                    <span
                      key={dk}
                      className="flex items-center gap-1 px-1.5 py-0.5 bg-amber-50 text-amber-700 text-[10px] rounded"
                    >
                      <Smartphone className="w-2.5 h-2.5" />
                      Device {i + 1}
                    </span>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Breadcrumb header rendered above the contact feed in any drilled
 * layer. Shows: All contacts > Sender Lemus > Jaime García > … with
 * each crumb clickable to walk back. Also surfaces the "open from
 * here" cross-tab actions on the active layer.
 */
function DrillBreadcrumbBar({ stack, onDrillTo, onOpenInGraph, onOpenInComms }) {
  const lastIdx = stack.length - 1;
  return (
    <div className="flex items-center gap-1 px-3 py-1.5 border-b border-light-200 bg-white flex-shrink-0">
      <nav className="flex items-center gap-1 flex-wrap min-w-0 flex-1" aria-label="Communications drill breadcrumb">
        <button
          type="button"
          onClick={() => onDrillTo(-1)}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[11px] text-light-700 hover:bg-light-100 rounded"
          title="Back to all contacts"
        >
          <Home className="w-3 h-3" />
          All contacts
        </button>
        {stack.map((c, idx) => {
          const isLast = idx === lastIdx;
          return (
            <React.Fragment key={`${c.person_key}-${idx}`}>
              <ChevronRight className="w-3 h-3 text-light-400" />
              <button
                type="button"
                onClick={() => onDrillTo(idx)}
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-[11px] rounded max-w-[200px] truncate ${
                  isLast
                    ? 'bg-owl-blue-100 text-owl-blue-900 font-semibold'
                    : 'text-light-700 hover:bg-light-100'
                }`}
                title={c.name || c.person_key}
              >
                <Users className="w-2.5 h-2.5" />
                <span className="truncate">{c.name || c.person_key}</span>
              </button>
            </React.Fragment>
          );
        })}
      </nav>

      {/* Cross-tab actions anchored to the head of the stack */}
      <div className="flex items-center gap-1 flex-shrink-0">
        <button
          type="button"
          onClick={onOpenInGraph}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded border border-light-300 bg-white hover:bg-light-50 text-light-700"
          title="View Cross-Phone Graph from this perspective"
        >
          <Network className="w-3 h-3" />
          In Graph
        </button>
        <button
          type="button"
          onClick={onOpenInComms}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded border border-light-300 bg-white hover:bg-light-50 text-light-700"
          title="Filter Comms Center by this perspective"
        >
          <MessageSquare className="w-3 h-3" />
          In Comms
        </button>
        <button
          type="button"
          onClick={() => onDrillTo(-1)}
          className="ml-1 inline-flex items-center justify-center w-5 h-5 rounded-full hover:bg-light-100 text-light-500"
          title="Close drill"
          aria-label="Close drill"
        >
          <X className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

function SortHeader({ field, label, sortField, sortDir, onSort }) {
  const active = sortField === field;
  return (
    <th
      className="text-center px-3 py-2 font-medium text-light-600 cursor-pointer hover:bg-light-100 select-none"
      onClick={() => onSort(field)}
    >
      <span className="inline-flex items-center gap-0.5">
        {label}
        <ArrowUpDown className={`w-3 h-3 ${active ? 'text-emerald-600' : 'text-light-300'}`} />
      </span>
    </th>
  );
}
