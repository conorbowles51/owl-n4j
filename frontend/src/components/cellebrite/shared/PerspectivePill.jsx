/**
 * PerspectivePill
 *
 * Cross-tab indicator for the active people-lens. Mounts above the
 * tab content in CellebriteView so investigators always see whether
 * they're looking at the full case or a perspective subset, and can
 * one-click reach the Graph / Comms / Communications views from the
 * current lens.
 *
 * Hidden when no perspective is active — pays zero visual cost most
 * of the time, surfaces as a sticky 28px-high chip whenever the
 * stack is non-empty.
 *
 * Breadcrumb-style: every frame on the stack is shown as a clickable
 * crumb, with the latest highlighted. Clicking a crumb pops back to
 * it; clicking the X clears the whole stack.
 */

import React from 'react';
import {
  Users, X, Network, MessageSquare, Eye, ChevronRight,
} from 'lucide-react';
import { usePerspective } from '../../../context/PerspectiveContext';
import { requestCellebriteTabSwitch } from '../../../utils/commsHandoff';

export default function PerspectivePill() {
  const ctx = usePerspective();
  if (!ctx || !ctx.hasPerspective) return null;
  const { frames, active, popToFrame, clear } = ctx;

  return (
    <div className="flex items-center gap-2 px-3 py-1 border-b border-amber-200 bg-amber-50 text-[11px] text-amber-900 flex-shrink-0">
      <Eye className="w-3 h-3 text-amber-700 flex-shrink-0" />
      <span className="font-semibold uppercase tracking-wide text-[10px] text-amber-700">
        Perspective
      </span>

      {/* Breadcrumb: every frame as a clickable crumb */}
      <nav className="flex items-center gap-1 flex-wrap min-w-0" aria-label="Perspective breadcrumb">
        {frames.map((f, idx) => {
          const isLast = idx === frames.length - 1;
          return (
            <React.Fragment key={`${idx}-${f.addedAt}`}>
              {idx > 0 && (
                <ChevronRight className="w-3 h-3 text-amber-400 flex-shrink-0" />
              )}
              <button
                type="button"
                onClick={() => popToFrame(idx)}
                className={`px-1.5 py-0.5 rounded inline-flex items-center gap-1 max-w-[180px] truncate ${
                  isLast
                    ? 'bg-amber-200 text-amber-900 font-semibold'
                    : 'text-amber-800 hover:bg-amber-100'
                }`}
                title={f.personKeys.length > 1
                  ? `${f.personKeys.length} people: ${f.personKeys.slice(0, 4).join(', ')}${f.personKeys.length > 4 ? '…' : ''}`
                  : f.personKeys[0]}
              >
                <Users className="w-2.5 h-2.5" />
                <span className="truncate">{f.label}</span>
                {f.personKeys.length > 1 && (
                  <span className="text-[9px] text-amber-600">
                    ({f.personKeys.length})
                  </span>
                )}
              </button>
            </React.Fragment>
          );
        })}
      </nav>

      <div className="flex-1" />

      {/* Cross-tab actions on the active frame */}
      <div className="flex items-center gap-1 flex-shrink-0">
        <ActionButton
          icon={Network}
          label="In Graph"
          title="Show this perspective in the Cross-Phone Graph"
          onClick={() => requestCellebriteTabSwitch('graph')}
        />
        <ActionButton
          icon={MessageSquare}
          label="In Comms"
          title="Filter Comms Center by this perspective"
          onClick={() => requestCellebriteTabSwitch('comms')}
        />
      </div>

      <button
        type="button"
        onClick={clear}
        className="ml-1 inline-flex items-center justify-center w-5 h-5 rounded-full hover:bg-amber-200 text-amber-700"
        title="Clear perspective"
        aria-label="Clear perspective"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}

function ActionButton({ icon: Icon, label, title, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded border border-amber-300 bg-white hover:bg-amber-100 text-amber-800"
    >
      <Icon className="w-2.5 h-2.5" />
      {label}
    </button>
  );
}
