import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

/**
 * Persistent status bar across every Cellebrite tab.
 *
 * Mirrors the Cellebrite Reader bottom strip ("Total: 8497 / Displayed:
 * 8497 / Selected: 0") — always visible so the investigator never has
 * to ask "is this all of it?". The numbers update live as filters,
 * scrubbers, and selections change.
 *
 * Architecture:
 *   - <CellebriteStatusProvider> wraps every tab in CellebriteView.
 *   - Each tab calls useCellebriteStatus({ total, displayed, selected,
 *     label, hint }) when it becomes active. The hook publishes those
 *     counts to the context and clears them on unmount / inactive.
 *   - <CellebriteStatusBar> renders the published values; it shows a
 *     dim "—" when the active tab hasn't published anything yet (e.g.
 *     before its first fetch returns).
 *
 * Counts semantics — kept loose so each tab can interpret them
 * naturally:
 *   total      Cardinality of the underlying dataset for this tab
 *              (e.g. all events in the case, ignoring filters).
 *   displayed  Cardinality after the tab's filter/scrubber pass.
 *   selected   Currently-selected item count (0 if no selection model).
 *   label      Short noun for what's being counted ("events",
 *              "messages", "locations"). Used in the bar's text.
 *   hint       Optional short string surfaced to the right (e.g.
 *              "showing first 5000 of 12340" when the tab caps).
 */

const CellebriteStatusContext = createContext({
  status: null,
  setStatus: () => {},
});

export function CellebriteStatusProvider({ children }) {
  // `status` is whatever the active tab last published, or null when no
  // tab has reported anything (initial state, or between tab switches).
  const [status, setStatus] = useState(null);
  const value = useMemo(() => ({ status, setStatus }), [status]);
  return (
    <CellebriteStatusContext.Provider value={value}>
      {children}
    </CellebriteStatusContext.Provider>
  );
}

/**
 * Tabs call this with their current counts. Pass `null` to clear (e.g.
 * when the tab is being unmounted or becomes inactive). Re-published on
 * every counts change so the bar stays in sync with filter activity.
 *
 * Important: `isActive` gates publishing — a non-active tab must NOT
 * overwrite the active tab's status. CellebriteView keeps tabs mounted
 * across switches; without this gate every keystroke in a hidden tab
 * would clobber the visible tab's bar.
 */
export function useCellebriteStatus({
  isActive,
  total,
  displayed,
  selected = 0,
  label = 'items',
  hint = null,
}) {
  const { setStatus } = useContext(CellebriteStatusContext);

  useEffect(() => {
    if (!isActive) return undefined;
    setStatus({
      total: Number.isFinite(total) ? total : null,
      displayed: Number.isFinite(displayed) ? displayed : null,
      selected: Number.isFinite(selected) ? selected : 0,
      label,
      hint: hint || null,
    });
    // Don't clear on inactive — the next active tab will overwrite.
    // Clearing here would briefly blank the bar during tab switches.
    return undefined;
  }, [isActive, total, displayed, selected, label, hint, setStatus]);
}

/**
 * The bar itself. Mount once at the bottom of CellebriteView. Stays
 * silent (just the empty strip) until a tab publishes something.
 */
export default function CellebriteStatusBar() {
  const { status } = useContext(CellebriteStatusContext);

  const total = status?.total;
  const displayed = status?.displayed;
  const selected = status?.selected ?? 0;
  const label = status?.label || 'items';
  const hint = status?.hint;

  // When displayed equals total we say "of N" — when it differs we
  // surface the filtering visibly so the user knows results are scoped.
  const filtered = (
    typeof total === 'number'
    && typeof displayed === 'number'
    && displayed !== total
  );

  return (
    <div
      className="
        flex items-center gap-4 px-4 py-1.5
        border-t border-light-200 bg-light-50
        text-xs text-light-600
        flex-shrink-0
      "
      role="status"
      aria-live="polite"
    >
      <Stat
        muted={total == null}
        label="Total"
        value={total}
      />
      <Stat
        muted={displayed == null}
        label={filtered ? 'Displayed' : 'Showing'}
        value={displayed}
        accent={filtered ? 'amber' : null}
      />
      <Stat
        muted={false}
        label="Selected"
        value={selected}
        accent={selected > 0 ? 'emerald' : null}
      />
      <span className="text-light-400">{label}</span>
      <div className="flex-1" />
      {hint && (
        <span className="text-light-500 truncate" title={hint}>
          {hint}
        </span>
      )}
    </div>
  );
}

function Stat({ label, value, muted, accent }) {
  const tone =
    accent === 'amber' ? 'text-amber-700'
    : accent === 'emerald' ? 'text-emerald-700'
    : 'text-owl-blue-900';
  return (
    <span className="flex items-center gap-1">
      <span className="text-light-500">{label}:</span>
      <span className={`tabular-nums font-medium ${muted ? 'text-light-400' : tone}`}>
        {muted ? '—' : (value ?? 0).toLocaleString()}
      </span>
    </span>
  );
}
