import React, { useState } from 'react';
import { X, Loader2, Users, AlertTriangle, Check } from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';

/**
 * Investigator-asserted identity merge.
 *
 * The system never auto-merges different phone numbers — that would be false
 * attribution (see the "Maitra/Maitro/Trabajo 444" case). When an investigator
 * KNOWS several numbers/handles are the same person, this folds them into the
 * primary identity: relationships move over, the secondary's name is kept as an
 * alias, and the merge is recorded on the survivor for audit. Not reversible.
 *
 * Input accepts Person keys (e.g. `phone-13014589977`, `email-x@y.com`) or bare
 * phone numbers (digits are normalised to `phone-<digits>`), one per line.
 */
export default function MergeIdentitiesDialog({ caseId, primaryKey, primaryName, onClose, onMerged }) {
  const [raw, setRaw] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const parseKeys = (text) =>
    text
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => {
        // Already a typed key — leave as-is.
        if (s.includes('-') || s.includes('@')) return s;
        // Bare phone number → phone-<digits>.
        const digits = s.replace(/[^0-9]/g, '');
        return digits ? `phone-${digits}` : s;
      })
      .filter((k) => k && k !== primaryKey);

  const secondaryKeys = parseKeys(raw);

  const submit = async () => {
    if (!secondaryKeys.length) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await cellebriteOverviewAPI.mergePersons(caseId, primaryKey, secondaryKeys);
      setResult(res);
      if (res?.merged_count > 0) onMerged?.(res);
    } catch (e) {
      setError(e?.message || 'Merge failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 max-h-[85vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-light-200">
          <Users className="w-4 h-4 text-owl-blue-700" />
          <div className="flex-1 text-sm font-semibold text-owl-blue-900">Merge identities</div>
          <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-4 space-y-3">
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

          <label className="block text-xs font-medium text-light-700">
            Identities to merge in
            <textarea
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              rows={4}
              placeholder={'phone-13014589977\nphone-12026000064\nor a bare number: 240-429-1127'}
              className="mt-1 w-full text-xs font-mono border border-light-300 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-owl-blue-400"
            />
          </label>

          {secondaryKeys.length > 0 && !result && (
            <div className="text-[11px] text-light-600">
              Will merge {secondaryKeys.length}: {secondaryKeys.map((k) => <span key={k} className="font-mono">{k} </span>)}
            </div>
          )}

          {error && (
            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">{error}</div>
          )}

          {result && (
            <div className={`text-xs rounded px-2 py-1.5 border ${result.merged_count > 0 ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-light-50 border-light-200 text-light-700'}`}>
              <div className="flex items-center gap-1 font-medium">
                <Check className="w-3.5 h-3.5" />
                {result.merged_count > 0
                  ? `Merged ${result.merged_count} identity(ies).`
                  : 'Nothing merged (identities not found or already merged).'}
              </div>
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
          <button onClick={onClose} className="px-3 py-1.5 text-xs text-light-700 hover:bg-light-100 rounded">
            {result ? 'Close' : 'Cancel'}
          </button>
          {!result && (
            <button
              onClick={submit}
              disabled={submitting || !secondaryKeys.length}
              className="px-3 py-1.5 text-xs font-medium text-white bg-owl-blue-700 rounded hover:bg-owl-blue-800 disabled:opacity-50 flex items-center gap-1"
            >
              {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Merge {secondaryKeys.length || ''}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
