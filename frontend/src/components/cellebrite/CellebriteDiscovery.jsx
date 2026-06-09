import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Search, Loader2, AlertTriangle, X, ChevronRight, ChevronDown,
  ExternalLink, Network,
  Users, UserPlus, MessageSquare, Phone, Mail, MapPin, Radio, Wifi, Route,
  Globe, Bookmark, Boxes, Activity, Cookie, AtSign, KeyRound, Type, UserCog,
  CreditCard, Calendar, StickyNote, Share2, Download, Upload, MessagesSquare,
  Smartphone, Power, Cable, ScrollText, Footprints, Gauge, FileText,
} from 'lucide-react';
import { cellebriteAPI } from '../../services/api';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import { usePerspective } from '../../context/PerspectiveContext';
import { useCellebriteSelection } from './shared/CellebriteSelectionContext';
import {
  requestCellebriteTabSwitch, setCommsHandoff, setDiscoveryTarget,
} from '../../utils/commsHandoff';

/**
 * Search & Discovery — a DETAILED search engine across every phone in the
 * case AND every data type Cellebrite ingests (Epic 2A, rebuilt).
 *
 * The backend (GET /api/cellebrite/discovery/search) now scans ~32 node
 * labels and returns one labelled category per type, grouped into families,
 * each item carrying its own `detail` fields + deep-link identifiers. This
 * component:
 *   - searches on submit (Enter / button) — an all-types scan is heavy, so
 *     we don't fire it on every keystroke;
 *   - groups results by family with per-family show/hide chips;
 *   - lets every row EXPAND IN PLACE to read the full record (no tab hop);
 *   - and gives a working "open in native tab" deep-link that lands on the
 *     EXACT record pre-filtered (people→Comms participants, messages/emails→
 *     Comms thread deep-search, files→Files filename, places→Locations).
 */

// Family display order + accent colour.
const FAMILIES = [
  { key: 'People', color: '#245e8f' },
  { key: 'Communications', color: '#0f7b3f' },
  { key: 'Location', color: '#b45309' },
  { key: 'Web & Apps', color: '#6b21a8' },
  { key: 'Accounts & Security', color: '#b91c1c' },
  { key: 'Calendar & Notes', color: '#0e7490' },
  { key: 'Social & Media', color: '#be185d' },
  { key: 'Media & Files', color: '#1f6feb' },
  { key: 'Device & System', color: '#475569' },
];
const FAMILY_ORDER = FAMILIES.map((f) => f.key);
const FAMILY_COLOR = Object.fromEntries(FAMILIES.map((f) => [f.key, f.color]));

// Per-category icon. Unknown types fall back to Boxes.
const CATEGORY_ICON = {
  person: Users, contact: UserPlus,
  message: MessageSquare, call: Phone, email: Mail,
  location: MapPin, cell_tower: Radio, wifi: Wifi, journey: Route,
  web_visit: Globe, web_search: Search, bookmark: Bookmark,
  installed_app: Boxes, app_session: Activity, cookie: Cookie,
  account: AtSign, credential: KeyRound, autofill: Type,
  device_user: UserCog, sim: CreditCard,
  meeting: Calendar, note: StickyNote,
  social_media: Share2, file_download: Download, file_upload: Upload,
  chat_activity: MessagesSquare,
  device: Smartphone, device_event: Power, connectivity: Cable,
  log: ScrollText, motion: Footprints, network_usage: Gauge,
  dictionary_word: Type,
  file: FileText,
};

const PIVOT_LABEL = {
  comms: 'Open in Comms Center',
  locations: 'Open in Locations',
  files: 'Open in Files',
  graph: 'Show in Cross-Phone Graph',
};

// Build a clean, contiguous phrase from a message snippet so the Comms
// deep-search (substring match on the body) actually re-finds the thread.
function commsSeed(item) {
  // Prefer a subject (emails) — it matches the comms body/subject scan.
  const subj = (item.detail || []).find((d) => d.label === 'Subject');
  let text = subj ? String(subj.value) : String(item.title || '');
  text = text.replace(/…/g, ' ').trim();
  const toks = text.split(/\s+/).filter(Boolean);
  // Drop a likely-partial first/last token (snippets are cut mid-word).
  const core = toks.length > 3 ? toks.slice(1, -1) : toks;
  const seed = core.join(' ').slice(0, 60).trim();
  return seed || text.slice(0, 60);
}

function locationSeed(item) {
  const addr = (item.detail || []).find((d) => d.label === 'Address' || d.label === 'Place');
  return String((addr && addr.value) || item.title || '').slice(0, 80);
}

export default function CellebriteDiscovery({ caseId, isActive = true }) {
  const phoneCtx = usePhoneReports();
  const reports = phoneCtx?.reports || [];
  const selectedReportKeys = phoneCtx ? phoneCtx.selectedReportKeys : new Set();
  const allSelected = phoneCtx ? phoneCtx.allSelected : true;
  const perspective = usePerspective();
  const { selectEntity } = useCellebriteSelection();

  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [groups, setGroups] = useState(null); // null = no search yet
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hiddenFamilies, setHiddenFamilies] = useState(() => new Set());
  const [expanded, setExpanded] = useState(() => new Set());

  const inFlight = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (isActive && inputRef.current) inputRef.current.focus();
  }, [isActive]);

  // Real scope ONLY when the user has actively narrowed the phone selection.
  // The default state is "all phones selected" = search everything, which is
  // NOT a scope the user chose — so we must not show "scoped to N phones" or
  // pass report_keys then (that was the phantom "scoped to 6 phones" bug).
  const reportKeysArr = useMemo(() => {
    if (!phoneCtx || allSelected) return null;
    return selectedReportKeys && selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
  }, [phoneCtx, allSelected, selectedReportKeys]);

  const runSearch = useCallback((q) => {
    const term = (q ?? '').trim();
    if (!caseId || !term) {
      setGroups(null); setSubmittedQuery(''); setError(null);
      return;
    }
    if (inFlight.current) inFlight.current.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    setLoading(true);
    setError(null);
    setSubmittedQuery(term);
    setExpanded(new Set());
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

  // Family-grouped, in canonical order.
  const families = useMemo(() => {
    if (!groups) return [];
    const byFam = new Map();
    for (const g of groups) {
      const fam = g.family || 'Other';
      if (!byFam.has(fam)) byFam.set(fam, []);
      byFam.get(fam).push(g);
    }
    return [...byFam.entries()]
      .sort((a, b) =>
        ((FAMILY_ORDER.indexOf(a[0]) + 1) || 999) - ((FAMILY_ORDER.indexOf(b[0]) + 1) || 999))
      .map(([key, gs]) => ({
        key,
        groups: gs,
        total: gs.reduce((s, g) => s + (g.total || 0), 0),
      }));
  }, [groups]);

  const totalHits = useMemo(() => families.reduce((s, f) => s + f.total, 0), [families]);
  const visibleFamilies = families.filter((f) => !hiddenFamilies.has(f.key));

  const toggleFamily = (k) => setHiddenFamilies((prev) => {
    const n = new Set(prev);
    if (n.has(k)) n.delete(k); else n.add(k);
    return n;
  });
  const toggleExpand = (key) => setExpanded((prev) => {
    const n = new Set(prev);
    if (n.has(key)) n.delete(key); else n.add(key);
    return n;
  });

  // ---- Deep-links: land on the EXACT record, pre-filtered (S2-03) ----
  const openResult = useCallback((item) => {
    const pivot = item.pivot;
    if (pivot === 'comms') {
      const pk = (item.person_keys || []).filter(Boolean);
      if (pk.length) {
        // People → Comms filtered to those participants.
        if (perspective?.setPerspective) {
          perspective.setPerspective(pk, item.title || `${pk.length} people`, 'discovery.pivot');
        }
        selectEntity({
          type: 'name-action',
          id: `discovery-pivot-comms-${item.key}-${Date.now()}`,
          caseId,
          payload: { _filter_intent: 'comms', person_keys: pk },
          source: 'discovery.pivot',
        });
        const rks = reports.map((r) => r.report_key).filter(Boolean);
        setCommsHandoff({ caseId, startTs: null, endTs: null, reportKeys: rks, source: 'discovery.pivot' });
      } else {
        // Messages / emails → Comms deep-search seeds the thread open.
        const seed = commsSeed(item);
        if (seed) setDiscoveryTarget({ caseId, tab: 'comms', search: seed });
      }
      requestCellebriteTabSwitch('comms');
    } else if (pivot === 'locations') {
      setDiscoveryTarget({ caseId, tab: 'locations', search: locationSeed(item) });
      requestCellebriteTabSwitch('locations');
    } else if (pivot === 'files') {
      setDiscoveryTarget({ caseId, tab: 'files', search: item.title || '' });
      requestCellebriteTabSwitch('files');
    } else if (pivot === 'graph') {
      const pk = (item.person_keys || []).filter(Boolean);
      if (pk.length && perspective?.setPerspective) {
        perspective.setPerspective(pk, item.title || `${pk.length} people`, 'discovery.pivot');
      }
      requestCellebriteTabSwitch('graph');
    }
  }, [caseId, perspective, reports, selectEntity]);

  const showInGraph = useCallback((item) => {
    const pk = (item.person_keys || []).filter(Boolean);
    if (pk.length && perspective?.setPerspective) {
      perspective.setPerspective(pk, item.title || `${pk.length} people`, 'discovery.pivot');
    }
    requestCellebriteTabSwitch('graph');
  }, [perspective]);

  const hasResults = submittedQuery && !error && groups;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Search bar */}
      <div style={{ padding: '14px 18px', borderBottom: '1px solid #e3e8ee', background: '#fff' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ position: 'relative', flex: 1, maxWidth: 640 }}>
            <Search size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') runSearch(query); }}
              placeholder="Search every phone & every data type — names, numbers, messages, places, files, accounts…"
              style={{
                width: '100%', padding: '10px 36px 10px 36px', fontSize: 14,
                border: '1px solid #cbd5e1', borderRadius: 9, outline: 'none',
              }}
            />
            {query && (
              <button
                type="button"
                onClick={() => { setQuery(''); setGroups(null); setSubmittedQuery(''); setError(null); }}
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
          <button
            type="button"
            onClick={() => runSearch(query)}
            disabled={loading || !query.trim()}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '9px 16px', borderRadius: 9, fontSize: 13.5, fontWeight: 600,
              border: '1px solid #245e8f',
              background: loading || !query.trim() ? '#9db8cf' : '#245e8f',
              color: '#fff', cursor: loading || !query.trim() ? 'default' : 'pointer',
            }}
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
            Search
          </button>
          {reportKeysArr && (
            <span style={{ fontSize: 12, color: '#94a3b8' }}>
              · scoped to {reportKeysArr.length} of {reports.length} phones
            </span>
          )}
        </div>

        {/* Family filter chips — appear once there are results */}
        {hasResults && totalHits > 0 && (
          <div style={{ display: 'flex', gap: 7, marginTop: 11, flexWrap: 'wrap', alignItems: 'center' }}>
            {families.map((f) => {
              const on = !hiddenFamilies.has(f.key);
              const color = FAMILY_COLOR[f.key] || '#475569';
              return (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => toggleFamily(f.key)}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    padding: '4px 10px', borderRadius: 99, cursor: 'pointer', fontSize: 12.5,
                    border: `1px solid ${on ? color : '#e3e8ee'}`,
                    background: on ? `${color}12` : '#fff',
                    color: on ? color : '#94a3b8',
                  }}
                >
                  {f.key}
                  <span style={{ fontWeight: 700 }}>{f.total}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Results */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px', minHeight: 0 }}>
        {!submittedQuery && !loading && <EmptyHint />}

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

        {loading && !groups && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#64748b', fontSize: 14, padding: '24px 0' }}>
            <Loader2 size={18} className="animate-spin" style={{ color: '#245e8f' }} />
            Searching every phone and data type for <b>“{submittedQuery}”</b>…
          </div>
        )}

        {hasResults && totalHits === 0 && !loading && (
          <div style={{ color: '#64748b', fontSize: 14, padding: '24px 0', textAlign: 'center' }}>
            No matches for <b>“{submittedQuery}”</b>{reportKeysArr ? ' in the selected phones' : ' anywhere in the case'}.
          </div>
        )}

        {hasResults && totalHits > 0 && (
          <div style={{ fontSize: 12.5, color: '#94a3b8', marginBottom: 14 }}>
            {totalHits.toLocaleString()} matches across {families.length} {families.length === 1 ? 'category group' : 'category groups'} for <b style={{ color: '#475569' }}>“{submittedQuery}”</b>
          </div>
        )}

        {hasResults && visibleFamilies.map((fam) => (
          <div key={fam.key} style={{ marginBottom: 22 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
              paddingBottom: 6, borderBottom: `2px solid ${FAMILY_COLOR[fam.key] || '#e3e8ee'}33`,
            }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: FAMILY_COLOR[fam.key] || '#475569' }} />
              <span style={{ fontWeight: 700, fontSize: 13, letterSpacing: 0.3, textTransform: 'uppercase', color: FAMILY_COLOR[fam.key] || '#475569' }}>
                {fam.key}
              </span>
              <span style={{ fontSize: 12, color: '#94a3b8' }}>{fam.total}</span>
            </div>
            {fam.groups.map((g) => (
              <ResultGroup
                key={g.type}
                group={g}
                familyColor={FAMILY_COLOR[fam.key] || '#475569'}
                expanded={expanded}
                onToggleExpand={toggleExpand}
                onOpen={openResult}
                onShowInGraph={showInGraph}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyHint() {
  return (
    <div style={{ color: '#94a3b8', fontSize: 14, padding: '40px 0', textAlign: 'center', maxWidth: 560, margin: '0 auto' }}>
      <Search size={28} style={{ opacity: 0.4 }} />
      <div style={{ marginTop: 12, fontSize: 15, color: '#64748b', fontWeight: 600 }}>
        Search across every phone and every data type
      </div>
      <div style={{ marginTop: 6, lineHeight: 1.5 }}>
        Type a name, number, a phrase from a message, an address, a filename, an
        account, an app, a Wi-Fi SSID — then press <b>Enter</b>. Results are grouped
        by category; expand any row to read the full record in place, or open it in
        its native tab.
      </div>
    </div>
  );
}

function ResultGroup({ group, familyColor, expanded, onToggleExpand, onOpen, onShowInGraph }) {
  const Icon = CATEGORY_ICON[group.type] || Boxes;
  const items = group.items || [];
  const extra = (group.total || 0) - items.length;

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7, paddingLeft: 2 }}>
        <Icon size={14} style={{ color: familyColor }} />
        <span style={{ fontWeight: 600, fontSize: 13.5, color: '#1f2a37' }}>{group.label}</span>
        <span style={{ fontSize: 12, color: '#94a3b8' }}>{group.total || 0}</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {items.map((item, i) => (
          <ResultRow
            key={item.key || i}
            item={item}
            isExpanded={expanded.has(item.key || `${group.type}-${i}`)}
            rowKey={item.key || `${group.type}-${i}`}
            onToggle={onToggleExpand}
            onOpen={onOpen}
            onShowInGraph={onShowInGraph}
          />
        ))}
        {extra > 0 && (
          <div style={{ fontSize: 12.5, color: '#94a3b8', paddingLeft: 4, marginTop: 2 }}>
            +{extra.toLocaleString()} more — refine your search to narrow them down.
          </div>
        )}
      </div>
    </div>
  );
}

function ResultRow({ item, isExpanded, rowKey, onToggle, onOpen, onShowInGraph }) {
  const detail = item.detail || [];
  const canOpen = !!item.pivot;
  const graphable = (item.person_keys || []).filter(Boolean).length > 0 || item.pivot === 'graph';
  const subline = [item.subtitle, formatTs(item.timestamp)].filter(Boolean).join(' · ');

  return (
    <div style={{ border: '1px solid #eef2f7', borderRadius: 9, background: '#fff', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px' }}>
        <button
          type="button"
          onClick={() => onToggle(rowKey)}
          title={isExpanded ? 'Collapse' : 'Expand details'}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex', alignItems: 'center', flexShrink: 0 }}
        >
          {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        <button
          type="button"
          onClick={() => onToggle(rowKey)}
          style={{ flex: 1, minWidth: 0, textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >
          <div style={{ fontSize: 13.5, color: '#1f2a37', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {item.title}
          </div>
          {subline && (
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {subline}
            </div>
          )}
        </button>
        {graphable && (
          <button type="button" onClick={() => onShowInGraph(item)} title="Show in Cross-Phone Graph" style={iconBtn}>
            <Network size={14} />
          </button>
        )}
        {canOpen && (
          <button type="button" onClick={() => onOpen(item)} title={PIVOT_LABEL[item.pivot] || 'Open'} style={iconBtn}>
            <ExternalLink size={14} />
          </button>
        )}
      </div>

      {isExpanded && (
        <div style={{ borderTop: '1px solid #f1f5f9', background: '#fafcff', padding: '10px 12px 12px 33px' }}>
          {detail.length === 0 ? (
            <div style={{ fontSize: 12.5, color: '#94a3b8' }}>No additional fields recorded.</div>
          ) : (
            <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '4px 14px', margin: 0 }}>
              {detail.map((d, j) => (
                <React.Fragment key={j}>
                  <dt style={{ fontSize: 12, color: '#94a3b8', fontWeight: 600 }}>{d.label}</dt>
                  <dd style={{ fontSize: 12.5, color: '#334155', margin: 0, wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>
                    {String(d.value)}
                  </dd>
                </React.Fragment>
              ))}
            </dl>
          )}
          {(canOpen || graphable) && (
            <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
              {canOpen && (
                <button type="button" onClick={() => onOpen(item)} style={actionBtn}>
                  <ExternalLink size={13} /> {PIVOT_LABEL[item.pivot] || 'Open'}
                </button>
              )}
              {graphable && item.pivot !== 'graph' && (
                <button type="button" onClick={() => onShowInGraph(item)} style={actionBtnGhost}>
                  <Network size={13} /> Show in Graph
                </button>
              )}
              {item.report_key && (
                <span style={{ alignSelf: 'center', fontSize: 11.5, color: '#94a3b8' }}>
                  on {item.report_key}
                </span>
              )}
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

const actionBtn = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 12px', borderRadius: 7, border: '1px solid #245e8f',
  background: '#245e8f', color: '#fff', cursor: 'pointer', fontSize: 12.5, fontWeight: 600,
};

const actionBtnGhost = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 12px', borderRadius: 7, border: '1px solid #cbd5e1',
  background: '#fff', color: '#475569', cursor: 'pointer', fontSize: 12.5, fontWeight: 600,
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
