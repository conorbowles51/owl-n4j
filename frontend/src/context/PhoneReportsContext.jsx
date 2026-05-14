/**
 * PhoneReportsContext
 *
 * Case-scoped React context that owns:
 *  - the list of Cellebrite PhoneReport records for the active case
 *  - the user's "which phones are visible" selection
 *  - phone-identity lookups (colour + short label) used everywhere
 *
 * Selection persists in localStorage per case so toggling a phone off
 * survives a refresh and propagates across every Cellebrite tab.
 *
 * Consumers should treat the context as optional: when there are no
 * Cellebrite reports for a case (or no provider at all), `reports`
 * is an empty array and `selectedReportKeys` is an empty Set —
 * components fall back to today's behaviour.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { cellebriteAPI } from '../services/api';
import {
  getPhoneIdentity,
  getPhoneIdentityByKey,
} from '../utils/phoneIdentity';

const PhoneReportsContext = createContext(null);

const STORAGE_PREFIX = 'owl.cellebrite.phoneSelection.';

function storageKey(caseId) {
  return `${STORAGE_PREFIX}${caseId}`;
}

function loadSelection(caseId) {
  if (!caseId || typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(storageKey(caseId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return new Set(parsed);
    return null;
  } catch {
    return null;
  }
}

function saveSelection(caseId, selectionSet) {
  if (!caseId || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      storageKey(caseId),
      JSON.stringify(Array.from(selectionSet)),
    );
  } catch {
    /* localStorage full or disabled — silent */
  }
}

export function PhoneReportsProvider({ caseId, children }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedReportKeys, setSelectedReportKeys] = useState(new Set());
  // Track whether we've completed initial hydration so re-renders don't
  // overwrite the user's selection during the load roundtrip.
  // hydratedRef is for internal write gating; `hydrated` (state below)
  // is exposed so consumers can wait for the first selection to settle
  // before firing expensive effects — without that gate, every Comms /
  // Events / Locations effect runs once with empty selection (returns
  // nothing useful) then re-runs once selection arrives, doubling
  // every per-tab API call on case open.
  const hydratedRef = useRef(false);
  const [hydrated, setHydrated] = useState(false);

  const fetchReports = useCallback(async () => {
    if (!caseId) {
      setReports([]);
      setSelectedReportKeys(new Set());
      hydratedRef.current = true;
      setHydrated(true);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await cellebriteAPI.getReports(caseId);
      const list = Array.isArray(data?.reports) ? data.reports : [];
      setReports(list);

      const stored = loadSelection(caseId);
      const validKeys = new Set(list.map((r) => r.report_key));

      let next;
      if (stored) {
        // Drop any stored keys that no longer exist; if the result is
        // empty (e.g. all phones renamed or removed), default back to all.
        const filtered = new Set([...stored].filter((k) => validKeys.has(k)));
        next = filtered.size > 0 ? filtered : new Set(validKeys);
      } else {
        next = new Set(validKeys);
      }

      setSelectedReportKeys(next);
      saveSelection(caseId, next);
      hydratedRef.current = true;
      setHydrated(true);
    } catch (err) {
      setError(err);
      setReports([]);
      setSelectedReportKeys(new Set());
      hydratedRef.current = true;
      setHydrated(true);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    hydratedRef.current = false;
    setHydrated(false);
    fetchReports();
  }, [fetchReports]);

  // Persist any selection change after initial hydration.
  useEffect(() => {
    if (!hydratedRef.current) return;
    saveSelection(caseId, selectedReportKeys);
  }, [caseId, selectedReportKeys]);

  const toggleReport = useCallback((key) => {
    setSelectedReportKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedReportKeys(new Set(reports.map((r) => r.report_key)));
  }, [reports]);

  const clear = useCallback(() => {
    setSelectedReportKeys(new Set());
  }, []);

  const selectOnly = useCallback((key) => {
    setSelectedReportKeys(new Set([key]));
  }, []);

  const setSelection = useCallback((keys) => {
    const arr = Array.isArray(keys) ? keys : Array.from(keys || []);
    setSelectedReportKeys(new Set(arr));
  }, []);

  const getIdentity = useCallback(
    (report) => getPhoneIdentity(report, reports),
    [reports],
  );

  const getIdentityByKey = useCallback(
    (reportKey) => getPhoneIdentityByKey(reportKey, reports),
    [reports],
  );

  // Filtered list of currently-active reports (preserves display order).
  const activeReports = useMemo(
    () => reports.filter((r) => selectedReportKeys.has(r.report_key)),
    [reports, selectedReportKeys],
  );

  const value = useMemo(
    () => ({
      caseId,
      reports,
      activeReports,
      selectedReportKeys,
      hasReports: reports.length > 0,
      hasMultiple: reports.length > 1,
      allSelected:
        reports.length > 0 && selectedReportKeys.size === reports.length,
      noneSelected:
        reports.length > 0 && selectedReportKeys.size === 0,
      loading,
      // True once fetchReports has resolved (success OR error) for the
      // current caseId. Consumers should gate expensive per-tab effects
      // on this so they don't fire once with empty selection then
      // re-fire when the real selection arrives, doubling every API
      // call on case open.
      hydrated,
      error,
      toggleReport,
      selectAll,
      clear,
      selectOnly,
      setSelection,
      refresh: fetchReports,
      getIdentity,
      getIdentityByKey,
    }),
    [
      caseId,
      reports,
      activeReports,
      selectedReportKeys,
      loading,
      hydrated,
      error,
      toggleReport,
      selectAll,
      clear,
      selectOnly,
      setSelection,
      fetchReports,
      getIdentity,
      getIdentityByKey,
    ],
  );

  return (
    <PhoneReportsContext.Provider value={value}>
      {children}
    </PhoneReportsContext.Provider>
  );
}

/**
 * Read the phone-reports context. Returns null when no provider is
 * mounted; callers must check before destructuring so non-Cellebrite
 * surfaces (or unit tests) keep working unchanged.
 */
export function usePhoneReports() {
  return useContext(PhoneReportsContext);
}

/**
 * Convenience: when a component just wants the identity for a single
 * report_key and tolerates the provider being absent.
 */
export function usePhoneIdentity(reportKey) {
  const ctx = useContext(PhoneReportsContext);
  if (!ctx) return null;
  return ctx.getIdentityByKey(reportKey);
}
