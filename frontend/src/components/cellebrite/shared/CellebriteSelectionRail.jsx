import React, { useEffect, useState } from 'react';
import {
  ChevronRight, ChevronLeft, X, Phone, MessageSquare, Mail, MapPin,
  Smartphone, User, Activity, Layers, Inbox,
} from 'lucide-react';
import { useCellebriteSelection } from './CellebriteSelectionContext';
import { rendererFor, labelFor } from './rail';

const RAIL_KEY_BASE = 'cellebrite.rail.collapsed';

/**
 * Persistent right-rail for Cellebrite tabs (Reader pattern).
 *
 * Sits at the right edge of every Cellebrite tab; renders a type-aware
 * detail view for whatever the active tab last selected. Collapsible to
 * a 48px icon strip for screen-space.
 *
 * Expanded width: 360px. Collapsed width: 48px. The collapsed state is
 * persisted per-case (so expanding once carries across tabs and across
 * refresh) but the SELECTION itself is not persisted — landing on a
 * stale id after a refresh would just produce a "loading… not found"
 * which is worse than starting empty.
 *
 * The `caseId` prop is used only to scope the collapsed-flag in
 * localStorage; the rail itself doesn't fetch or care about case
 * identity. Renderers can read it via the selection's caseId field.
 */
export default function CellebriteSelectionRail({ caseId }) {
  const { selection, clearSelection } = useCellebriteSelection();

  // Default to COLLAPSED so we don't steal 360px from every existing
  // Cellebrite layout on first load. The first time the user clicks
  // anything that calls selectEntity() we auto-expand (effect below).
  // After that, the user's manual collapse/expand state persists.
  const persistKey = caseId ? `${RAIL_KEY_BASE}.${caseId}` : null;
  const [collapsed, setCollapsed] = useState(() => {
    const stored = readCollapsed(persistKey);
    // null = no prior preference -> default collapsed
    return stored == null ? true : stored;
  });

  // First-selection auto-expand. Only triggers when the user has never
  // manually toggled the rail (stored === null); after that, respect
  // their preference even if a new selection arrives.
  useEffect(() => {
    if (!selection) return;
    const stored = readCollapsed(persistKey);
    if (stored == null && collapsed) {
      setCollapsed(false);
    }
    // We deliberately don't include `collapsed` in deps — we only want
    // this to react to selection arrival, not to user-driven collapses.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection?.id, selection?.type, persistKey]);

  // Persist collapsed state per-case so flipping it once carries across
  // tabs and across refresh. Wrapped in try/catch (private mode, quota).
  useEffect(() => {
    if (!persistKey || typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(persistKey, JSON.stringify({ v: 1, collapsed }));
    } catch {
      // Storage failure is non-fatal — the rail still works for the session.
    }
  }, [persistKey, collapsed]);

  // ----- Collapsed state: thin icon strip -----
  if (collapsed) {
    return (
      <div
        className="flex flex-col items-center w-12 border-l border-light-200 bg-light-50 flex-shrink-0"
        role="complementary"
        aria-label="Cellebrite selection rail (collapsed)"
      >
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="w-12 h-10 flex items-center justify-center text-light-500 hover:text-owl-blue-700 border-b border-light-200"
          title="Expand details rail"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        {selection && (
          <div
            className="w-12 h-10 flex items-center justify-center text-emerald-600"
            title={`Selected: ${labelFor(selection.type)}`}
          >
            {iconFor(selection.type, 'w-4 h-4')}
          </div>
        )}
      </div>
    );
  }

  // ----- Expanded state: full rail -----
  const Renderer = selection ? rendererFor(selection.type) : null;

  return (
    <aside
      className="flex flex-col w-[360px] border-l border-light-200 bg-white flex-shrink-0 min-h-0"
      role="complementary"
      aria-label="Cellebrite selection rail"
    >
      {/* Header */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
        {selection ? (
          <>
            <span className="text-emerald-600">
              {iconFor(selection.type, 'w-3.5 h-3.5')}
            </span>
            <span className="text-xs font-semibold text-owl-blue-900">
              {labelFor(selection.type)}
            </span>
            {selection.payload?.name && (
              <span className="text-xs text-light-600 truncate" title={selection.payload.name}>
                · {selection.payload.name}
              </span>
            )}
            <div className="flex-1" />
            <button
              type="button"
              onClick={clearSelection}
              className="p-1 text-light-400 hover:text-light-700 rounded"
              title="Clear selection"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </>
        ) : (
          <>
            <Inbox className="w-3.5 h-3.5 text-light-400" />
            <span className="text-xs text-light-500">No selection</span>
            <div className="flex-1" />
          </>
        )}
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className="p-1 text-light-400 hover:text-owl-blue-700 rounded"
          title="Collapse rail"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {selection && Renderer ? (
          <Renderer selection={selection} />
        ) : (
          <div className="px-3 py-6 text-xs text-light-500 text-center">
            Select an item to see its details here.
          </div>
        )}
      </div>
    </aside>
  );
}

function iconFor(type, cls = 'w-4 h-4') {
  switch (type) {
    case 'message':      return <MessageSquare className={cls} />;
    case 'call':         return <Phone className={cls} />;
    case 'email':        return <Mail className={cls} />;
    case 'location':     return <MapPin className={cls} />;
    case 'cell_tower':   return <Activity className={cls} />;
    case 'contact':      return <User className={cls} />;
    case 'app_session':  return <Smartphone className={cls} />;
    case 'device_event': return <Activity className={cls} />;
    case 'event':        return <Layers className={cls} />;
    default:             return <Inbox className={cls} />;
  }
}

/**
 * Returns the persisted collapsed flag, or null when no preference has
 * been stored yet. Distinguishing null from false lets the caller
 * default to collapsed on first run AND auto-expand on first selection
 * — without overriding a user who has explicitly chosen `expanded`.
 */
function readCollapsed(key) {
  if (!key || typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.v !== 1) return null;
    return Boolean(parsed.collapsed);
  } catch {
    return null;
  }
}
