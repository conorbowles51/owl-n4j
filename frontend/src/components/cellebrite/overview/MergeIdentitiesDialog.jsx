import React, { useState, useEffect, useRef } from 'react';
import { X, Loader2, Users, AlertTriangle, Check, Search, Smartphone } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import PersonName from '../shared/PersonName';

/**
 * Investigator-asserted identity merge — SEARCH + PICK (no free-text keys).
 *
 * The system never auto-merges different phone numbers (that would be false
 * attribution). When an investigator KNOWS several numbers/handles are the same
 * person, this folds them into the primary identity: relationships move over,
 * the secondary's name is kept as an alias, and the merge is recorded on the
 * survivor for audit. Not reversible — so you pick real, visible candidates
 * (name + activity + device span) rather than typing a key by hand.
 */
export default function MergeIdentitiesDialog({ caseId, primaryKey, primaryName, onClose, onMerged }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState([]); // [{key, name, ...}]
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const debounce = useRef(null);

  // Debounced case-wide person search, excluding the primary + already-picked.
  useEffect(() => {
    if (!query.trim()) { setResults([]); setSearching(false); return; }
    setSearching(true);
    clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      try {
        const res = await cellebriteOverviewAPI.searchPersons(caseId, query.trim(), { excludeKey: primaryKey, limit: 25 });
        const picked = new Set(selected.map((s) => s.key));
        setResults((res.results || []).filter((r) => !picked.has(r.key)));
      } catch (e) {
        setError(e?.message || 'Search failed');
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(debounce.current);
  }, [query, caseId, primaryKey, selected]);

  const add = (cand) => { setSelected((s) => [...s, cand]); setQuery(''); setResults([]); };
  const remove = (key) => setSelected((s) => s.filter((x) => x.key !== key));

  const submit = async () => {
    if (!selected.length) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await cellebriteOverviewAPI.mergePersons(caseId, primaryKey, selected.map((s) => s.key));
      setResult(res);
      if (res?.merged_count > 0) onMerged?.(res);
    } catch (e) {
      setError(e?.message || 'Merge failed');
    } finally {
      setSubmitting(false);
    }
  };

  const fmt = (c) => `${c.calls} calls · ${c.msgs} msgs${c.emails ? ` · ${c.emails} emails` : ''}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 px-4 py-3 border-b border-light-200">
          <Users className="w-4 h-4 text-owl-blue-700" />
          <div className="flex-1 text-sm font-semibold text-owl-blue-900">Merge identities</div>
          <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-4 space-y-3 overflow-auto">
          <div className="text-xs text-light-600">
            Fold other identities into{' '}
            <span className="font-semibold text-owl-blue-900">{primaryName || primaryKey}</span>{' '}
            <span className="font-mono text-light-500">({primaryKey})</span>.
            Their conversations move here; their names are kept as aliases.
          </div>
          <div className="flex items-start gap-2 rounded bg-amber-50 border border-amber-200 px-2 py-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600 flex-shrink-0 mt-0.5" />
            <span className="text-[11px] text-amber-800">
              Only merge identities you've confirmed are the same person — this can't be undone.
            </span>
          </div>

          {/* Selected identities */}
          {selected.length > 0 && (
            <div className="space-y-1">
              <div className="text-[11px] font-medium text-light-700">To merge in ({selected.length}):</div>
              {selected.map((s) => (
                <div key={s.key} className="flex items-center gap-2 bg-owl-blue-50 border border-owl-blue-200 rounded px-2 py-1">
                  <div className="flex-1 min-w-0">
                    <PersonName name={s.name} personKey={s.key} numbers={s.phone_numbers} className="text-xs font-medium text-owl-blue-900 truncate block" numberClassName="text-[10px]" />
                    <div className="text-[10px] text-light-600 font-mono truncate">{s.key} · {fmt(s)} · {s.devices} device{s.devices === 1 ? '' : 's'}</div>
                  </div>
                  <button onClick={() => remove(s.key)} className="p-0.5 text-light-500 hover:text-red-600"><X className="w-3.5 h-3.5" /></button>
                </div>
              ))}
            </div>
          )}

          {/* Search */}
          {!result && (
            <div>
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-light-400 absolute left-2 top-2.5" />
                <input
                  autoFocus
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by name or number to add…"
                  className="w-full text-xs border border-light-300 rounded pl-7 pr-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-owl-blue-400"
                />
                {searching && <Loader2 className="w-3.5 h-3.5 animate-spin text-light-400 absolute right-2 top-2.5" />}
              </div>
              {/* Results */}
              {results.length > 0 && (
                <div className="mt-1 border border-light-200 rounded divide-y divide-light-100 max-h-52 overflow-auto">
                  {results.map((r) => (
                    <button
                      key={r.key}
                      onClick={() => add(r)}
                      className="w-full text-left px-2 py-1.5 hover:bg-light-50 flex items-center gap-2"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-light-900 truncate flex items-center gap-1">
                          <PersonName name={r.name} personKey={r.key} numbers={r.phone_numbers} numberClassName="text-[10px]" />
                          {r.is_owner && <span className="text-[8px] uppercase bg-emerald-100 text-emerald-700 px-1 rounded">owner</span>}
                        </div>
                        <div className="text-[10px] text-light-500 font-mono truncate">{r.key}</div>
                        <div className="text-[10px] text-light-600">{fmt(r)} · <Smartphone className="w-2.5 h-2.5 inline" /> {r.devices}</div>
                      </div>
                      <span className="text-[10px] text-owl-blue-600">+ add</span>
                    </button>
                  ))}
                </div>
              )}
              {query.trim() && !searching && results.length === 0 && (
                <div className="mt-1 text-[11px] text-light-500">No matching identities.</div>
              )}
            </div>
          )}

          {error && <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">{error}</div>}
          {result && (
            <div className={`text-xs rounded px-2 py-1.5 border ${result.merged_count > 0 ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-light-50 border-light-200 text-light-700'}`}>
              <div className="flex items-center gap-1 font-medium"><Check className="w-3.5 h-3.5" />
                {result.merged_count > 0 ? `Merged ${result.merged_count} identity(ies).` : 'Nothing merged.'}</div>
              {result.merged_count > 0 && (
                <div className="mt-1 text-[11px]">
                  {primaryName || primaryKey} now has {result.relationships_now?.toLocaleString()} linked records.
                  {result.aliases?.length > 0 && <> Aliases: {result.aliases.join(', ')}.</>}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 px-4 py-3 border-t border-light-200">
          <button onClick={onClose} className="px-3 py-1.5 text-xs text-light-700 hover:bg-light-100 rounded">{result ? 'Close' : 'Cancel'}</button>
          {!result && (
            <button
              onClick={submit}
              disabled={submitting || !selected.length}
              className="px-3 py-1.5 text-xs font-medium text-white bg-owl-blue-700 rounded hover:bg-owl-blue-800 disabled:opacity-50 flex items-center gap-1"
            >
              {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Merge {selected.length || ''} selected
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
