import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Search, Loader2, Users, MessageSquare, MapPin, Boxes, FileText,
  ExternalLink, Network, AlertTriangle, X,
} from 'lucide-react';
import { cellebriteAPI } from '../../services/api';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import { usePerspective } from '../../context/PerspectiveContext';
import { useCellebriteSelection } from './shared/CellebriteSelectionContext';
import { requestCellebriteTabSwitch, setCommsHandoff } from '../../utils/commsHandoff';

/**
 * Search & Discovery center (Epic 2A — S2-01/02/03/04).
 *
 * The one place to search ACROSS every phone in the case AND every data
 * type at once — People, Messages, Locations, Other resources, and Files.
 * The other tabs each search their own slice; this is the unified entry
 * point Alex's call notes asked for.
 *
 * Results come back grouped by type (S2-02) from
 * GET /api/cellebrite/discovery/search. Each result pivots into its native
 * tab pre-filtered (S2-03) by reusing the existing perspective + selection
 * rail + tab-switch handoff (no new plumbing), and People/Locations can be
 * shown in the Cross-Phone Graph (S2-04) by handing the keys to the graph
 * search that already supports rebuild+frame+select.
 */

const TYPE_META = {
  person: { Icon: Users, color: '#245e8f' },
  message: { Icon: MessageSquare, color: '#0f7b3f' },
  location: { Icon: MapPin, color: '#b45309' },
  resource: { Icon: Boxes, color: '#6b21a8' },
  file: { Icon: FileText, color: '#475569' },
};

// All toggleable result types, in display order.
const ALL_TYPES = ['person', 'message', 'location', 'resource', 'file'];

export default function CellebriteDiscovery({ caseId, isActive = true }) {
  const phoneCtx = usePhoneReports();
  const reports = phoneCtx?.reports || [];
  const selectedReportKeys = phoneCtx ? phoneCtx.selectedReportKeys : new Set();
  const reportsReady = phoneCtx ? phoneCtx.hydrated : true;
  const perspective = usePerspective();
  const { selectEntity } = useCellebriteSelection();

  const [query, setQuery] = useState('');
  const [activeTypes, setActiveTypes] = useState(() => new Set(ALL_TYPES));
  const [groups, setGroups] = useState(null); // null = no search yet
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [submittedQuery, setSubmittedQuery] = useState('');

  const inFlight = useRef(null);
  const inputRef = useRef(null);

  // Focus the box when the tab becomes active — it's a search-first tab.
  useEffect(() => {
    if (isActive && inputRef.current) inputRef.current.focus();
  }, [isActive]);

  const reportKeysArr = useMemo(
    () => (selectedReportKeys && selectedReportKeys.size > 0 ? [...selectedReportKeys] : null),
    [selectedReportKeys],
  );

  const runSearch = useCallback((q) => {
    const term = (q ?? '').trim();
    if (!caseId || !term) {
      setGroups(null);
      setSubmittedQuery('');
      setError(null);
      return;
    }
    // Cancel any in-flight request so fast typers don't get stale results.
    if (inFlight.current) inFlight.current.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    setLoading(true);
    setError(null);
    setSubmittedQuery(term);
    cellebriteAPI.discoverySearch(caseId, term, {
      reportKeys: reportKeysArr,
      limitPerType: 10,
      signal: controller.signal,
    })
      .then((res) => {
        if (controller.signal.aborted) return;
        setGroups(Array.isArray(res?.groups) ? res.groups : []);
      })
      .catch((err) => {
        if (controller.signal.aborted || err?.name === 'AbortError') return;
        setError(err?.message || 'Search failed');
        setGroups([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [caseId, reportKeysArr]);

  // Debounce the search as the user types.
  useEffect(() => {
    if (!reportsReady) return undefined;
    const t = setTimeout(() => runSearch(query), 280);
    return () => clearTimeout(t);
  }, [query, runSearch, reportsReady]);

  const toggleType = (t) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) {
        if (next.size > 1) next.delete(t); // never empty
      } else {
        next.add(t);
      }
      return next;
    });
  };

  // --- Pivots (S2-03) — reuse the proven handoff used by the graph tab ---

  const pivotPeopleTo = useCallback((tabId, personKeys, label) => {
    const pk = (personKeys || []).filter(Boolean);
    if (pk.length && perspective?.setPerspective) {
      const cur = [...(perspective.activeKeys || [])].sort().join('|');
      const next = [...pk].sort().join('|');
      if (cur !== next) {
        perspective.setPerspective(pk, label || `${pk.length} people`, 'discovery.pivot');
      }
    }
    // Publish a filter intent so the Comms Center pre-fills its participants.
    selectEntity({
      type: 'name-action',
      id: `discovery-pivot-${tabId}-${Date.now()}`,
      caseId,
      payload: { _filter_intent: 'comms', person_keys: pk },
      source: 'discovery.pivot',
    });
    if (tabId === 'comms' || tabId === 'communications') {
      const rks = reports.map((rr) => rr.report_key).filter(Boolean);
      setCommsHandoff({ caseId, startTs: null, endTs: null, reportKeys: rks, source: 'discovery.pivot' });
    }
    requestCellebriteTabSwitch(tabId);
  }, [caseId, perspective, reports, selectEntity]);

  // Open a single result in the most useful native tab.
  const openResult = useCallback((type, item) => {
    switch (type) {
      case 'person':
        pivotPeopleTo('comms', item.person_keys || (item.key ? [item.key] : []), item.title);
        break;
      case 'message':
        // Carry the thread's participants if known; else just land in Comms.
        pivotPeopleTo('comms', item.person_keys || [], item.title);
        break;
      case 'location':
        requestCellebriteTabSwitch('events');
        break;
      case 'file':
        requestCellebriteTabSwitch('files');
        break;
      case 'resource':
      default:
        requestCellebriteTabSwitch('graph');
        break;
    }
  }, [pivotPeopleTo]);

  // Show a person/location/resource in the Cross-Phone Graph (S2-04).
  const showInGraph = useCallback((type, item) => {
    if (type === 'person' && (item.person_keys?.length || item.key)) {
      pivotPeopleTo('graph', item.person_keys || [item.key], item.title);
    } else {
      requestCellebriteTabSwitch('graph');
    }
  }, [pivotPeopleTo]);

  const visibleGroups = useMemo(() => {
    if (!groups) return [];
    return groups.filter((g) => activeTypes.has(g.type));
  }, [groups, activeTypes]);

  const totalHits = useMemo(
    () => visibleGroups.reduce((sum, g) => sum + (g.total || 0), 0),
    [visibleGroups],
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Search bar */}
      <div style={{ padding: '14px 18px', borderBottom: '1px solid #e3e8ee', background: '#fff' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ position: 'relative', flex: 1, maxWidth: 620 }}>
            <Search
              size={16}
              style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }}
            />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') runSearch(query); }}
              placeholder="Search every phone — people, messages, places, files…"
              style={{
                width: '100%', padding: '10px 36px 10px 36px', fontSize: 14,
                border: '1px solid #cbd5e1', borderRadius: 9, outline: 'none',
              }}
            />
            {query && (
              <button
                type="button"
                onClick={() => { setQuery(''); setGroups(null); setSubmittedQuery(''); }}
                style={{
                  position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8',
                  display: 'flex', alignItems: 'center',
                }}
                title="Clear"
              >
                <X size={15} />
              </button>
            )}
          </div>
          {loading && <Loader2 size={18} className="animate-spin" style={{ color: '#245e8f' }} />}
        </div>

        {/* Type toggles (S2-02) */}
        <div style={{ display: 'flex', gap: 7, marginTop: 11, flexWrap: 'wrap' }}>
          {ALL_TYPES.map((t) => {
            const meta = TYPE_META[t];
            const Icon = meta.Icon;
            const on = activeTypes.has(t);
            return (
              <button
                key={t}
                type="button"
                onClick={() => toggleType(t)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '4px 10px', borderRadius: 99, cursor: 'pointer',
                  fontSize: 12.5, textTransform: 'capitalize',
                  border: `1px solid ${on ? meta.color : '#e3e8ee'}`,
                  background: on ? `${meta.color}12` : '#fff',
                  color: on ? meta.color : '#94a3b8',
                }}
              >
                <Icon size={13} /> {t === 'resource' ? 'Other' : t}
              </button>
            );
          })}
          {reportKeysArr && (
            <span style={{ alignSelf: 'center', fontSize: 12, color: '#94a3b8', marginLeft: 4 }}>
              · scoped to {reportKeysArr.length} phone{reportKeysArr.length > 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Results */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px', minHeight: 0 }}>
        {!submittedQuery && (
          <EmptyHint />
        )}

        {error && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '12px 14px',
            background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 9, color: '#b91c1c',
          }}>
            <AlertTriangle size={16} /> {error}
            <button
              type="button"
              onClick={() => runSearch(submittedQuery || query)}
              style={{ marginLeft: 'auto', border: '1px solid #fecaca', background: '#fff', borderRadius: 7, padding: '4px 10px', cursor: 'pointer', fontSize: 12.5 }}
            >
              Retry
            </button>
          </div>
        )}

        {submittedQuery && !error && groups && totalHits === 0 && !loading && (
          <div style={{ color: '#64748b', fontSize: 14, padding: '24px 0', textAlign: 'center' }}>
            No matches for <b>“{submittedQuery}”</b>{reportKeysArr ? ' in the selected phones' : ''}.
          </div>
        )}

        {submittedQuery && !error && visibleGroups.map((g) => (
          <ResultGroup
            key={g.type}
            group={g}
            onOpen={(item) => openResult(g.type, item)}
            onShowInGraph={(item) => showInGraph(g.type, item)}
          />
        ))}
      </div>
    </div>
  );
}

function EmptyHint() {
  return (
    <div style={{ color: '#94a3b8', fontSize: 14, padding: '40px 0', textAlign: 'center', maxWidth: 520, margin: '0 auto' }}>
      <Search size={28} style={{ opacity: 0.4 }} />
      <div style={{ marginTop: 12, fontSize: 15, color: '#64748b', fontWeight: 600 }}>
        Search across every phone at once
      </div>
      <div style={{ marginTop: 6, lineHeight: 1.5 }}>
        Type a name, number, a phrase from a message, an address, or a filename.
        Results are grouped by type — open any one in its tab, or show people and
        places in the graph.
      </div>
    </div>
  );
}

function ResultGroup({ group, onOpen, onShowInGraph }) {
  const meta = TYPE_META[group.type] || TYPE_META.resource;
  const Icon = meta.Icon;
  const items = group.items || [];
  const extra = (group.total || 0) - items.length;

  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon size={15} style={{ color: meta.color }} />
        <span style={{ fontWeight: 600, fontSize: 14, color: '#1f2a37' }}>{group.label}</span>
        <span style={{ fontSize: 12.5, color: '#94a3b8' }}>{group.total || 0}</span>
      </div>

      {items.length === 0 ? (
        <div style={{ fontSize: 13, color: '#cbd5e1', paddingLeft: 23 }}>no matches</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {items.map((item, i) => (
            <div
              key={item.key || i}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '9px 12px', border: '1px solid #eef2f7', borderRadius: 9,
                background: '#fff',
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 13.5, color: '#1f2a37', whiteSpace: 'nowrap',
                  overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {item.title}
                </div>
                {(item.subtitle || item.timestamp) && (
                  <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
                    {[item.subtitle, formatTs(item.timestamp)].filter(Boolean).join(' · ')}
                  </div>
                )}
              </div>
              {(group.type === 'person' || group.type === 'location' || group.type === 'resource') && (
                <button
                  type="button"
                  onClick={() => onShowInGraph(item)}
                  title="Show in graph"
                  style={iconBtn}
                >
                  <Network size={14} />
                </button>
              )}
              <button
                type="button"
                onClick={() => onOpen(item)}
                title="Open"
                style={iconBtn}
              >
                <ExternalLink size={14} />
              </button>
            </div>
          ))}
          {extra > 0 && (
            <div style={{ fontSize: 12.5, color: '#94a3b8', paddingLeft: 4, marginTop: 2 }}>
              +{extra} more — refine your search to narrow them down.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const iconBtn = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  width: 30, height: 30, borderRadius: 7, border: '1px solid #e3e8ee',
  background: '#fff', cursor: 'pointer', color: '#475569', flexShrink: 0,
};

function formatTs(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleString();
  } catch {
    return '';
  }
}
