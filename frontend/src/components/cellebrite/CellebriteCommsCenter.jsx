import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, BookOpen, SlidersHorizontal, Activity, X } from 'lucide-react';
import { cellebriteCommsAPI } from '../../services/api';
import PhoneSelector from './shared/PhoneSelector';
import NoPhonesSelectedEmptyState from './shared/NoPhonesSelectedEmptyState';
import CommsParticipantsFilter from './comms/CommsParticipantsFilter';
import CommsCompactToolbar from './comms/CommsCompactToolbar';
import CommsThreadList from './comms/CommsThreadList';
import CommsThreadView from './comms/CommsThreadView';
import CommsCrossTypeTimeline from './comms/CommsCrossTypeTimeline';
import CellebriteSearchInput from './shared/CellebriteSearchInput';
import ResizableSplit from './shared/ResizableSplit';
import { useChatContext } from '../../contexts/ChatContext';
import { buildCommsContext } from '../../utils/chatContextSummary';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import { parseQuery, matchItem } from '../../utils/cellebriteSearch';
import { useCellebriteStatus } from './shared/CellebriteStatusBar';
import { useCellebriteSelection } from './shared/CellebriteSelectionContext';

/**
 * Cellebrite Communication Center — the hybrid dashboard orchestrator.
 *
 * The phone selection is owned by PhoneReportsContext so it persists
 * across tabs and across page refreshes. The `reports` prop is kept
 * for backwards compatibility with callers that pass an explicit list,
 * but when the context is available it is the source of truth.
 */
export default function CellebriteCommsCenter({ caseId, reports: reportsProp = [], isActive = true }) {
  const phoneCtx = usePhoneReports();
  const fallbackReports = useMemo(() => reportsProp || [], [reportsProp]);
  const fallbackSelection = useMemo(
    () => new Set(fallbackReports.map(r => r.report_key)),
    [fallbackReports],
  );
  const reports = phoneCtx?.reports?.length ? phoneCtx.reports : fallbackReports;
  const selectedReportKeys = phoneCtx ? phoneCtx.selectedReportKeys : fallbackSelection;
  // When the context is the source of truth, wait for it to finish
  // hydrating before firing any per-tab fetches. Without this, every
  // effect downstream runs once with an empty selection (fast no-op
  // server response), then re-runs the moment hydration completes,
  // doubling every Comms API call on case open. When we're operating
  // off the explicit reports prop instead (legacy callers), there's
  // nothing to wait for.
  const reportsReady = phoneCtx ? phoneCtx.hydrated : true;
  // Phase K1 — Participants combined filter. Each entry:
  //   { key: 'phone-…', name: 'Alex', role: 'any' | 'from' | 'to' }
  // The PARENT (this component) derives the legacy fromKeys / toKeys
  // sets from this array at fetch time so the backend stays untouched.
  // 'any' chips contribute to BOTH sets (server filter is union); 'from'
  // chips contribute to fromKeys only; 'to' chips contribute to toKeys
  // only. Effect: a single 'any' chip = "every comm involving this
  // person" without forcing the user to pick a direction.
  const [participants, setParticipants] = useState([]);

  // Participants picker mode. 'split' = legacy From/To AND semantics
  // (matches the old behaviour exactly). 'any' = direction-agnostic
  // involvement: every participant goes into a single OR bucket
  // (`participant_keys`), so "Filter Comms by this contact" returns
  // every comm involving them rather than only self-msgs.
  // Per-case localStorage so the user's choice persists across visits.
  const participantsModeKey = `cb.comms.participantsMode.${caseId || 'unknown'}`;
  const [participantsMode, setParticipantsMode] = useState(() => {
    if (typeof window === 'undefined') return 'split';
    try {
      const stored = window.localStorage.getItem(participantsModeKey);
      return stored === 'any' ? 'any' : 'split';
    } catch { return 'split'; }
  });
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try { window.localStorage.setItem(participantsModeKey, participantsMode); }
    catch { /* ignore */ }
  }, [participantsMode, participantsModeKey]);

  // Split mode: derive From / To Sets the legacy way. In Any mode we
  // do NOT populate these — instead we hand the union to the backend
  // via `participant_keys` (OR/involvement). This is the structural fix
  // for the "Filter Comms by one contact returns nothing" bug, which
  // was caused by Split-mode AND semantics requiring sender == recipient
  // when both From and To were seeded with the same key.
  const fromKeys = useMemo(() => {
    if (participantsMode === 'any') return new Set();
    const out = new Set();
    for (const p of participants) {
      if (p.role === 'from' || p.role === 'any') out.add(p.key);
    }
    return out;
  }, [participants, participantsMode]);
  const toKeys = useMemo(() => {
    if (participantsMode === 'any') return new Set();
    const out = new Set();
    for (const p of participants) {
      if (p.role === 'to' || p.role === 'any') out.add(p.key);
    }
    return out;
  }, [participants, participantsMode]);
  // Any mode: union of every selected participant key — backend OR
  // semantics. Empty Set in Split mode so the API client omits the
  // param entirely.
  const participantKeys = useMemo(() => {
    if (participantsMode !== 'any') return new Set();
    const out = new Set();
    for (const p of participants) out.add(p.key);
    return out;
  }, [participants, participantsMode]);
  const [activeTypes, setActiveTypes] = useState(new Set(['message', 'call', 'email']));
  const [activeApps, setActiveApps] = useState(new Set()); // empty = all apps
  // Scrubber-driven coarse window (Date | null). Maps to startDate/endDate
  // strings sent to the server-side filter.
  const [windowStart, setWindowStart] = useState(null);
  const [windowEnd, setWindowEnd] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Phase K3 — Browse / Read mode toggle. Browse = full filter
  // chrome (default; matches the legacy layout). Read = collapse
  // every filter row + the bottom cross-type timeline so the thread
  // list + thread view get the entire screen. Per-case localStorage
  // so the user's choice persists across visits to the same case.
  const viewModeKey = `cb.comms.viewMode.${caseId || 'unknown'}`;
  const [viewMode, setViewMode] = useState(() => {
    if (typeof window === 'undefined') return 'browse';
    try {
      const stored = window.localStorage.getItem(viewModeKey);
      return stored === 'read' ? 'read' : 'browse';
    } catch { return 'browse'; }
  });
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try { window.localStorage.setItem(viewModeKey, viewMode); }
    catch { /* ignore */ }
  }, [viewMode, viewModeKey]);
  const isReadMode = viewMode === 'read';

  // Phase K4 (revised) — cross-type timeline as a slide-in flyover
  // from the bottom edge. The K4 first-pass removed it entirely;
  // user pushed back ('this is a huge piece') so it's back, but
  // doesn't pay layout cost when off. Default closed; toggle from
  // the mode-bar button. Per-case localStorage so the user's
  // last preference (open/closed) persists.
  const timelineFlyoverKey = `cb.comms.timelineFlyover.${caseId || 'unknown'}`;
  const [timelineFlyoverOpen, setTimelineFlyoverOpen] = useState(() => {
    if (typeof window === 'undefined') return false;
    try { return window.localStorage.getItem(timelineFlyoverKey) === '1'; }
    catch { return false; }
  });
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try { window.localStorage.setItem(timelineFlyoverKey, timelineFlyoverOpen ? '1' : '0'); }
    catch { /* ignore */ }
  }, [timelineFlyoverOpen, timelineFlyoverKey]);

  // ISO yyyy-mm-dd derived from the scrubber window for the API.
  const startDate = windowStart ? toISODate(windowStart) : '';
  const endDate = windowEnd ? toISODate(windowEnd) : '';

  // --- Data state ---
  const [entities, setEntities] = useState([]);
  const [entitiesLoading, setEntitiesLoading] = useState(false);

  // Backfill participant chip names once entities load — Filter Comms
  // intents may seed a chip before entities arrive (the chip then
  // shows the raw key); this resolves the prettier name retroactively
  // without changing the chip key (filter still applies).
  useEffect(() => {
    if (!entities.length) return;
    setParticipants((prev) => {
      let dirty = false;
      const next = prev.map(p => {
        if (p.name && p.name !== p.key) return p;
        const e = entities.find(x => x.key === p.key);
        if (!e || !e.name || e.name === p.key) return p;
        dirty = true;
        return { ...p, name: e.name };
      });
      return dirty ? next : prev;
    });
  }, [entities]);

  const [sourceApps, setSourceApps] = useState([]);

  const [threads, setThreads] = useState([]);
  const [threadsTotal, setThreadsTotal] = useState(0);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [threadsProgress, setThreadsProgress] = useState(0);
  const [threadsStage, setThreadsStage] = useState('');

  // Envelope = cheap aggregation across the whole comms shape (no item
  // rows). Powers the "honest" scrubber bounds + density curve and the
  // status bar's true total. Fetched in parallel with the body load
  // so the UI can render the bar before the threads themselves arrive.
  const [envelope, setEnvelope] = useState(null);
  const [envelopeLoading, setEnvelopeLoading] = useState(false);

  const [selectedThread, setSelectedThread] = useState(null);

  // Per-message selection — drives the universal right-rail. The
  // thread-level state above stays separate (it picks which thread to
  // render in the middle pane); this picks which message/call/even
  // inside that thread the rail should show. Cleared when the thread
  // changes so a stale id doesn't outlive its container.
  const { selectEntity, selection } = useCellebriteSelection();
  const [selectedItemId, setSelectedItemId] = useState(null);
  useEffect(() => {
    setSelectedItemId(null);
  }, [selectedThread?.thread_id]);

  // Type-agnostic "Filter Comms" intent listener. Originally added
  // for the Contacts (unified) tab (Phase G3); broadened so any
  // surface — Overview Contacts/Messages/Calls/Emails, search results,
  // future panes — can publish a selection with
  // `_filter_intent: 'comms'` + `person_keys: [...]` and have the
  // Comms feed seed both the From and To filter with that union.
  // Use a ref to track the last consumed intent id so we don't
  // re-apply on every selection state change.
  const lastFilterIntentRef = useRef(null);
  useEffect(() => {
    if (!selection) return;
    if (selection.payload?._filter_intent !== 'comms') return;
    if (lastFilterIntentRef.current === selection.id) return;
    lastFilterIntentRef.current = selection.id;
    const personKeys = selection.payload?.person_keys || [];
    if (personKeys.length === 0) return;
    // Force Any-direction mode whenever a Filter Comms intent fires.
    // The intent's natural meaning is "show me every comm involving
    // these people" — Split mode (AND semantics) silently returned
    // nothing when the same key was seeded in both From and To, which
    // was the root cause of the empty-feed regression on contact
    // filters. Any mode routes the keys through `participant_keys`
    // (OR semantics) so the result matches user expectation.
    setParticipantsMode('any');
    setParticipants((prev) => {
      const byKey = new Map(prev.map(p => [p.key, p]));
      for (const k of personKeys) {
        const existing = byKey.get(k);
        if (existing) {
          byKey.set(k, { ...existing, role: 'any' });
        } else {
          byKey.set(k, { key: k, name: k, role: 'any' });
        }
      }
      return [...byKey.values()];
    });
  }, [selection]);

  const handleItemSelect = useCallback((item) => {
    if (!item) return;
    setSelectedItemId(item.id || null);
    // Map comms item shape onto the rail's selection contract. The
    // event-like accordion in the rail handles all three types so we
    // pass the type straight through (message / call / email).
    selectEntity({
      type: item.type || 'message',
      id: item.id,
      caseId,
      reportKey: item.report_key || item.cellebrite_report_key,
      payload: {
        // Mirror the projected fields the EventBody renderer expects
        // (it was originally written for the events-tab payload shape).
        // `node_key` must be the Neo4j node's `key` property — the rail's
        // /events/detail/{key} endpoint matches on that, not on `id`
        // (which is the source-system id). Fall back to `item.id` only
        // when older payloads don't carry `key` yet.
        ...item,
        node_key: item.key || item.id,
        event_type: item.type,
        label:
          item.type === 'email'
            ? (item.subject || '(no subject)')
            : item.type === 'call'
              ? `${item.sender?.name || 'Unknown'} → ${item.recipient?.name || 'Unknown'}`
              : (item.body || '(message)').slice(0, 80),
      },
      source: 'comms',
    });
  }, [caseId, selectEntity]);

  // View-aware AI context
  const rootRef = useRef(null);
  const { publish, clear } = useChatContext();

  // Publish view context to ChatContext (debounced). Runs whenever the filters
  // or the threads list change.
  useEffect(() => {
    publish({
      ...buildCommsContext({
        reports,
        selectedReportKeys,
        fromKeys,
        toKeys,
        activeTypes,
        activeApps,
        startDate,
        endDate,
        searchQuery,
        threads,
        selectedThread,
      }),
      anchorRef: rootRef,
    });
    return () => {
      // Don't clear aggressively — other unmount paths handle the full clear.
    };
  }, [
    publish,
    reports,
    selectedReportKeys,
    fromKeys,
    toKeys,
    activeTypes,
    activeApps,
    startDate,
    endDate,
    searchQuery,
    threads,
    selectedThread,
  ]);

  // On unmount, clear the context so the chips disappear when the user leaves.
  useEffect(() => () => clear(), [clear]);

  // Device map for thread row badges
  const deviceById = useMemo(() => {
    const map = {};
    reports.forEach(r => {
      map[r.report_key] = `${r.device_model || '?'}${r.phone_owner_name ? ` · ${r.phone_owner_name}` : ''}`;
    });
    return map;
  }, [reports]);

  const threadTypesParam = useMemo(() => {
    const map = { message: 'chat', call: 'calls', email: 'emails' };
    return [...activeTypes].map(t => map[t]).filter(Boolean);
  }, [activeTypes]);

  // Load entities + source apps when report set changes
  useEffect(() => {
    if (!caseId) return;
    if (!reportsReady) return;
    let cancelled = false;
    setEntitiesLoading(true);
    const keys = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    Promise.all([
      cellebriteCommsAPI.getEntities(caseId, keys).catch(() => ({ entities: [] })),
      cellebriteCommsAPI.getSourceApps(caseId, keys).catch(() => ({ apps: [] })),
    ]).then(([entitiesData, appsData]) => {
      if (!cancelled) {
        setEntities(entitiesData.entities || []);
        setSourceApps(appsData.apps || []);
        setEntitiesLoading(false);
        // Prune any selected apps that no longer exist
        setActiveApps(prev => {
          if (prev.size === 0) return prev;
          const available = new Set((appsData.apps || []).map(a => a.source_app));
          const next = new Set([...prev].filter(a => available.has(a)));
          return next.size === prev.size ? prev : next;
        });
      }
    });
    return () => { cancelled = true; };
  }, [caseId, selectedReportKeys, reportsReady]);

  // Load threads when filters change.
  // Phased fetch: one server call per thread type so we can show real
  // progress as each stage resolves (chat threads are usually the
  // heaviest stage, calls and emails are quicker). The resulting
  // arrays are merged client-side, sorted by last_activity DESC, and
  // capped to the visible limit.
  useEffect(() => {
    if (!caseId) return;
    if (!reportsReady) return;
    const controller = new AbortController();
    let cancelled = false;
    setThreadsLoading(true);
    setThreadsProgress(0);
    setThreadsStage('');
    setThreads([]);
    setThreadsTotal(0);

    const reportKeysArr = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    const baseArgs = {
      reportKeys: reportKeysArr,
      fromKeys: fromKeys.size > 0 ? [...fromKeys] : null,
      toKeys: toKeys.size > 0 ? [...toKeys] : null,
      // In Any mode `participantKeys` is populated and from/to are
      // empty Sets. Backend OR-combines participant_keys with from/to
      // when both are present; in our case only one channel is ever
      // active at a time per the participantsMode toggle.
      participantKeys: participantKeys.size > 0 ? [...participantKeys] : null,
      sourceApps: activeApps.size > 0 ? [...activeApps] : null,
      startDate: startDate || null,
      endDate: endDate || null,
      limit: 300,
      signal: controller.signal,
    };

    // Friendly labels for the active set, in stable order.
    const STAGE_LABELS = {
      chat: 'Loading chat conversations',
      calls: 'Loading call threads',
      emails: 'Loading email threads',
    };
    const stages = threadTypesParam.length > 0
      ? threadTypesParam
      : ['chat', 'calls', 'emails'];

    (async () => {
      const aggregated = [];
      let totalSum = 0;

      for (let i = 0; i < stages.length; i += 1) {
        if (cancelled) return;
        const t = stages[i];
        setThreadsStage(STAGE_LABELS[t] || `Loading ${t}`);
        try {
          // eslint-disable-next-line no-await-in-loop
          const data = await cellebriteCommsAPI.getThreads(caseId, {
            ...baseArgs,
            threadTypes: [t],
          });
          if (cancelled) return;
          aggregated.push(...(data.threads || []));
          totalSum += Number(data.total || 0);
        } catch (err) {
          // Caller-initiated abort = this effect was superseded; the new
          // run owns state from here on, so don't fall through to the
          // setThreads/setThreadsLoading writes below.
          if (err?.name === 'AbortError' || cancelled) return;
          // One stage failing shouldn't blank the whole tab — just
          // skip its rows and keep going.
        }
        setThreadsProgress(Math.round(((i + 1) / stages.length) * 100));
      }

      if (cancelled) return;

      // Same sort + slice the server used to apply itself.
      aggregated.sort(
        (a, b) => (b.last_activity || '').localeCompare(a.last_activity || ''),
      );
      const sliced = aggregated.slice(0, baseArgs.limit);

      setThreads(sliced);
      setThreadsTotal(totalSum);
      setThreadsLoading(false);
      setThreadsStage('');
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [caseId, selectedReportKeys, fromKeys, toKeys, participantKeys, threadTypesParam, activeApps, startDate, endDate, reportsReady]);

  // Envelope fetch — runs in parallel with the threads load so the
  // scrubber bounds + density bars + status bar's true total can paint
  // before any thread row arrives. Same filter inputs as the threads
  // load (minus searchQuery, which is client-side only).
  //
  // The envelope endpoint expects feed-item type names ("message",
  // "call", "email"), not the thread-type names ("chat", "calls",
  // "emails") used by /comms/threads, so we send activeTypes directly.
  useEffect(() => {
    if (!caseId) return;
    if (!reportsReady) return;
    const controller = new AbortController();
    let cancelled = false;
    setEnvelopeLoading(true);
    cellebriteCommsAPI.getEnvelope(caseId, {
      reportKeys: selectedReportKeys.size > 0 ? [...selectedReportKeys] : null,
      fromKeys: fromKeys.size > 0 ? [...fromKeys] : null,
      toKeys: toKeys.size > 0 ? [...toKeys] : null,
      participantKeys: participantKeys.size > 0 ? [...participantKeys] : null,
      types: activeTypes.size > 0 ? [...activeTypes] : null,
      sourceApps: activeApps.size > 0 ? [...activeApps] : null,
      startDate: startDate || null,
      endDate: endDate || null,
      signal: controller.signal,
    }).then(env => {
      if (cancelled) return;
      setEnvelope(env || null);
      setEnvelopeLoading(false);
    }).catch((err) => {
      if (cancelled || err?.name === 'AbortError') return;
      // Don't blank an existing envelope on transient errors — the bar
      // would briefly collapse to "no data" and confuse the user.
      setEnvelopeLoading(false);
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [caseId, selectedReportKeys, fromKeys, toKeys, participantKeys, activeTypes, activeApps, startDate, endDate, reportsReady]);

  // Cellebrite sometimes ingests the same logical conversation twice
  // — e.g. once as a Chat node and once as a Conversation node, or once
  // with an extra participant captured ("+1") and once without. Both
  // rows have the same name/source_app/report_key but distinct
  // thread_ids and slightly different participant sets. Collapse them
  // here so the user sees one row per real conversation.
  //
  // Rule: group by (report_key, source_app, thread_type, sorted
  // participant keys). Within a group, prefer the row with the most
  // messages (richest data); if tied, prefer the one with more
  // participants. The other row's items end up under the chosen
  // thread_id, so opening the survivor still shows the same content.
  const dedupedThreads = useMemo(() => dedupeThreads(threads), [threads]);

  // ------------------------------------------------------------------
  // Deep message-body search (server-side full-text)
  //
  // Thread metadata only includes the chat name + participant names, so
  // typing a word that appears in message bodies wouldn't match locally.
  // We hit /comms/messages/search after a 250ms debounce — instant for
  // "common app/contact" terms (which match locally first), and one
  // round-trip for "find this word in any chat".
  // ------------------------------------------------------------------
  const [deepSearch, setDeepSearch] = useState({
    query: '',
    threadIds: new Set(),
    matchesByThread: {},
    loading: false,
  });

  // Debounce + fire the deep search whenever the query (or scope) changes.
  useEffect(() => {
    const q = searchQuery.trim();
    if (!q || !caseId) {
      setDeepSearch({ query: '', threadIds: new Set(), matchesByThread: {}, loading: false });
      return;
    }
    let cancelled = false;
    setDeepSearch((prev) => ({ ...prev, loading: true }));
    const t = setTimeout(() => {
      const reportKeysArr = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
      cellebriteCommsAPI
        .searchMessages(caseId, { q, reportKeys: reportKeysArr, limit: 300 })
        .then((data) => {
          if (cancelled) return;
          const matchesByThread = {};
          for (const m of data.matches || []) {
            if (!m.thread_id) continue;
            (matchesByThread[m.thread_id] ||= []).push(m);
          }
          setDeepSearch({
            query: q,
            threadIds: new Set(data.thread_ids || []),
            matchesByThread,
            loading: false,
          });
        })
        .catch(() => {
          if (cancelled) return;
          setDeepSearch({ query: q, threadIds: new Set(), matchesByThread: {}, loading: false });
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [caseId, searchQuery, selectedReportKeys]);

  // In-memory thread metadata search (per keystroke, no debounce).
  // Combined with deep-search results: a thread shows up if EITHER its
  // metadata matches OR a message inside it matches.
  const parsedQuery = useMemo(() => parseQuery(searchQuery), [searchQuery]);
  const { filteredThreads, threadHighlights } = useMemo(() => {
    if (!searchQuery) return { filteredThreads: dedupedThreads, threadHighlights: [] };
    const out = [];
    const allHighlights = new Set();
    const deepHits = deepSearch.threadIds;
    for (const t of dedupedThreads) {
      const m = matchItem(t, parsedQuery, 'thread', reports);
      const inDeep = deepHits.has(t.thread_id);
      if (m.matches || inDeep) {
        out.push(t);
        m.highlights.forEach((h) => allHighlights.add(h));
      }
    }
    // Always highlight the literal search term itself, even if it only
    // matched a body (so the row text gets `<mark>` if the term appears
    // anywhere displayable).
    if (searchQuery.trim()) allHighlights.add(searchQuery.trim().toLowerCase());
    return { filteredThreads: out, threadHighlights: Array.from(allHighlights) };
  }, [dedupedThreads, searchQuery, parsedQuery, reports, deepSearch.threadIds]);

  // Publish counts to the persistent status bar.
  //
  // `total` prefers the envelope's true item count over the threads
  // list length — the envelope sees every message/call/email matching
  // the active filters, while the threads list is bounded by the
  // server's per-block cap. `displayed` stays the post-filter thread
  // count so the bar mirrors what the user can actually click on.
  // The hint surfaces the gap when the loaded slice is materially
  // smaller than the envelope so the user knows there's "more under
  // the hood" without surprising them on scroll.
  const envelopeTotal = envelope?.total ?? null;
  const trueTotal = envelopeTotal ?? Math.max(threadsTotal, dedupedThreads.length);
  useCellebriteStatus({
    isActive,
    total: trueTotal,
    displayed: filteredThreads.length,
    selected: selectedThread ? 1 : 0,
    label: 'threads',
    hint: threadsLoading
      ? (threadsStage || 'Loading…')
      : envelopeLoading
        ? 'Computing envelope…'
        : (envelopeTotal != null && envelopeTotal > dedupedThreads.length
            ? `Envelope: ${envelopeTotal.toLocaleString()} items across ${dedupedThreads.length.toLocaleString()} loaded threads`
            : null),
  });

  // When the user types a deep-search term, automatically open the first
  // matching thread so they can see the actual message immediately.
  // Only fires when the user has no thread selected yet, or when the
  // selected thread is no longer in the filtered list.
  useEffect(() => {
    if (!deepSearch.query) return;
    if (deepSearch.loading) return;
    if (filteredThreads.length === 0) return;
    const stillPresent =
      selectedThread && filteredThreads.some((t) => t.thread_id === selectedThread.thread_id);
    if (stillPresent) return;
    // Pick the first thread that has a message-body hit (those are the
    // most relevant to the user's query); fall back to the first thread.
    const first =
      filteredThreads.find((t) => deepSearch.matchesByThread[t.thread_id]) ||
      filteredThreads[0];
    if (first) setSelectedThread(first);
  }, [deepSearch.query, deepSearch.loading, deepSearch.matchesByThread, filteredThreads, selectedThread]);

  // Clear selected thread when it no longer matches filters
  useEffect(() => {
    if (!selectedThread) return;
    const stillPresent = filteredThreads.some(t => t.thread_id === selectedThread.thread_id);
    if (!stillPresent) setSelectedThread(null);
  }, [filteredThreads, selectedThread]);

  if (phoneCtx?.noneSelected) {
    return (
      <div ref={rootRef} className="flex flex-col h-full min-h-0 bg-white">
        <PhoneSelector />
        <NoPhonesSelectedEmptyState />
      </div>
    );
  }

  // The horizontal thread-list / thread-view split — same in Browse
  // and Read modes, so extracted once and rendered into either
  // surrounding layout below.
  const threadSplit = (
    <ResizableSplit
      direction="horizontal"
      storageKey={`cb.comms.threadList.${caseId}`}
      defaultSize={320}
      minSize={200}
      maxSize={600}
      className="h-full"
      first={(
        <CommsThreadList
          threads={filteredThreads}
          loading={threadsLoading || entitiesLoading}
          loadingProgress={threadsProgress}
          loadingStage={threadsStage}
          selectedThreadId={selectedThread?.thread_id}
          onSelect={setSelectedThread}
          deviceById={deviceById}
          highlights={threadHighlights}
        />
      )}
      second={(
        <CommsThreadView
          caseId={caseId}
          selectedThread={selectedThread}
          externalSearchQuery={searchQuery}
          firstMatch={
            selectedThread && deepSearch.matchesByThread[selectedThread.thread_id]
              ? deepSearch.matchesByThread[selectedThread.thread_id][0]
              : null
          }
          onItemSelect={handleItemSelect}
          selectedItemId={selectedItemId}
        />
      )}
    />
  );

  // Mode toggle button rendered into both layouts so the user can
  // flip back to Browse from Read with a single click.
  const modeToggle = (
    <ModeToggleButton
      viewMode={viewMode}
      setViewMode={setViewMode}
      timelineFlyoverOpen={timelineFlyoverOpen}
      setTimelineFlyoverOpen={setTimelineFlyoverOpen}
    />
  );

  // Cross-type timeline flyover. Mounted at the root level so it
  // overlays both Browse and Read layouts identically. Slides in
  // from the bottom edge (separate from the right-rail flyout
  // so they can co-exist without fighting for the same edge).
  // Caps at 50vh so it never eats the whole feed.
  const timelineFlyover = timelineFlyoverOpen ? (
    <CrossTypeTimelineFlyover
      caseId={caseId}
      fromKeys={fromKeys}
      toKeys={toKeys}
      participantKeys={participantKeys}
      reportKeys={selectedReportKeys}
      types={activeTypes}
      sourceApps={activeApps}
      startDate={startDate || null}
      endDate={endDate || null}
      onItemSelect={handleItemSelect}
      onClose={() => setTimelineFlyoverOpen(false)}
    />
  ) : null;

  // ---------------- Read mode: max-feed layout ----------------
  // No filter chrome, no bottom timeline, no scrubber. Just the
  // thread split filling the screen + a thin search bar + the mode
  // toggle (so the user can get back to Browse). Filter state from
  // the Browse mode is preserved — it's still applied to threads,
  // we just don't show the controls.
  if (isReadMode) {
    return (
      <div ref={rootRef} className="flex flex-col h-full min-h-0 bg-white">
        <PhoneSelector />
        <div className="flex items-center gap-2 px-4 py-1.5 border-b border-light-200 bg-light-50 flex-shrink-0">
          {modeToggle}
          <div className="flex-1 max-w-2xl">
            <CellebriteSearchInput
              value={searchQuery}
              onChange={setSearchQuery}
              placeholder='Search threads — type:chat from:John app:WhatsApp'
              matchCount={filteredThreads.length}
              totalCount={threads.length}
              itemNoun="thread"
              focusOnSlash
              compact
            />
          </div>
          <span className="text-[11px] text-light-500">
            Filter chrome hidden — switch to Browse to refine
          </span>
        </div>
        <div className="flex-1 min-h-0">
          {threadSplit}
        </div>
        {timelineFlyover}
      </div>
    );
  }

  // ---------------- Browse mode: full layout (default) ----------------

  return (
    <div ref={rootRef} className="flex flex-col h-full min-h-0 bg-white">
      {/* Device selector strip — global across Cellebrite tabs */}
      <PhoneSelector />

      {/* Mode toggle row */}
      <div className="flex items-center gap-2 px-4 py-1 border-b border-light-200 bg-light-50 flex-shrink-0">
        {modeToggle}
        <span className="text-[11px] text-light-500">
          Browse mode — switch to Read to maximise the conversation feed
        </span>
      </div>

      {/* Layout — three resizable tiers:
            1. From/To entity filter (top, resizable height)
            2. Source row + type row + scrubber + search + thread
               split (middle, takes whatever's left after 1 and 3)
            3. Cross-type timeline (bottom, resizable height)
          All three persist their sizes per-case in localStorage so
          investigators get their preferred layout back next session.

          Without the explicit drag-resize on tier 1 the From/To
          filter eats half the screen on busy cases — its content is
          unbounded (one row per entity) and the windowed render
          sized itself to whatever container height it got. */}
      {/* Phase K1: Participants filter — self-contained collapsible
          chip strip; the old ResizableSplit between it and the rest
          of the page was a workaround for the From/To filter eating
          half the screen, no longer needed. */}
      <CommsParticipantsFilter
        entities={entities}
        participants={participants}
        onParticipantsChange={setParticipants}
        mode={participantsMode}
        onModeChange={setParticipantsMode}
      />

      {/* Phase K2: Compact toolbar combining search + type pills +
          source dropdown + scrubber-handle. Reclaims the three
          stacked rows of header chrome the old layout had. */}
      <CommsCompactToolbar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        searchMatchCount={filteredThreads.length}
        searchTotalCount={threads.length}
        activeTypes={activeTypes}
        onTypesChange={setActiveTypes}
        sourceApps={sourceApps}
        activeApps={activeApps}
        onAppsChange={setActiveApps}
        scrubberItems={threads}
        scrubberEnvelope={envelope ? {
          minDate: envelope.min_date,
          maxDate: envelope.max_date,
          histogram: envelope.histogram,
          total: envelope.total,
          loading: envelopeLoading,
          hasMoreThanItems: typeof envelope.total === 'number' && envelope.total > threads.length,
        } : null}
        windowStart={windowStart}
        windowEnd={windowEnd}
        onWindowChange={(s, e) => { setWindowStart(s); setWindowEnd(e); }}
      />

      {/* Phase K4 (revised): cross-type timeline returns as a slide-
          in flyover from the bottom edge instead of an always-mounted
          panel. Mounted at the root so it overlays without eating
          layout cost when off. Toggle from the Timeline button in
          the mode bar. */}
      <div className="flex-1 min-h-0">
        {threadSplit}
      </div>
      {timelineFlyover}
    </div>
  );
}

/**
 * Three-button mode bar:
 *   - Browse  (full filter chrome — default)
 *   - Read    (collapse all chrome, max conversation space)
 *   - Timeline (toggle the cross-type bottom flyover)
 *
 * Browse / Read are MUTUALLY EXCLUSIVE layout modes (one or the
 * other). Timeline is INDEPENDENT — it's a flyover overlay that
 * works on top of either layout. The visual styling reflects this:
 * Browse/Read share a pill-radio look, Timeline is a separate
 * pressable button alongside.
 *
 * Filter STATE is preserved across the toggle — only the controls
 * are hidden in Read mode. Per-case localStorage handled by the
 * parent so the toggle itself is stateless.
 */
function ModeToggleButton({
  viewMode, setViewMode,
  timelineFlyoverOpen, setTimelineFlyoverOpen,
}) {
  const isRead = viewMode === 'read';
  return (
    <div className="inline-flex items-center gap-1.5">
      {/* Browse / Read — paired pill toggle (mutually exclusive) */}
      <div className="inline-flex border border-light-300 rounded overflow-hidden text-[11px]">
        <button
          type="button"
          onClick={() => setViewMode('browse')}
          className={`flex items-center gap-1 px-2 py-0.5 transition-colors ${
            !isRead
              ? 'bg-owl-blue-100 text-owl-blue-800'
              : 'bg-white text-light-600 hover:bg-light-100'
          }`}
          title="Browse mode — full filter controls"
        >
          <SlidersHorizontal className="w-3 h-3" />
          Browse
        </button>
        <button
          type="button"
          onClick={() => setViewMode('read')}
          className={`flex items-center gap-1 px-2 py-0.5 border-l border-light-300 transition-colors ${
            isRead
              ? 'bg-owl-blue-100 text-owl-blue-800'
              : 'bg-white text-light-600 hover:bg-light-100'
          }`}
          title="Read mode — hide filter chrome, max conversation space"
        >
          <BookOpen className="w-3 h-3" />
          Read
        </button>
      </div>

      {/* Timeline — independent toggle for the cross-type flyover.
          Works on top of either Browse or Read mode. */}
      <button
        type="button"
        onClick={() => setTimelineFlyoverOpen(v => !v)}
        className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] border rounded transition-colors ${
          timelineFlyoverOpen
            ? 'bg-emerald-100 border-emerald-300 text-emerald-800'
            : 'bg-white border-light-300 text-light-600 hover:bg-light-100'
        }`}
        title={
          timelineFlyoverOpen
            ? 'Hide the cross-type timeline'
            : 'Show the cross-type timeline (slides in from bottom)'
        }
      >
        <Activity className="w-3 h-3" />
        Timeline
      </button>
    </div>
  );
}

/**
 * Cross-type timeline bottom flyover. Slides up from the bottom
 * edge with a 220ms ease — same animation language as the right-
 * rail flyout. Caps at 50vh so it never eats the whole feed even
 * if the user opens it while the conversation is short.
 *
 * Dismissal: X button, Esc key, or toggling the Timeline button
 * off in the mode bar.
 */
function CrossTypeTimelineFlyover({
  caseId, fromKeys, toKeys, participantKeys, reportKeys, types, sourceApps,
  startDate, endDate, onItemSelect, onClose,
}) {
  // Esc to dismiss.
  useEffect(() => {
    const onKey = (ev) => { if (ev.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // User-resizable height. Drag the top edge up/down to grow/shrink.
  // Bounds: minimum 120px so the chrome stays usable; maximum 80vh
  // so the flyover never quite covers the entire feed (a sliver of
  // context behind it is part of the design — keeps the user
  // anchored). Default 40vh. Per-case localStorage so the user's
  // preferred size persists across visits.
  const heightKey = `cb.comms.timelineFlyoverHeight.${caseId || 'unknown'}`;
  const defaultHeight = Math.round(window.innerHeight * 0.4);
  const [height, setHeight] = useState(() => {
    if (typeof window === 'undefined') return defaultHeight;
    try {
      const stored = window.localStorage.getItem(heightKey);
      const n = stored ? Number(stored) : NaN;
      if (Number.isFinite(n) && n >= 120) return Math.min(n, window.innerHeight * 0.8);
    } catch { /* ignore */ }
    return defaultHeight;
  });
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try { window.localStorage.setItem(heightKey, String(Math.round(height))); }
    catch { /* ignore */ }
  }, [height, heightKey]);

  // Drag state lives in a ref so the document-level pointermove
  // handler doesn't re-render the component every pixel — it just
  // updates the height state which IS reactive.
  const dragRef = useRef({ active: false, startY: 0, startHeight: 0 });
  const onPointerDown = useCallback((ev) => {
    ev.preventDefault();
    dragRef.current = {
      active: true,
      startY: ev.clientY,
      startHeight: height,
    };
    // Lock the cursor + suppress text selection while dragging.
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';

    const onMove = (mv) => {
      if (!dragRef.current.active) return;
      // Pulling UP grows the flyover (negative delta), pulling DOWN
      // shrinks it. Bounded by min 120px and 80vh.
      const delta = dragRef.current.startY - mv.clientY;
      const next = Math.max(
        120,
        Math.min(window.innerHeight * 0.8, dragRef.current.startHeight + delta),
      );
      setHeight(next);
    };
    const onUp = () => {
      dragRef.current.active = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
    };
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
  }, [height]);

  return (
    <aside
      className="fixed left-0 right-0 bottom-0 z-30 bg-white border-t border-light-200 shadow-2xl flex flex-col animate-timeline-slide"
      role="complementary"
      aria-label="Cross-type comms timeline"
      style={{ height: `${height}px` }}
    >
      <style>{`
        @keyframes timeline-slide-up {
          from { transform: translateY(100%); }
          to   { transform: translateY(0); }
        }
        .animate-timeline-slide {
          animation: timeline-slide-up 220ms cubic-bezier(0.22, 0.61, 0.36, 1);
        }
      `}</style>

      {/* Top-edge resize handle — sits across the whole top edge so
          the user can grab anywhere along it. Hover affordance
          (emerald accent) matches the resizable splits we already
          have elsewhere in the Cellebrite tabs. */}
      <div
        onPointerDown={onPointerDown}
        className="h-1.5 cursor-row-resize bg-light-100 hover:bg-emerald-300 active:bg-emerald-400 transition-colors flex-shrink-0"
        title="Drag to resize the timeline flyover"
        role="separator"
        aria-orientation="horizontal"
      />

      <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-light-200 bg-light-50 flex-shrink-0">
        <Activity className="w-3.5 h-3.5 text-emerald-600" />
        <span className="text-xs font-semibold text-owl-blue-900">
          Conversation timeline
        </span>
        <span className="text-[11px] text-light-500">
          · cross-type events under the active filters · drag the top edge to resize
        </span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={onClose}
          className="p-1 text-light-400 hover:text-light-700 rounded"
          title="Close (Esc)"
          aria-label="Close timeline flyover"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        <CommsCrossTypeTimeline
          caseId={caseId}
          fromKeys={fromKeys}
          toKeys={toKeys}
          participantKeys={participantKeys}
          reportKeys={reportKeys}
          types={types}
          sourceApps={sourceApps}
          startDate={startDate}
          endDate={endDate}
          onItemSelect={onItemSelect}
        />
      </div>
    </aside>
  );
}

/**
 * yyyy-mm-dd in local time. Used to sync the scrubber Date window with
 * the server-side date filter strings.
 */
function toISODate(d) {
  if (!(d instanceof Date) || isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Collapse threads that represent the same logical conversation.
 *
 * Cellebrite occasionally produces two PARENT chat nodes for one real
 * Facebook Messenger / WhatsApp / SMS conversation — e.g. one captured
 * with an extra participant ("+1") and one without, or a parser that
 * emitted both a `Chat` and a `Conversation` model for the same chat.
 * The list then shows two near-identical rows and clicking one selects
 * the lesser duplicate.
 *
 * Strategy: bucket by (report_key, source_app, thread_type, sorted
 * participant keys). Within each bucket pick the row with the most
 * messages, breaking ties by participant count, then by latest
 * `last_activity`. The other rows in the bucket are merged: their
 * `thread_id` is added to a `merged_thread_ids` array on the survivor
 * so the back-end can be queried for the union later if needed.
 *
 * Subset rule: if bucket A's participant set is a strict subset of
 * bucket B's participants and they share (report_key, source_app,
 * thread_type), the smaller bucket folds into the larger. This catches
 * the "+1 vs no +1" case the user reported.
 */
function dedupeThreads(threads) {
  if (!Array.isArray(threads) || threads.length < 2) return threads || [];

  // Step 1: bucket by exact participant set
  const exactBuckets = new Map();
  for (const t of threads) {
    const key = exactKey(t);
    if (!exactBuckets.has(key)) exactBuckets.set(key, []);
    exactBuckets.get(key).push(t);
  }

  // Step 2: pick a survivor per exact bucket
  const survivors = [];
  for (const bucket of exactBuckets.values()) {
    survivors.push(pickSurvivor(bucket));
  }

  // Step 3: subset-merge — if survivor A's participants ⊂ survivor B's
  // and they share (report_key, source_app, thread_type), drop A.
  // O(n²) over survivors which is fine for typical thread counts.
  const dropped = new Set();
  for (let i = 0; i < survivors.length; i++) {
    if (dropped.has(i)) continue;
    const a = survivors[i];
    const aSet = participantSet(a);
    if (aSet.size === 0) continue;
    for (let j = 0; j < survivors.length; j++) {
      if (i === j || dropped.has(j)) continue;
      const b = survivors[j];
      if (!sameContext(a, b)) continue;
      const bSet = participantSet(b);
      if (bSet.size <= aSet.size) continue; // only collapse smaller into larger
      let isSubset = true;
      for (const k of aSet) {
        if (!bSet.has(k)) { isSubset = false; break; }
      }
      if (isSubset) {
        // Carry the smaller's thread_id onto the survivor for traceability.
        const merged = b.merged_thread_ids || [];
        if (a.thread_id) merged.push(a.thread_id);
        if (Array.isArray(a.merged_thread_ids)) merged.push(...a.merged_thread_ids);
        b.merged_thread_ids = merged;
        dropped.add(i);
        break;
      }
    }
  }

  return survivors.filter((_, idx) => !dropped.has(idx));
}

function exactKey(t) {
  const ps = (t.participants || [])
    .map(p => p && p.key)
    .filter(Boolean)
    .sort()
    .join('|');
  return [
    t.report_key || '',
    (t.source_app || '').toLowerCase(),
    (t.thread_type || '').toLowerCase(),
    ps,
  ].join('::');
}

function sameContext(a, b) {
  return (
    (a.report_key || '') === (b.report_key || '')
    && (a.source_app || '').toLowerCase() === (b.source_app || '').toLowerCase()
    && (a.thread_type || '').toLowerCase() === (b.thread_type || '').toLowerCase()
  );
}

function participantSet(t) {
  const s = new Set();
  for (const p of t.participants || []) {
    if (p && p.key) s.add(p.key);
  }
  return s;
}

function pickSurvivor(bucket) {
  if (bucket.length === 1) return bucket[0];
  // Sort by messages desc, participants desc, last_activity desc
  const sorted = [...bucket].sort((a, b) => {
    const am = a.message_count || 0;
    const bm = b.message_count || 0;
    if (am !== bm) return bm - am;
    const ap = (a.participants || []).length;
    const bp = (b.participants || []).length;
    if (ap !== bp) return bp - ap;
    const at = a.last_activity ? new Date(a.last_activity).getTime() : 0;
    const bt = b.last_activity ? new Date(b.last_activity).getTime() : 0;
    return bt - at;
  });
  const winner = { ...sorted[0] };
  const merged = [];
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].thread_id) merged.push(sorted[i].thread_id);
  }
  if (merged.length) winner.merged_thread_ids = merged;
  return winner;
}
