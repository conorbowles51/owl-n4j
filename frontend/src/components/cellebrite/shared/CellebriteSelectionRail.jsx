import React, { useEffect } from 'react';
import {
  X, Phone, MessageSquare, Mail, MapPin,
  Smartphone, User, Activity, Layers, Inbox,
} from 'lucide-react';
import { useCellebriteSelection } from './CellebriteSelectionContext';
import { rendererFor, labelFor } from './rail';

/**
 * Cellebrite selection flyout (was a persistent right rail).
 *
 * Slides in from the right when the user selects something via
 * selectEntity(). Closed otherwise — paying zero layout cost when no
 * selection exists. Same accordion registry, same cross-surface
 * re-publishing as the previous rail; just no permanent dock.
 *
 * Why it changed: the persistent rail was a constant 360px tax on
 * every Cellebrite layout, paid even when the user hadn't selected
 * anything. Investigators here scan tables → click one row → read →
 * dismiss → scan again. That's intermittent need; the flyout pays
 * cost only when the rail is actually useful.
 *
 * Renderers in shared/rail/ are unchanged — they only render the
 * accordion body, not the flyout chrome.
 *
 * Dismissal:
 *   - X button in the header
 *   - Esc key (window listener while open)
 *   - Click outside (the dim backdrop)
 *
 * The `caseId` prop is no longer used — kept in the signature so
 * callers don't have to update at the same time as this conversion.
 */
// eslint-disable-next-line no-unused-vars
export default function CellebriteSelectionRail({ caseId }) {
  const { selection, clearSelection } = useCellebriteSelection();
  const open = !!selection;

  // Esc key dismisses while open.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') clearSelection();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, clearSelection]);

  // Render nothing when there's no selection — the flyout has zero
  // DOM footprint and no layout impact when closed. Selection arrival
  // mounts both backdrop + panel together; CSS transition handles the
  // slide-in.
  if (!open) return null;

  const Renderer = rendererFor(selection.type);

  return (
    <>
      {/* No backdrop. The previous dim overlay sat above the page
          and — even with pointer-events-none — visually obscured the
          underlying content. Callers that need the rail to coexist
          with a still-usable main view (e.g. Comms Center) shift
          their own layout to make room for the panel; nothing else
          needs dimming. */}

      {/* Slide-in panel */}
      <aside
        className="fixed top-0 right-0 bottom-0 w-[480px] max-w-[90vw] bg-white border-l border-light-200 shadow-2xl z-40 flex flex-col animate-flyout-slide"
        role="complementary"
        aria-label="Cellebrite selection details"
        // Stop propagation so clicks on the panel don't dismiss it via
        // the backdrop's onClick.
        onClick={(e) => e.stopPropagation()}
      >
        {/* Inline keyframes — keeps the animation self-contained
            without needing a tailwind config change. */}
        <style>{`
          @keyframes flyout-slide-in {
            from { transform: translateX(100%); }
            to   { transform: translateX(0); }
          }
          .animate-flyout-slide {
            animation: flyout-slide-in 220ms cubic-bezier(0.22, 0.61, 0.36, 1);
          }
        `}</style>

        {/* Header */}
        <div className="flex items-center gap-1.5 px-3 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
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
            title="Close (Esc)"
            aria-label="Close details flyout"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          <Renderer selection={selection} />
        </div>
      </aside>
    </>
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
