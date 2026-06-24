import React from 'react';
import { Filter, ExternalLink } from 'lucide-react';
import { useCellebriteSelection } from '../shared/CellebriteSelectionContext';

/**
 * Tiny "Filter Comms by these parties" trigger used at the trailing
 * edge of every Overview row (Contacts, Messages, Calls, Emails).
 *
 * Click → publishes a synthetic selection carrying the union of person
 * keys + a `_filter_intent: 'comms'` hint. Two existing pieces of
 * shell react:
 *   - FilterIntentTabSwitcher (in CellebriteView) switches the active
 *     tab to Comms.
 *   - CellebriteCommsCenter consumes the hint and seeds the From + To
 *     entity filter with the keys.
 *
 * Type-agnostic: works for any caller that can produce a list of
 * Person keys. The button stops event propagation so wrapping rows
 * with their own onClick (open detail in rail, etc.) keep working.
 */
export default function FilterCommsButton({
  caseId,
  reportKey,
  // Person keys to seed the Comms filter with. Caller assembles
  // whatever it has — sender, recipient, contact key, etc. — and
  // hands them to us. Empty array = no-op (button hidden).
  personKeys = [],
  // Used as the rail selection.id so React state changes when the
  // user clicks different rows; `${type}:${first key}` works fine.
  intentId,
  // Free-form label shown in the rail title bar before Comms takes
  // over. Caller-supplied so the chip reads sensibly per surface.
  label = 'Filter Communications',
  // 'icon' = compact icon-only button (good for dense rows).
  // 'full' = icon + 'Filter Comms' label.
  variant = 'icon',
}) {
  const { selectEntity } = useCellebriteSelection();

  const keys = (personKeys || []).filter(Boolean);
  if (keys.length === 0) return null;

  const onClick = (ev) => {
    // Don't let the parent row's onClick fire — that would also try to
    // open the rail detail / fly-to / etc., racing the tab switch.
    ev.stopPropagation();
    selectEntity({
      // Type doesn't matter for the consumer — it only checks the
      // payload's _filter_intent. We tag it 'event' so the rail's
      // EventAccordion would render gracefully if the user un-switches
      // tabs before the consumer consumes it.
      type: 'event',
      id: intentId || `filter:${keys[0]}`,
      caseId,
      reportKey,
      payload: {
        _filter_intent: 'comms',
        person_keys: keys,
        label,
      },
      source: 'overview.filter-comms',
    });
  };

  if (variant === 'full') {
    return (
      <button
        type="button"
        onClick={onClick}
        className="inline-flex items-center gap-1 text-[11px] text-owl-blue-700 hover:text-owl-blue-900 hover:underline"
        title={`Filter the Communications feed by ${keys.length === 1 ? 'this party' : 'these parties'}`}
      >
        <Filter className="w-3 h-3" />
        Filter Communications
        <ExternalLink className="w-3 h-3" />
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center justify-center text-light-500 hover:text-owl-blue-700 hover:bg-owl-blue-50 rounded p-1 transition-colors"
      title={`Filter the Communications feed by ${keys.length === 1 ? 'this party' : 'these parties'}`}
    >
      <Filter className="w-3.5 h-3.5" />
    </button>
  );
}
