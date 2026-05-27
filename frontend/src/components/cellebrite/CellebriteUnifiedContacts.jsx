import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Users, Filter, ExternalLink, Phone, MessageSquare, Mail } from 'lucide-react';
import { cellebriteEventsAPI } from '../../services/api';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import { useCellebriteStatus } from './shared/CellebriteStatusBar';
import { useCellebriteSelection } from './shared/CellebriteSelectionContext';
import CellebriteSearchInput from './shared/CellebriteSearchInput';
import PhoneIdentityChip from './shared/PhoneIdentityChip';
import PhoneSelector from './shared/PhoneSelector';

/**
 * "Contacts (unified)" tab.
 *
 * Cellebrite gives us per-device Person nodes — Alex on phone A, Boss
 * on phone B, Solorzano on phone C — even when they're all the same
 * human reachable on +1-202-805-2817. This tab rolls those Persons up
 * by canonical phone number so the investigator sees one row per
 * person-across-phones, with the alias chip-group attached.
 *
 * Click a row → opens the unified contact in the universal rail
 * (per-device breakdown, recent comms across all aliases). The "Filter
 * Comms feed" button per row hands the union of person_keys to the
 * Comms tab so the investigator can see every message/call to/from
 * that human across every phone in one feed. (Filter wiring lands in
 * G3 — for now the button publishes a selection that CommsCenter
 * will consume.)
 */
export default function CellebriteUnifiedContacts({ caseId, isActive = true }) {
  const phoneCtx = usePhoneReports();
  const reports = phoneCtx?.reports || [];
  const selectedReportKeys = phoneCtx ? phoneCtx.selectedReportKeys : new Set();
  const reportsReady = phoneCtx ? phoneCtx.hydrated : true;

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  // Backend signals truncation when the case has more Person nodes
  // than the safety cap (5K) so we can warn the user that the rollup
  // is incomplete instead of pretending it's the full picture.
  const [truncated, setTruncated] = useState(false);
  const [personCount, setPersonCount] = useState(0);

  // Fetch the rollup whenever the case, the phone selection, or the
  // hydration state changes. Search is applied locally so the user
  // gets instant feedback while typing without a re-fetch per char.
  useEffect(() => {
    if (!caseId) return undefined;
    if (!reportsReady) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const reportKeysArr = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    cellebriteEventsAPI.getUnifiedContacts(caseId, {
      reportKeys: reportKeysArr,
      limit: 1000,
    })
      .then((res) => {
        if (cancelled) return;
        setRows(res?.rows || []);
        setTruncated(!!res?.truncated);
        setPersonCount(res?.person_count || 0);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message || 'Failed to load unified contacts');
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [caseId, selectedReportKeys, reportsReady]);

  // Local substring filter — checks canonical, display number, and
  // every alias name. Cheap because the rollup is bounded by Person
  // cardinality (typically a few hundred per case).
  const filteredRows = useMemo(() => {
    if (!search) return rows;
    const needle = search.toLowerCase();
    return rows.filter((r) => {
      if (r.canonical && r.canonical.toLowerCase().includes(needle)) return true;
      if (r.display_number && r.display_number.toLowerCase().includes(needle)) return true;
      return (r.aliases || []).some((a) => (a.name || '').toLowerCase().includes(needle));
    });
  }, [rows, search]);

  useCellebriteStatus({
    isActive,
    total: rows.length,
    displayed: filteredRows.length,
    selected: 0,
    label: 'unified contacts',
    hint: loading ? 'Loading…' : null,
  });

  const { selectEntity } = useCellebriteSelection();
  const [selectedCanonical, setSelectedCanonical] = useState(null);

  const onPickRow = (row) => {
    setSelectedCanonical(row.canonical || row.person_keys[0]);
    selectEntity({
      type: 'contact_unified',
      id: row.canonical || row.person_keys[0],
      caseId,
      payload: row,
      source: 'contacts.unified',
    });
  };

  if (!caseId) return null;

  return (
    <div className="h-full flex flex-col bg-white min-h-0">
      <PhoneSelector />

      <div className="px-4 py-2 border-b border-light-200 bg-white flex-shrink-0">
        <CellebriteSearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search by number or alias name…"
          matchCount={filteredRows.length}
          totalCount={rows.length}
          itemNoun="contact"
          focusOnSlash
        />
      </div>
      {truncated && (
        <div className="px-4 py-1.5 bg-amber-50 border-b border-amber-200 text-[11px] text-amber-900 flex-shrink-0">
          This case has {personCount.toLocaleString()}+ contacts —
          rollup capped at the top {personCount.toLocaleString()} by activity.
          Rare contacts beyond that may not appear here.
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-auto">
        {loading && rows.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-sm text-light-500">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            Building unified contacts rollup…
          </div>
        ) : error ? (
          <div className="px-4 py-6 text-sm text-red-700">{error}</div>
        ) : filteredRows.length === 0 ? (
          <div className="px-4 py-8 text-sm text-light-500 text-center">
            <Users className="w-8 h-8 mx-auto mb-2 text-light-300" />
            {rows.length === 0
              ? 'No contacts in this case yet — process a Cellebrite report first.'
              : 'No contacts match the current search.'}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-light-50 border-b border-light-200">
              <tr className="text-left text-xs uppercase tracking-wide text-light-600">
                <th className="px-4 py-2 font-semibold">Number</th>
                <th className="px-4 py-2 font-semibold">Aliases used</th>
                <th className="px-4 py-2 font-semibold">Devices</th>
                <th className="px-4 py-2 font-semibold tabular-nums">
                  <Phone className="w-3 h-3 inline mr-1" />Calls
                </th>
                <th className="px-4 py-2 font-semibold tabular-nums">
                  <MessageSquare className="w-3 h-3 inline mr-1" />Msgs
                </th>
                <th className="px-4 py-2 font-semibold tabular-nums">
                  <Mail className="w-3 h-3 inline mr-1" />Emails
                </th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row) => {
                const id = row.canonical || (row.person_keys && row.person_keys[0]);
                const isSelected = id === selectedCanonical;
                return (
                  <tr
                    key={id || Math.random()}
                    onClick={() => onPickRow(row)}
                    className={`cursor-pointer border-b border-light-100 ${
                      isSelected ? 'bg-owl-blue-50' : 'hover:bg-light-50'
                    }`}
                  >
                    <td className="px-4 py-2 font-mono text-owl-blue-900 whitespace-nowrap">
                      {row.display_number || (
                        <span className="italic text-light-500">
                          {row.aliases[0]?.name || '—'}
                        </span>
                      )}
                      {row.is_phone_owner && (
                        <span className="ml-2 text-[9px] uppercase tracking-wide bg-emerald-100 text-emerald-700 px-1 py-px rounded">
                          owner
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <AliasChipGroup aliases={row.aliases || []} reports={reports} />
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(row.report_keys || []).map((rk) => (
                          <PhoneIdentityChip key={rk} reportKey={rk} variant="dense" />
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-light-700">
                      {row.call_count.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-light-700">
                      {row.msg_count.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-light-700">
                      {row.email_count.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        type="button"
                        onClick={(ev) => {
                          ev.stopPropagation();
                          // Publish a selection with a `filter_intent`
                          // hint — CommsCenter (G3) will consume this
                          // to switch its filter to the union of
                          // person_keys. Until G3 ships, this still
                          // opens the rail with the unified row.
                          selectEntity({
                            type: 'contact_unified',
                            id,
                            caseId,
                            payload: { ...row, _filter_intent: 'comms' },
                            source: 'contacts.unified.filter',
                          });
                        }}
                        className="text-xs text-owl-blue-700 hover:underline inline-flex items-center gap-1"
                        title="Filter Comms feed by this number's aliases"
                      >
                        <Filter className="w-3 h-3" />
                        Filter Comms
                        <ExternalLink className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/**
 * Wrapped chip group of alias names used on different devices for the
 * same canonical number. Most-used name first (server-sorted).
 */
function AliasChipGroup({ aliases }) {
  if (!aliases.length) return <span className="text-light-400">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {aliases.map((a) => (
        <span
          key={`${a.key}::${a.name}`}
          className="inline-flex items-center text-[11px] bg-light-100 text-light-700 px-1.5 py-0.5 rounded"
          title={
            a.report_keys.length
              ? `Used on ${a.report_keys.length} device${a.report_keys.length === 1 ? '' : 's'}`
              : a.key
          }
        >
          {a.name}
          {a.report_keys.length > 1 && (
            <span className="ml-1 text-[9px] text-light-500">×{a.report_keys.length}</span>
          )}
        </span>
      ))}
    </div>
  );
}

// Match the icon-export pattern used by the other Cellebrite tabs.
export const UnifiedContactsTabIcon = Users;
