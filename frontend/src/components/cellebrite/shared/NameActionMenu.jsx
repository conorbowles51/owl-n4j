/**
 * NameActionMenu
 *
 * Reusable popover for any clickable person name in the Cellebrite
 * shell. Mounts as a tiny chevron next to the name; clicking opens
 * a 5-item menu covering the universal "what can I do with this
 * person" actions:
 *
 *   - Drill into communications  (push a frame, switch to Communications)
 *   - View Cross-Phone Graph from here (replace perspective, switch tab)
 *   - Filter Comms Center by this person (replace perspective, switch tab)
 *   - Add to current perspective (widen the active frame)
 *   - Replace current perspective (set, no widen, no push)
 *
 * Anchors via React's portal-style absolute positioning relative to
 * the trigger button — no portal library, no z-index war, just a
 * small absolute-positioned div that listens for outside clicks.
 *
 * The component is type-agnostic: it doesn't care whether the name
 * came from a contact row, an email recipient, a message sender, or
 * a graph node — it just needs a `personKey` and a display `name`.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  ChevronDown, Eye, Network, MessageSquare,
  Users, Plus, RefreshCw, ArrowRight,
} from 'lucide-react';
import { usePerspective } from '../../../context/PerspectiveContext';
import { useCellebriteSelection } from './CellebriteSelectionContext';
import { requestCellebriteTabSwitch } from '../../../utils/commsHandoff';

export default function NameActionMenu({
  personKey,
  name,
  // Optional hooks. When `onDrill` is provided, the Drill action calls
  // it INSTEAD of the default push-frame-and-switch-tab — used by
  // Communications to do the drill in-place instead of bouncing tabs.
  onDrill = null,
  // Cosmetic tweaks
  compact = false,
  className = '',
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const perspective = usePerspective();
  const { selectEntity } = useCellebriteSelection();

  // Close on outside click
  useEffect(() => {
    if (!open) return undefined;
    const onDocDown = (e) => {
      if (menuRef.current?.contains(e.target)) return;
      if (triggerRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDocDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!personKey) return null;

  const drill = () => {
    setOpen(false);
    if (onDrill) {
      onDrill(personKey, name);
      return;
    }
    if (perspective) perspective.pushFrame([personKey], name || personKey, 'name-menu.drill');
    requestCellebriteTabSwitch('communications');
  };

  const inGraph = () => {
    setOpen(false);
    if (perspective) perspective.setPerspective([personKey], name || personKey, 'name-menu.graph');
    requestCellebriteTabSwitch('graph');
  };

  const inComms = () => {
    setOpen(false);
    // Reuse the existing _filter_intent:'comms' plumbing so the Comms
    // Center seeds the participants filter the same way it does for
    // Overview "Filter Comms" actions. No PerspectiveContext required
    // for this one to work — but we still push it onto the stack so
    // the user can chain further drills.
    if (perspective) perspective.setPerspective([personKey], name || personKey, 'name-menu.comms');
    selectEntity({
      type: 'name-action',
      id: `name-action-${personKey}-${Date.now()}`,
      caseId: perspective?.caseId,
      payload: { _filter_intent: 'comms', person_keys: [personKey] },
      source: 'name-action-menu',
    });
    requestCellebriteTabSwitch('comms');
  };

  const addToPerspective = () => {
    setOpen(false);
    if (!perspective) return;
    if (perspective.hasPerspective) {
      perspective.widenActive([personKey]);
    } else {
      perspective.setPerspective([personKey], name || personKey, 'name-menu.add');
    }
  };

  const replacePerspective = () => {
    setOpen(false);
    if (perspective) {
      perspective.setPerspective([personKey], name || personKey, 'name-menu.replace');
    }
  };

  // Trigger renders as a chevron button (compact) or a full chip
  // depending on context. The parent decides — in dense tables the
  // chevron is enough; in wider rail blocks a chip reads better.
  return (
    <span className={`inline-flex items-center ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={`Actions for ${name || personKey}`}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`inline-flex items-center justify-center text-light-500 hover:text-owl-blue-700 hover:bg-light-100 rounded ${
          compact ? 'w-4 h-4' : 'w-5 h-5'
        }`}
      >
        <ChevronDown className={compact ? 'w-2.5 h-2.5' : 'w-3 h-3'} />
      </button>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          className="absolute z-50 mt-5 ml-1 min-w-[220px] bg-white border border-light-200 rounded shadow-lg py-1 text-[11px]"
        >
          <MenuHeader name={name || personKey} />
          <Divider />
          <MenuItem icon={ArrowRight} label="Drill into communications" onClick={drill} />
          <MenuItem icon={Network} label="View Cross-Phone Graph from here" onClick={inGraph} />
          <MenuItem icon={MessageSquare} label="Filter Communications Center by this" onClick={inComms} />
          <Divider />
          {perspective?.hasPerspective ? (
            <>
              <MenuItem icon={Plus} label="Add to current perspective" onClick={addToPerspective} />
              <MenuItem icon={RefreshCw} label="Replace perspective" onClick={replacePerspective} />
            </>
          ) : (
            <MenuItem icon={Eye} label="Start perspective from here" onClick={replacePerspective} />
          )}
        </div>
      )}
    </span>
  );
}

function MenuHeader({ name }) {
  return (
    <div className="px-2.5 py-1.5 text-[10px] uppercase tracking-wide text-light-500 flex items-center gap-1 truncate">
      <Users className="w-2.5 h-2.5" />
      <span className="truncate">{name}</span>
    </div>
  );
}

function Divider() {
  return <div className="h-px bg-light-200 my-0.5" />;
}

function MenuItem({ icon: Icon, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      role="menuitem"
      className="w-full text-left flex items-center gap-1.5 px-2.5 py-1 hover:bg-light-50 text-light-800"
    >
      <Icon className="w-3 h-3 text-light-500 flex-shrink-0" />
      <span className="truncate">{label}</span>
    </button>
  );
}
